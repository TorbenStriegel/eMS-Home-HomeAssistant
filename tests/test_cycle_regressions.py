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
    """The slow-start confirmation window must be included in the energy."""
    c = coordinator()
    run_samples(c, clock, 1.2, 240)

    # The first sample has no preceding interval: 220 s at 1.2 kW.
    assert c._session_energy_wh == pytest.approx(1.2 * 220 / 3.6)
    assert c._session_seconds == 220


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
    run_samples(c, clock, 1.2, 60)          # too short to confirm
    assert c._gate_energy_wh > 0

    run_samples(c, clock, 0.0, 60)          # power falls away -> candidate gone
    assert c._gate_energy_wh == 0.0


@pytest.mark.parametrize("power_kw", [2.0, 3.0])
def test_instant_start_on_first_sample_preserves_gate(clock, power_kw):
    c = coordinator()
    c._gate_energy_wh = 40.0
    c._gate_grid_wh = 15.0
    c._gate_seconds = 120.0
    c._accumulate_session_energy(sample(power_kw))

    assert c._session_ended is False
    assert c._charge_since == clock.monotonic()
    assert c._session_energy_wh == 40.0
    assert c._session_grid_wh == 15.0
    assert c._session_seconds == 120.0
    assert c._gate_energy_wh == c._gate_grid_wh == c._gate_seconds == 0.0


def test_slow_start_waits_for_full_confirmation_window(clock):
    c = coordinator()
    c._accumulate_session_energy(sample(1.2))
    started = clock.monotonic()
    run_samples(c, clock, 1.2, 160)
    assert c._session_ended is True
    assert c._session_energy_wh == 0.0
    assert c._charge_since == started

    clock.advance(20)
    c._accumulate_session_energy(sample(1.2))
    assert c._session_ended is False
    assert c._session_energy_wh == pytest.approx(60.0)
    assert c._session_seconds == 180.0
    assert c._charge_since == started


def test_instant_start_after_slow_candidate_integrates_once(clock):
    c = coordinator()
    c._accumulate_session_energy(sample(1.2))
    clock.advance(60)
    c._accumulate_session_energy(sample(1.2))
    assert c._gate_energy_wh == pytest.approx(20.0)
    clock.advance(60)
    c._accumulate_session_energy(sample(3.0))
    assert c._session_energy_wh == pytest.approx(70.0)
    assert c._session_grid_wh == pytest.approx(70.0)
    assert c._session_seconds == 120.0
    clock.advance(60)
    c._accumulate_session_energy(sample(3.0))
    assert c._session_energy_wh == pytest.approx(120.0)
    assert c._session_seconds == 180.0


def test_instant_start_fires_exactly_one_start_event(clock):
    from custom_components.ems_home.notifications import EVENT_STARTED

    c = coordinator()
    events = []
    c.hass = SimpleNamespace(
        config=SimpleNamespace(language="en"),
        bus=SimpleNamespace(async_fire=lambda event, data: events.append((event, data))),
    )
    c._accumulate_session_energy(sample(3.0))
    assert [event for event, _ in events] == [EVENT_STARTED]
    run_samples(c, clock, 3.0, 240)
    assert [event for event, _ in events] == [EVENT_STARTED]


@pytest.mark.parametrize("next_power", [1.2, 3.0])
def test_instant_start_clears_charge_since_on_end_and_detects_next_cycle(clock, next_power):
    c = coordinator()
    c._plugged = True
    c._accumulate_session_energy(sample(3.0))
    assert c._charge_since == clock.monotonic()
    run_samples(c, clock, 3.0, 240)
    c._plugged = False
    run_samples(c, clock, 0.0, c.UNPLUG_CONFIRM_SAMPLES * 20)
    assert c._session_ended is True
    assert c._charge_since is None
    previous_energy = c._session_energy_wh

    c._plugged = True
    clock.advance(20)
    c._accumulate_session_energy(sample(next_power))
    assert c._charge_since == clock.monotonic()
    if next_power < c.INSTANT_CYCLE_POWER_KW:
        assert c._session_ended is True
        assert c._session_energy_wh == previous_energy
        run_samples(c, clock, next_power, c.MIN_CYCLE_SECONDS)
    assert c._session_ended is False
    assert c._session_energy_wh < previous_energy


@pytest.mark.parametrize("configured, expected", [(None, 2.0), (0.1, 0.5), (3.4, 3.4), (30, 22.0)])
def test_instant_power_constructor_clamps_configuration(monkeypatch, configured, expected):
    monkeypatch.setattr(coord_mod.DataUpdateCoordinator, "__init__", lambda *args, **kwargs: None)
    c = EMSHomeCoordinator(SimpleNamespace(), SimpleNamespace(), instant_power=configured)
    assert c.INSTANT_CYCLE_POWER_KW == expected


def test_instant_threshold_can_be_lower_than_minimum_power(clock):
    c = coordinator()
    c.MIN_CYCLE_POWER_KW = 4.0
    c._gate_energy_wh = 10.0
    c._accumulate_session_energy(sample(3.0))
    assert c._session_ended is False
    assert c._session_energy_wh == 10.0
    assert c._charge_since == clock.monotonic()


