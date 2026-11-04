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
    obj._session_grid_wh = 0.0
    obj._session_prev = None
    obj._energy_last_ts = None
    obj._latest_smart_meter = None
    obj.grid_price = 0.0
    obj.pv_price = 0.0
    obj._last_session = {}
    return obj


def meter(power_kw: float):
    return SimpleNamespace(power_total=int(power_kw * 1000))


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


def test_all_energy_counts_as_grid_when_the_meter_imports_that_much():
    c = coordinator()
    c._latest_smart_meter = meter(5.0)          # house + car import 5 kW
    c._energy_last_ts = time.monotonic() - 10
    c._accumulate_session_energy(state(3.6))
    assert abs(c._session_energy_wh - c._session_grid_wh) < 0.1


def test_pv_share_when_the_meter_imports_less_than_the_car_draws():
    c = coordinator()
    c._latest_smart_meter = meter(1.8)          # 1.8 kW from the grid
    c._energy_last_ts = time.monotonic() - 10
    c._accumulate_session_energy(state(3.6))
    assert 9.5 < c._session_energy_wh < 10.5
    assert 4.7 < c._session_grid_wh < 5.3       # 1.8 kW * 10 s
    assert c._session_energy_wh - c._session_grid_wh > 4.5   # the rest is PV


def test_export_never_counts_as_grid_energy():
    c = coordinator()
    c._latest_smart_meter = meter(-4.0)         # feeding in, so nothing from the grid
    c._energy_last_ts = time.monotonic() - 10
    c._accumulate_session_energy(state(3.6))
    assert c._session_grid_wh == 0.0


def test_grid_share_resets_with_the_cycle():
    c = coordinator()
    c._session_grid_wh = 4000.0
    c._track_session_cycle(reading(3000, CHARGING))
    c._track_session_cycle(reading(2, CHARGING))
    assert c._session_grid_wh == 0.0 and c._session_energy_wh == 0.0


def test_cost_and_saving_from_the_tariffs():
    from custom_components.ems_home.coordinator import EMSHomeData

    data = EMSHomeData(
        device_status=None,
        emobility_state=None,
        charge_mode=None,
        tracked_session_energy_wh=12400,
        tracked_session_grid_wh=5100,
        grid_price=0.32,
        pv_price=0.0,
    )
    assert data.session_energy_kwh == 12.4
    assert data.session_grid_kwh == 5.1
    assert data.session_pv_kwh == 7.3
    assert data.session_cost == 1.632           # 5.1 kWh * 0.32
    assert data.session_saved == 2.336          # 7.3 kWh * 0.32


def test_no_cost_without_a_tariff():
    from custom_components.ems_home.coordinator import EMSHomeData

    data = EMSHomeData(device_status=None, emobility_state=None, charge_mode=None,
                       tracked_session_energy_wh=12400, tracked_session_grid_wh=5100)
    assert data.session_cost is None
    assert data.session_saved is None


def test_finished_cycle_is_remembered():
    c = coordinator()
    c.grid_price = 0.30
    c._session_energy_wh = 10000.0
    c._session_grid_wh = 4000.0

    c._track_session_cycle(reading(3000, CHARGING))
    c._track_session_cycle(reading(2, CHARGING))    # new cycle

    last = c._last_session
    assert last["energy_kwh"] == 10.0
    assert last["energy_grid_kwh"] == 4.0
    assert last["energy_pv_kwh"] == 6.0
    assert last["duration_min"] == 50.0
    assert last["cost"] == 1.2                      # 4 kWh * 0.30
    assert last["ended_at"]
