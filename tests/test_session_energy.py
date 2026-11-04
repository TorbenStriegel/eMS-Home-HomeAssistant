"""The per-cycle session energy the coordinator integrates itself.

The firmware reports session energy only on some versions (on the tested device
it stays at 0), so the coordinator integrates the reported charging power and
starts over when a new cycle begins.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.ems_home.coordinator import EMSHomeCoordinator  # noqa: E402
from custom_components.ems_home.ws_proto import EVSEReading  # noqa: E402


def coordinator() -> EMSHomeCoordinator:
    obj = object.__new__(EMSHomeCoordinator)
    obj._session_energy_wh = 0.0
    obj._session_prev = None
    obj._energy_last_ts = None
    return obj


def reading(duration: int, status: int) -> EVSEReading:
    return EVSEReading(uuid="wb-1", evse_status=status, session_duration=duration)


def state(power_kw: float):
    return SimpleNamespace(ev_charging_power=SimpleNamespace(total=int(power_kw * 1_000_000)))


CHARGING = 4
SUSPENDED = 12
AVAILABLE = 1


def test_accumulates_while_charging():
    c = coordinator()
    c._energy_last_ts = time.monotonic() - 10  # ten seconds ago
    c._accumulate_session_energy(state(3.6))
    # 3.6 kW for 10 s = 10 Wh
    assert 9.5 < c._session_energy_wh < 10.5


def test_no_accumulation_without_power():
    c = coordinator()
    c._session_energy_wh = 1234.0
    c._energy_last_ts = time.monotonic() - 10
    c._accumulate_session_energy(state(0))
    assert c._session_energy_wh == 1234.0


def test_long_gap_is_not_counted():
    """After a restart the gap is huge – counting it would invent energy."""
    c = coordinator()
    c._energy_last_ts = time.monotonic() - 3600
    c._accumulate_session_energy(state(11))
    assert c._session_energy_wh == 0.0


def test_counter_reset_starts_a_new_cycle():
    c = coordinator()
    c._session_energy_wh = 8421.0
    c._track_session_cycle(reading(3000, CHARGING))
    assert c._session_energy_wh == 8421.0, "still the same cycle"

    c._track_session_cycle(reading(5, CHARGING))  # device restarted its counter
    assert c._session_energy_wh == 0.0
    assert c._energy_last_ts is None


def test_plugging_in_starts_a_new_cycle():
    c = coordinator()
    c._session_energy_wh = 500.0
    c._track_session_cycle(reading(0, AVAILABLE))     # no car
    c._track_session_cycle(reading(0, CHARGING))      # car plugged in
    assert c._session_energy_wh == 0.0


def test_paused_session_keeps_the_counter():
    """Status 12 (paused) must not look like a new cycle."""
    c = coordinator()
    c._session_energy_wh = 700.0
    c._track_session_cycle(reading(600, CHARGING))
    c._track_session_cycle(reading(700, SUSPENDED))
    assert c._session_energy_wh == 700.0
