"""Regressions found by the smoke test against the real device."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.ems_home import coordinator as coord_mod  # noqa: E402
from custom_components.ems_home.coordinator import EMSHomeCoordinator  # noqa: E402
from custom_components.ems_home.ws_proto import EVSEReading, EVSE_PLUGGED_STATES  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.t = 10_000.0

    def monotonic(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture()
def clock(monkeypatch):
    fake = Clock()
    monkeypatch.setattr(coord_mod.time, "monotonic", fake.monotonic)
    return fake


def coordinator() -> EMSHomeCoordinator:
    obj = object.__new__(EMSHomeCoordinator)
    obj._session_energy_wh = 0.0
    obj._session_grid_wh = 0.0
    obj._session_seconds = 0.0
    obj._session_prev = None
    obj._energy_last_ts = None
    obj._latest_smart_meter = None
    obj.grid_price = 0.35
    obj.pv_price = 0.0
    obj._last_session = {}
    obj._session_ended = True
    obj._charge_since = None
    obj._gate_energy_wh = 0.0
    obj._gate_grid_wh = 0.0
    obj._gate_seconds = 0.0
    obj._integrated_state_id = None
    obj._pending_mode = None
    obj._pending_quota = {}
    obj._pending_mode_deadline = 0.0
    obj._store = None
    return obj


def sample(power_kw: float):
    return SimpleNamespace(ev_charging_power=SimpleNamespace(total=int(power_kw * 1_000_000)))


def run_samples(c: EMSHomeCoordinator, clock: Clock, power_kw: float, seconds: float, step: float = 20.0):
    """Feed one sample per `step` seconds for `seconds`."""
    elapsed = 0.0
    while elapsed < seconds:
        clock.advance(step)
        elapsed += step
        c._accumulate_session_energy(sample(power_kw))


def test_the_confirmation_window_is_not_lost(clock):
    """200 s at 3,6 kW used to count 20 Wh instead of 200 Wh."""
    c = coordinator()
    run_samples(c, clock, 3.6, 240)

    # 240 s * 3,6 kW = 0,24 kWh, the first 180 s included
    assert 0.22 <= c._session_energy_wh / 1000 <= 0.26


def test_a_charge_below_the_gate_still_counts_nothing(clock):
    c = coordinator()
    run_samples(c, clock, 0.2, 600)

    assert c._session_energy_wh == 0.0


def test_a_restart_in_the_middle_of_a_charge_continues(clock):
    c = coordinator()
    stored = {
        "energy_wh": 5000.0,
        "grid_wh": 5000.0,
        "seconds": 3600.0,
        "ended": False,
        "last_session": {},
    }

    class Store:
        async def async_load(self):
            return stored

        def async_delay_save(self, *_args, **_kwargs):
            return None

    c._store = Store()
    asyncio.run(c.async_load_session())
    assert c._session_ended is False

    run_samples(c, clock, 3.6, 60)
    assert c._session_energy_wh > 5000.0, "the restored cycle keeps growing"


def test_energy_does_not_grow_without_new_samples(clock):
    c = coordinator()
    c._session_ended = False
    c._energy_last_ts = clock.monotonic() - 20
    c._accumulate_session_energy(sample(3.6))
    once = c._session_energy_wh

    # no time passes: the same reading adds nothing
    c._accumulate_session_energy(sample(3.6))
    assert c._session_energy_wh == once


def test_a_paused_charge_keeps_the_car_plugged():
    """Status 10 (suspended_evse) is a pause, not an unplug."""
    assert 10 in EVSE_PLUGGED_STATES
    assert EVSEReading(uuid="wb", evse_status=10).is_plugged is True


def test_a_single_unplugged_frame_does_not_end_the_cycle(clock):
    """Three samples in a row are needed – one misreported status is not enough."""
    c = coordinator()
    c._session_ended = False
    c._session_energy_wh = 5000.0
    c._plugged = False
    c._energy_last_ts = clock.monotonic() - 20

    for _ in range(EMSHomeCoordinator.UNPLUG_CONFIRM_SAMPLES - 1):
        c._accumulate_session_energy(sample(0.0))
        assert c._session_ended is False

    c._accumulate_session_energy(sample(0.0))
    assert c._session_ended is True


def test_an_aborted_candidate_drops_its_buffer(clock):
    """A short top-up must not leak its energy into the next real charge."""
    c = coordinator()
    run_samples(c, clock, 3.6, 60)          # too short to confirm
    assert c._gate_energy_wh > 0

    run_samples(c, clock, 0.0, 60)          # power falls away -> candidate gone
    assert c._gate_energy_wh == 0.0


def test_a_full_battery_ends_the_cycle_although_the_car_stays_plugged(clock):
    """The wallbox reports 'charging_paused' when the car is full – that is a finish."""
    c = coordinator()
    c._session_ended = False
    c._session_energy_wh = 9000.0
    c._session_grid_wh = 9000.0
    c._plugged = True                      # still plugged in
    c._energy_last_ts = clock.monotonic() - 20

    run_samples(c, clock, 0.0, 240)
    assert c._session_ended is False, "pausing for four minutes is not the end"

    run_samples(c, clock, 0.0, 120)
    assert c._session_ended is True, "five idle minutes end the charge"
    assert c._last_session.get("still_plugged") is True


def test_a_resumed_charge_starts_a_new_cycle(clock):
    c = coordinator()
    run_samples(c, clock, 3.6, 120)          # confirmed
    assert c._session_energy_wh > 0

    run_samples(c, clock, 0.0, 360)          # full -> cycle ends
    assert c._session_ended is True

    run_samples(c, clock, 3.6, 120)          # charging resumes
    assert c._session_ended is False


def test_the_idle_end_value_is_used(clock):
    """The option replaces the 300 s default."""
    c = coordinator()
    c.IDLE_END_SECONDS = 60.0
    c._session_ended = False
    c._session_energy_wh = 5000.0
    c._plugged = True
    c._energy_last_ts = clock.monotonic() - 20

    run_samples(c, clock, 0.0, 120)
    assert c._session_ended is True


class _States:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, entity_id):
        value = self.values.get(entity_id)
        return None if value is None else SimpleNamespace(state=value)


VEHICLE = "sensor.aktuelles_ladefahrzeug"


def with_vehicle_sensor(c: EMSHomeCoordinator) -> dict[str, str]:
    states = _States()
    c.hass = SimpleNamespace(
        config=SimpleNamespace(language="de"),
        states=states,
        bus=SimpleNamespace(async_fire=lambda *_a, **_k: None),
        async_create_task=lambda coro: coro.close(),
    )
    c.notify_vehicle_entity = VEHICLE
    c.notify_enabled = False
    c._plugged = True
    return states.values


def test_the_car_that_drew_the_energy_owns_the_charge(clock):
    """Live on 24.11.: the Mercedes charged for almost four hours. One second before
    the wallbox saw the plug go, the car's own status changed and the vehicle template
    (\"Mercedes if it reports charging, otherwise Seat\") switched to Seat. Reading
    the name only at the end filed the Mercedes charge under the Seat."""
    c = coordinator()
    names = with_vehicle_sensor(c)
    names[VEHICLE] = "Seat"                  # left over: the car cloud lags the wallbox
    run_samples(c, clock, 11.0, 20, step=10)
    names[VEHICLE] = "Mercedes"
    run_samples(c, clock, 11.0, 4 * 3600)
    names[VEHICLE] = "Seat"                  # the car reports first …
    run_samples(c, clock, 11.0, 20)
    c._plugged = False                       # … then the wallbox sees the plug go
    run_samples(c, clock, 0.0, 60)

    assert c._session_ended is True
    assert c._last_session["vehicle"] == "Mercedes"


def test_a_car_without_any_data_still_gets_its_charge(clock):
    """The Seat reports nothing; the template names it by elimination. A swap from
    the Mercedes leaves the sensor on \"Mercedes\" for the first seconds."""
    c = coordinator()
    names = with_vehicle_sensor(c)
    names[VEHICLE] = "Mercedes"
    run_samples(c, clock, 7.0, 80)           # the gate plus 20 s under the old name
    names[VEHICLE] = "Seat"
    run_samples(c, clock, 7.0, 3 * 3600)
    c._plugged = False
    run_samples(c, clock, 0.0, 60)

    assert c._last_session["vehicle"] == "Seat"


def test_a_restart_keeps_the_vehicle_votes(clock):
    c = coordinator()
    names = with_vehicle_sensor(c)
    saved = {}
    stored = {
        "energy_wh": 30000.0,
        "grid_wh": 30000.0,
        "seconds": 10800.0,
        "ended": False,
        "last_session": {},
        # a damaged entry loses only its own vote
        "vehicle_wh": {"Mercedes": 30000.0, "": 5.0, "Seat": "x"},
    }

    class Store:
        async def async_load(self):
            return stored

        def async_delay_save(self, func, _delay):
            saved["data"] = func

    c._store = Store()
    asyncio.run(c.async_load_session())
    assert c._vehicle_wh == {"Mercedes": 30000.0}

    names[VEHICLE] = "Seat"                  # after the restart the sensor is wrong
    run_samples(c, clock, 11.0, 120)
    c._persist_session(force=True)
    assert set(saved["data"]()["vehicle_wh"]) == {"Mercedes", "Seat"}
    c._plugged = False
    run_samples(c, clock, 0.0, 60)

    assert c._last_session["vehicle"] == "Mercedes"


def test_without_votes_the_current_name_is_used(clock):
    c = coordinator()
    names = with_vehicle_sensor(c)
    names[VEHICLE] = "Seat"
    c._session_energy_wh = 1000.0
    c._session_grid_wh = 1000.0
    c._session_seconds = 600.0
    c._finish_cycle(None)

    assert c._last_session["vehicle"] == "Seat"
