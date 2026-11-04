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
