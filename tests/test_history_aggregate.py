"""Calendar aggregation, immutable historical prices and period sensor contracts."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from homeassistant.util import dt as dt_util

from custom_components.ems_home import aggregate, sensor
from custom_components.ems_home.aggregate import HistoryAggregateCache, period_bounds, summarise
from custom_components.ems_home.const import DATA_COORDINATOR, DOMAIN
from custom_components.ems_home.history import ChargingHistory

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 24, 12, tzinfo=BERLIN)
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def local_timezone():
    previous = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(BERLIN)
    yield
    dt_util.set_default_time_zone(previous)


def record(**overrides):
    result = {
        "id": "one", "started_at": "2026-11-23T22:30:00+00:00",
        "ended_at": "2026-11-24T02:00:00+00:00", "energy_wh": 8704,
        "grid_wh": 8408, "duration_s": 10062, "grid_price": 0.35,
        "pv_price": 0, "cost": 2.943, "saved": 0.104, "vehicle": None,
    }
    return {**result, **overrides}


@pytest.mark.parametrize(("period", "now", "start", "end"), [
    ("week", "2026-01-01T12:00", "2025-12-29", "2026-01-05"),
    ("week", "2026-11-29T23:59", "2026-11-23", "2026-11-30"),
    ("month", "2026-02-28T23:59", "2026-02-01", "2026-03-01"),
    ("month", "2028-02-29T23:59", "2028-02-01", "2028-03-01"),
    ("month", "2026-12-31T23:59", "2026-12-01", "2027-01-01"),
    ("year", "2026-12-31T23:59", "2026-01-01", "2027-01-01"),
    ("year", "2027-01-01T00:00", "2027-01-01", "2028-01-01"),
])
def test_calendar_bounds(period, now, start, end):
    bounds = period_bounds(period, datetime.fromisoformat(now).replace(tzinfo=BERLIN))
    assert bounds == tuple(datetime.fromisoformat(v).replace(tzinfo=BERLIN) for v in (start, end))
    assert all(v.hour == v.minute == v.second == v.microsecond == 0 for v in bounds)


def test_total_is_unbounded_and_invalid_period_is_rejected():
    assert period_bounds("total", NOW) == (None, None)
    with pytest.raises(ValueError):
        period_bounds("day", NOW)


@pytest.mark.parametrize("period", ["week", "month", "year"])
def test_half_open_boundaries_and_whole_session_assignment(period):
    start, end = period_bounds(period, NOW)
    entries = [record(id=str(i), started_at=when.isoformat(), ended_at=(end + timedelta(days=1)).isoformat())
               for i, when in enumerate([start - timedelta(seconds=1), start, end - timedelta(seconds=1), end])]
    result = summarise(entries, start, end)
    assert result["sessions"] == 2
    assert result["energy_kwh"] == 17.408
    assert result["duration_min"] == round(20124 / 60, 1)


def test_midnight_month_boundary_uses_local_start_not_utc_or_finish():
    entry = record(started_at="2026-03-31T21:30:00+00:00", ended_at="2026-04-01T01:00:00+00:00")
    march = summarise([entry], *period_bounds("month", datetime(2026, 3, 31, tzinfo=BERLIN)))
    april = summarise([entry], *period_bounds("month", datetime(2026, 4, 1, tzinfo=BERLIN)))
    assert march["energy_kwh"] == 8.704 and march["duration_min"] == 167.7
    assert april["sessions"] == 0
    # UTC still says March, but this charge started on April 1 locally.
    entry["started_at"] = "2026-03-31T22:30:00+00:00"
    assert summarise([entry], *period_bounds("month", datetime(2026, 4, 1, tzinfo=BERLIN)))["sessions"] == 1


@pytest.mark.parametrize(("day", "hours", "timestamps"), [
    ("2026-03-29", 23, ["2026-03-28T23:00:00+00:00", "2026-03-29T00:30:00+00:00", "2026-03-29T01:30:00+00:00", "2026-03-29T21:59:59+00:00"]),
    ("2026-10-25", 25, ["2026-10-24T22:00:00+00:00", "2026-10-25T00:30:00+00:00", "2026-10-25T01:30:00+00:00", "2026-10-25T22:59:59+00:00"]),
])
def test_dst_days_keep_local_assignment_and_monotonic_duration(day, hours, timestamps):
    start = datetime.fromisoformat(day).replace(tzinfo=BERLIN)
    end = start + timedelta(days=1)
    assert (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds() == hours * 3600
    entries = [record(id=str(i), started_at=timestamp) for i, timestamp in enumerate(timestamps)]
    entries += [record(started_at=(start - timedelta(seconds=1)).isoformat()), record(started_at=end.isoformat())]
    result = summarise(entries, start, end)
    assert result["sessions"] == 4
    assert result["energy_kwh"] == 34.816
    assert result["duration_min"] == round(4 * 10062 / 60, 1)


@pytest.mark.parametrize(("period", "day", "start_offset", "end_offset"), [
    ("week", "2026-03-29", 3600, 7200),
    ("week", "2026-10-25", 7200, 3600),
    ("month", "2026-03-29", 3600, 7200),
    ("month", "2026-10-25", 7200, 3600),
])
def test_period_bounds_preserve_dst_offsets(period, day, start_offset, end_offset):
    start, end = period_bounds(period, datetime.fromisoformat(day).replace(tzinfo=BERLIN))
    assert start.utcoffset().total_seconds() == start_offset
    assert end.utcoffset().total_seconds() == end_offset


def test_thousand_entries_sum_integer_wh_seconds_and_stored_money_exactly():
    entries = [record(id=str(i), energy_wh=1001 + i * 7, grid_wh=503 + i * 3,
                      duration_s=61 + i, cost=0.101, saved=0.003) for i in range(1000)]
    result = summarise(entries, None, None)
    assert result["energy_kwh"] == sum(s["energy_wh"] for s in entries) / 1000
    assert result["energy_grid_kwh"] == sum(s["grid_wh"] for s in entries) / 1000
    assert result["energy_pv_kwh"] == sum(s["energy_wh"] - s["grid_wh"] for s in entries) / 1000
    assert result["duration_min"] == round(sum(s["duration_s"] for s in entries) / 60, 1)
    assert result["cost"] == float(sum(Decimal(str(s["cost"])) for s in entries)) == 101
    assert result["saved"] == 3
    assert result["avg_kwh"] == round(sum(s["energy_wh"] for s in entries) / 1_000_000, 3)
    assert result["min_kwh"] == 1.001
    assert result["max_kwh"] == entries[-1]["energy_wh"] / 1000


def test_price_change_cannot_reprice_stored_month_costs():
    from custom_components.ems_home.coordinator import EMSHomeData

    from custom_components.ems_home.ems_home_api import ChargeModeConfig, DeviceStatus, EMobilityState

    entries = [record()]
    before = deepcopy(entries)
    data = EMSHomeData(
        device_status=DeviceStatus.from_dict({}),
        emobility_state=EMobilityState.from_dict({}),
        charge_mode=ChargeModeConfig.from_dict({}),
    )
    data.grid_price = 0.35
    result = summarise(entries, *period_bounds("month", NOW))
    data.grid_price = 0.99
    data.pv_price = 0.25
    assert summarise(entries, *period_bounds("month", NOW)) == result
    assert result["cost"] == 2.943 and entries == before


def test_only_priced_sessions_contribute_money_and_zero_is_a_price():
    result = summarise([record(), record(cost=None, saved=100), record(cost=0, saved=0)], None, None)
    assert result["sessions"] == 3 and result["priced_sessions"] == 2
    assert result["cost"] == 2.943 and result["saved"] == 0.104
    assert summarise([record(cost=0, saved=0)], None, None)["cost"] == 0


def test_no_priced_sessions_in_period_means_null_not_zero():
    result = summarise([record(cost=None, saved=None), record(started_at="2026-10-01T00:00:00+00:00")], *period_bounds("month", NOW))
    assert result["sessions"] == 1 and result["priced_sessions"] == 0
    assert result["cost"] is result["saved"] is None
    result = summarise([record(grid_price=None, pv_price=0.1, saved=None)], None, None)
    assert result["cost"] == 2.943 and result["saved"] is None


@pytest.mark.parametrize("vehicle", [None, "", "   "])
def test_vehicle_attribute_is_absent_without_names(vehicle):
    assert "by_vehicle" not in summarise([record(vehicle=vehicle)], None, None)


def test_vehicle_groups_only_named_sessions_without_losing_unnamed_energy():
    entries = [record(vehicle="Seat"), record(vehicle="Seat", cost=None), record(vehicle="BMW", cost=None), record()]
    result = summarise(entries, None, None)
    assert result["sessions"] == 4
    assert result["by_vehicle"] == {
        "Seat": {"sessions": 2, "energy_kwh": 17.408, "cost": 2.943},
        "BMW": {"sessions": 1, "energy_kwh": 8.704, "cost": None},
    }


@pytest.mark.parametrize("period", aggregate.PERIODS)
def test_empty_history_has_zero_metrics_no_vehicle_and_null_money(period):
    result = summarise([], *period_bounds(period, NOW))
    assert result == {"sessions": 0, "energy_kwh": 0, "energy_grid_kwh": 0,
                      "energy_pv_kwh": 0, "cost": None, "saved": None,
                      "priced_sessions": 0, "avg_kwh": 0, "max_kwh": 0,
                      "min_kwh": 0, "duration_min": 0, "price_per_kwh": None}


@pytest.mark.parametrize("timestamp", [None, "invalid"])
def test_unassignable_starts_only_count_in_total(timestamp):
    entries = [record(started_at=timestamp)]
    assert summarise(entries, *period_bounds("month", NOW))["sessions"] == 0
    assert summarise(entries, None, None)["sessions"] == 1


def test_naive_legacy_timestamp_is_utc():
    assert summarise([record(started_at="2026-03-31T22:30:00")], *period_bounds("month", datetime(2026, 4, 1, tzinfo=BERLIN)))["sessions"] == 1


def test_cache_avoids_scans_and_invalidates_for_append_delete_rollover_upsert(monkeypatch):
    counted = Mock(wraps=aggregate.summarise)
    monkeypatch.setattr(aggregate, "summarise", counted)
    cache = HistoryAggregateCache()
    entries = [record()]
    for _ in range(10):
        cache.get("month", entries, NOW)
    assert counted.call_count == 1
    entries.append(record(id="two"))
    assert cache.get("month", entries, NOW)[2]["sessions"] == 2
    entries.pop(0)
    assert cache.get("month", entries, NOW)[2]["sessions"] == 1
    entries[0] = record(id="three")
    cache.get("month", entries, NOW)
    cache.get("month", entries, NOW, revision="new-write")
    cache.get("month", entries, NOW.replace(month=12), revision="new-write")
    assert counted.call_count == 6
    assert len(cache._results) == 1


def test_cache_never_leaks_nested_mutations_or_cross_entry_results():
    cache = HistoryAggregateCache()
    entries = [record(vehicle="Seat")]
    result = cache.get("total", entries, NOW)[2]
    result["by_vehicle"]["Seat"]["cost"] = -999
    assert cache.get("total", entries, NOW)[2]["by_vehicle"]["Seat"]["cost"] == 2.943
    assert HistoryAggregateCache().get("total", [record(cost=99)], NOW)[2]["cost"] == 99


def make_entity(period="month", *, enabled=True):
    history = ChargingHistory(SimpleNamespace(async_delay_save=Mock()))
    history.enabled = enabled
    coordinator = SimpleNamespace(_history=history, last_update_success=False,
                                  client=SimpleNamespace(uses_https=False, host="localhost", port=80),
                                  async_add_listener=Mock())
    description = next(d for d in sensor.SENSOR_DESCRIPTIONS if d.key == f"history_{period}")
    return sensor.EMSHistorySensor(coordinator, SimpleNamespace(entry_id="entry"), description)


@pytest.mark.parametrize("period", aggregate.PERIODS)
def test_sensor_metadata_state_attributes_reset_and_offline_availability(period, monkeypatch):
    monkeypatch.setattr(sensor.dt_util, "now", lambda: NOW)
    entity = make_entity(period)
    description = entity.entity_description
    assert entity.unique_id == f"entry_history_{period}"
    assert description.state_class == sensor.SensorStateClass.TOTAL
    assert description.device_class == sensor.SensorDeviceClass.ENERGY
    assert description.native_unit_of_measurement == "kWh"
    assert description.entity_category is None and description.requires is None
    assert entity.available and entity.native_value == 0
    entity.coordinator._history.upsert(record(vehicle="Seat"))
    assert entity.native_value == 8.704
    start, end = period_bounds(period, NOW)
    assert entity.last_reset == (dt_util.as_utc(start) if start else None)
    assert entity.extra_state_attributes == {
        **{k: v for k, v in summarise([record(vehicle="Seat")], start, end).items() if k != "energy_kwh"},
        "period_start": start.isoformat() if start else None,
        "period_end": end.isoformat() if end else None, "estimated": True,
    }


def test_sensor_upsert_refreshes_same_count_and_id_and_deletion_decreases(monkeypatch):
    monkeypatch.setattr(sensor.dt_util, "now", lambda: NOW)
    entity = make_entity()
    history = entity.coordinator._history
    history.upsert(record())
    assert entity.native_value == 8.704
    history.upsert(record(energy_wh=9000))
    assert entity.native_value == 9
    history.sessions.clear()
    assert entity.native_value == 0


def test_sensor_changes_period_without_new_history_and_disabled_is_unavailable(monkeypatch):
    monkeypatch.setattr(sensor.dt_util, "now", lambda: NOW)
    entity = make_entity()
    entity.coordinator._history.upsert(record())
    assert entity.native_value == 8.704
    monkeypatch.setattr(sensor.dt_util, "now", lambda: NOW.replace(month=12))
    assert entity.native_value == 0
    assert entity.extra_state_attributes["period_start"] == "2026-12-01T00:00:00+01:00"
    entity.coordinator._history.enabled = False
    assert not entity.available
    entity.coordinator._history = None
    assert not entity.available


def test_setup_registers_four_history_sensors_and_keeps_existing_entities():
    entity = make_entity()
    entry = SimpleNamespace(entry_id="entry")
    hass = SimpleNamespace(data={DOMAIN: {"entry": {DATA_COORDINATOR: entity.coordinator}}})
    collected = []
    asyncio.run(sensor.async_setup_entry(hass, entry, lambda entities: collected.extend(entities)))
    assert len(collected) == len(sensor.SENSOR_DESCRIPTIONS)
    assert sum(isinstance(e, sensor.EMSHistorySensor) for e in collected) == 4
    assert len({e.unique_id for e in collected}) == len(collected)
    for item in collected:
        if not item.entity_description.key.startswith("history_"):
            assert type(item) is sensor.EMSHomeSensor


def test_translation_keys_exist_with_consistent_english_names_and_numeric_states():
    paths = ["strings.json", "translations/en.json", "translations/de.json"]
    translations = [json.loads((ROOT / "custom_components/ems_home" / path).read_text())["entity"]["sensor"] for path in paths]
    for period, german in zip(aggregate.PERIODS, ["Woche", "Monat", "Jahr", "gesamt"]):
        key = f"history_{period}"
        assert translations[0][key] == translations[1][key] == {"name": f"Charging history {period}"}
        assert translations[2][key] == {"name": f"Ladehistorie {german}"}
        # kWh states are numeric; HA formats them rather than translating enums.
        assert "state" not in translations[0][key]
