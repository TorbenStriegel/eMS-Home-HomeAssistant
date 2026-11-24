"""Monthly compaction, replay protection and explicitly disabled history."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
import logging
import json
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.ems_home.aggregate import archive_session, period_bounds, summarise
from custom_components.ems_home.history import ChargingHistory, HistoryStore, history_key
from test_history import FakeStore, make_coordinator, record
from test_history_aggregate import make_entity
from test_history_services import setup, call

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 24, 12, tzinfo=BERLIN)


@pytest.fixture(autouse=True)
def local_clock(monkeypatch):
    previous = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(BERLIN)
    monkeypatch.setattr(dt_util, "now", lambda: NOW)
    yield
    dt_util.set_default_time_zone(previous)


def load(data=None, **options):
    obj = ChargingHistory(FakeStore(deepcopy(data)), **options)
    asyncio.run(obj.async_load())
    return obj


def total(obj, period="total"):
    return summarise(obj.sessions, *period_bounds(period, NOW), archive=obj.archive)


def test_load_compacts_old_months_and_keeps_local_boundary_and_unknown_dates():
    entries = [
        record("old", started_at="2021-10-31T22:59:59Z"),
        record("boundary", started_at="2021-10-31T23:00:00Z"),
        record("recent"), record("unknown", started_at=None),
    ]
    before = summarise(entries, None, None)
    obj = load({"sessions": entries, "future": {"preserved": True}})
    assert [s["id"] for s in obj.sessions] == ["boundary", "recent", "unknown"]
    assert list(obj.archive) == ["2021-10"]
    assert obj.archive["2021-10"]["count"] == 1
    assert total(obj) == before
    assert obj._store.delayed
    assert obj._data()["future"] == {"preserved": True}


def test_finish_compacts_after_month_rollover_and_preserves_snapshots(monkeypatch):
    obj = load({"sessions": [record("oct", started_at="2026-10-15T12:00:00Z")]}, retention_months=1)
    assert not obj.archive
    obj.upsert(record("nov"))
    snapshot = obj._store.delayed[-1][0]()
    monkeypatch.setattr(dt_util, "now", lambda: NOW.replace(month=12))
    obj.upsert(record("dec", started_at="2026-12-01T12:00:00Z"))
    assert [s["id"] for s in obj.sessions] == ["nov", "dec"]
    assert obj.archive["2026-10"]["count"] == 1
    assert len(snapshot["sessions"]) == 2 and "archive" not in snapshot


def test_thousand_entries_all_metrics_and_vehicle_totals_survive_repeated_compaction():
    entries = [record(str(i), started_at="2021-03-01T12:00:00Z",
                      energy_wh=1001 + i, grid_wh=503 + i // 2, duration_s=61 + i,
                      cost=None if i % 3 == 0 else 0.101,
                      saved=None if i % 5 == 0 else 0.003,
                      vehicle=["Seat", "BMW", None][i % 3]) for i in range(1000)]
    before = summarise(entries, None, None)
    obj = load({"sessions": entries[:500]})
    for entry in entries[500:]:
        obj.upsert(entry)
    assert obj.sessions == []
    assert total(obj) == before
    bucket = obj.archive["2021-03"]
    assert bucket["energy_wh"] == sum(s["energy_wh"] for s in entries)
    assert bucket["grid_wh"] == sum(s["grid_wh"] for s in entries)
    assert bucket["duration_s"] == sum(s["duration_s"] for s in entries)
    assert bucket["min_wh"] == 1001 and bucket["max_wh"] == 2000
    assert bucket["count"] == 1000
    assert not obj.apply_retention()
    restored = load(obj._data())
    assert total(restored) == before
    assert not restored._store.delayed


def test_unlimited_keeps_all_details_but_does_not_discard_existing_archive():
    old = record("old", started_at="2000-01-01T12:00:00Z")
    archive = {"1999-12": archive_session({}, old)}
    obj = load({"sessions": [old], "archive": archive}, retention_months=0)
    assert obj.sessions == [old] and obj.archive == archive
    assert not obj._store.delayed
    obj.upsert(record("older", started_at="1998-01-01T12:00:00Z"))
    assert len(obj.sessions) == 2 and obj.archive == archive


def test_archived_pending_record_is_not_counted_again_after_reload():
    old = record("pending", started_at="2020-01-01T12:00:00Z")
    obj = load({"sessions": [old]})
    restored = load(obj._data())
    assert restored.has("pending")
    assert not restored.reconcile(old)
    assert not restored.upsert(old)
    assert restored.sessions == [] and total(restored)["sessions"] == 1
    assert restored.reconciled == 0 and not restored._store.delayed


@pytest.mark.parametrize("period", ["year", "total"])
def test_archive_is_included_in_sensors_and_cache_refresh(period):
    entity = make_entity(period)
    obj = load({"sessions": [record("jan", started_at="2026-01-15T12:00:00Z"),
                              record("old", started_at="2025-01-15T12:00:00Z"), record()]},
               retention_months=0)
    entity.coordinator._history = obj
    before = entity.native_value, entity.extra_state_attributes
    obj.retention_months = 1
    obj.upsert(record())
    assert obj.archive and (entity.native_value, entity.extra_state_attributes) == before
    assert entity.native_value == (17.408 if period == "year" else 26.112)


def test_existing_archive_merges_instead_of_replacing_and_keeps_unknown_fields():
    old = record("old", started_at="2021-03-01T12:00:00Z")
    bucket = archive_session({}, old)
    bucket["future"] = "preserved"
    obj = load({"archive": {"2021-03": bucket}, "sessions": [{**old, "id": "second"}]})
    assert obj.archive["2021-03"]["count"] == 2
    assert obj.archive["2021-03"]["future"] == "preserved"
    assert total(obj) == summarise([old, old], None, None)


def test_unpriced_archived_sessions_keep_null_money_and_unnamed_vehicles():
    old = record("old", started_at="2020-01-01T00:00:00Z", cost=None, saved=None, vehicle=None)
    obj = load({"sessions": [old]})
    assert obj.archive["2020-01"]["cost"] is None
    assert obj.archive["2020-01"]["saved"] is None
    assert total(obj) == summarise([old], None, None)
    assert "by_vehicle" not in total(obj)


def test_disabled_neither_loads_nor_writes_and_does_not_keep_pending_records():
    store = FakeStore(raise_on_load=AssertionError("must not load"))
    obj = ChargingHistory(store, enabled=False)
    asyncio.run(obj.async_load())
    assert not obj.enabled and obj.load_error is None
    assert not obj.upsert(record()) and not obj.reconcile(record())
    assert not obj.delete("abc123") and not obj.apply_retention()
    c = make_coordinator(obj)
    c._start_cycle_record(0)
    c._last_session = {"energy_kwh": 8.704, "ended_at": NOW.isoformat()}
    c._record_history("idle", True)
    assert c._pending_record is None
    asyncio.run(obj.async_flush())
    assert not store.saved and not store.delayed


@pytest.mark.parametrize("period", ["week", "month", "year", "total"])
def test_disabled_sensors_write_actual_unavailable_state_with_attribute(tmp_path, period):
    from homeassistant.helpers.entity_platform import EntityPlatform

    async def run():
        hass = HomeAssistant(str(tmp_path))
        entity = make_entity(period)
        entity.coordinator._history = ChargingHistory(FakeStore(), enabled=False)
        await entity.coordinator._history.async_load()
        entity.hass = hass
        entity.entity_id = f"sensor.history_{period}"
        entity.platform = EntityPlatform(
            hass=hass, logger=logging.getLogger(__name__), domain="sensor",
            platform_name="ems_home", platform=None,
            scan_interval=timedelta(seconds=20), entity_namespace=None,
        )
        entity.async_write_ha_state()
        state = hass.states.get(entity.entity_id)
        assert state.state == "unavailable"
        # Home Assistant does not write extra attributes for an unavailable state,
        # so the flag is asserted on the entity itself.
        assert entity.extra_state_attributes["history_disabled"] is True
        assert not entity.available

    asyncio.run(run())


@pytest.mark.parametrize("with_archive", [False, True])
def test_real_store_migration_with_and_without_optional_archive(tmp_path, with_archive):
    async def run():
        hass = HomeAssistant(str(tmp_path))
        key = history_key("migration")
        store = HistoryStore(hass, 1, key, minor_version=1)
        path = tmp_path / ".storage" / key
        path.parent.mkdir()
        data = {"sessions": [record()], "future": 42}
        if with_archive:
            # The concept's older bucket has no pricing counters and only
            # count/energy per vehicle. Both remain readable.
            data["archive"] = {"2020-01": {
                "count": 2, "energy_wh": 4000, "grid_wh": 2000,
                "cost": 0.7, "saved": 0.7, "duration_s": 1200,
                "min_wh": 1000, "max_wh": 3000,
                "by_vehicle": {"Seat": {"count": 2, "energy_wh": 4000}},
            }}
        path.write_text(json.dumps({"version": 1, "minor_version": 0, "key": key, "data": data}))
        obj = ChargingHistory(store, hass)
        await obj.async_load()
        assert obj.enabled and obj.sessions == [record()]
        assert obj.archive == data.get("archive", {})
        assert total(obj)["energy_kwh"] == (12.704 if with_archive else 8.704)
        obj.upsert(record("new"))
        await obj.async_flush()
        persisted = json.loads(path.read_text())["data"]
        assert persisted["future"] == 42
        assert persisted.get("archive", {}) == data.get("archive", {})

    asyncio.run(run())


@pytest.mark.parametrize("archive", [[], {"bad": {}}, {"2020-13": {}},
                                      {"2020-01": {"count": "bad", "energy_wh": 1}}])
def test_invalid_archive_is_not_changed_even_during_minor_migration(tmp_path, archive):
    async def run():
        hass = HomeAssistant(str(tmp_path))
        store = HistoryStore(hass, 1, history_key("broken"), minor_version=1)
        path = tmp_path / ".storage" / store.key
        path.parent.mkdir()
        raw = json.dumps({"version": 1, "minor_version": 0, "key": store.key,
                          "data": {"sessions": [], "archive": archive}})
        path.write_text(raw)
        obj = ChargingHistory(store, hass)
        await obj.async_load()
        assert not obj.enabled and obj.load_error
        assert not obj.upsert(record())
        await obj.async_flush()
        assert path.read_text() == raw

    asyncio.run(run())


def test_disabled_finish_survives_session_reload_without_backfill():
    from test_history import SnapshotStore

    disabled = load(enabled=False)
    c = make_coordinator(disabled)
    c._store = SnapshotStore({"ended": True, "pending_record": record()})
    asyncio.run(c.async_load_session())
    assert c._pending_record is None
    c._start_cycle_record(0)
    c._last_session = {"energy_kwh": 8.704, "ended_at": NOW.isoformat()}
    c._record_history("idle", True)
    c._announce_finish_inner()
    assert c._fired[-1][1]["session_id"] == c._cycle["id"]
    c._history = load()
    c._reconcile_history()
    assert c._history.sessions == []


@pytest.mark.parametrize("options, enabled, months", [
    ({}, True, 60),
    ({"history_enabled": False, "history_retention_months": 0}, False, 0),
    ({"history_retention_months": 600}, True, 600),
])
def test_setup_passes_flat_history_options_to_runtime(monkeypatch, options, enabled, months):
    from unittest.mock import AsyncMock, Mock
    from custom_components import ems_home as integration

    store = FakeStore()
    monkeypatch.setattr(integration, "HistoryStore", Mock(return_value=store))
    client = Mock()
    monkeypatch.setattr(integration, "EMSHomeHTTP", Mock(return_value=client))
    factory = Mock(return_value=SimpleNamespace(
        async_load_session=AsyncMock(), async_config_entry_first_refresh=AsyncMock(),
        async_start_websockets=AsyncMock(), async_stop_websockets=AsyncMock(),
    ))
    monkeypatch.setattr(integration, "EMSHomeCoordinator", factory)
    monkeypatch.setattr(integration, "_async_register_services", Mock())
    monkeypatch.setattr(integration, "_async_register_card", AsyncMock())
    hass = SimpleNamespace(
        data={}, async_add_executor_job=AsyncMock(),
        config=SimpleNamespace(config_dir="/tmp", path=lambda *parts: "/tmp"),
        config_entries=SimpleNamespace(async_forward_entry_setups=AsyncMock()),
        bus=SimpleNamespace(async_listen_once=Mock()),
    )
    entry = SimpleNamespace(
        entry_id="runtime", options=options, data={"host": "localhost", "password": "test-only"},
        async_on_unload=Mock(), add_update_listener=Mock(),
    )
    assert asyncio.run(integration.async_setup_entry(hass, entry))
    obj = factory.call_args.kwargs["history"]
    assert obj.configured_enabled is enabled and obj.enabled is enabled
    assert obj.retention_months == months
    assert not store.delayed and not store.saved


def test_a_damaged_entry_is_skipped_instead_of_breaking_the_history():
    """One broken record must not cost the user the whole history.

    The damaged entry stays in the file (so it can be repaired) but is never
    counted: it has no energy, so it cannot be archived or summarised.
    """
    from custom_components.ems_home import aggregate

    obj = ChargingHistory(
        FakeStore({"sessions": [record("valid", started_at="2020-01-01T00:00:00Z"),
                                {"id": "invalid", "started_at": "2020-01-02T00:00:00Z"}]}),
        retention_months=0,          # keep everything detailed for this check
    )
    asyncio.run(obj.async_load())
    assert obj.enabled
    assert {s.get("id") for s in obj.sessions} == {"valid", "invalid"}
    summary = aggregate.summarise(obj.sessions, None, None)
    assert summary["sessions"] == 1, "only the usable entry counts"


def test_month_chart_combines_archive_and_sessions_for_multiple_entries(tmp_path):
    async def run():
        hass, c = await setup(tmp_path, [record()])
        old = record("jan", started_at="2026-01-15T12:00:00Z")
        c._history = ChargingHistory(FakeStore({"sessions": [old, record()]}), retention_months=1)
        await c._history.async_load()
        before = await call(hass, start="2026-11-24", vehicle="missing", offset=100)
        months = before["months"]
        assert len(months) == 12 and months[0]["month"] == "2025-12"
        assert months[1]["month"] == "2026-01"
        assert months[1]["energy_kwh"] == 8.704
        assert months[-1]["energy_kwh"] == 8.704
        assert before["count"] == 0 and before["sessions"] == []
        second = ChargingHistory(FakeStore({"sessions": [old]}), retention_months=1)
        await second.async_load()
        hass.data["ems_home"]["second"] = {"coordinator": SimpleNamespace(_history=second)}
        combined = await call(hass)
        assert combined["months"][1]["energy_kwh"] == 17.408
        assert combined["months"][1]["sessions"] == 2
        assert combined["count"] == 1
        assert (await call(hass, entry_id="first"))["months"] == months

    asyncio.run(run())
