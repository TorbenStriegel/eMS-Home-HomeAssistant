"""History service contracts exercised through the real HA service registry."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import os
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
import yaml

from custom_components import ems_home as integration
from custom_components.ems_home import history_services as services, sensor
from custom_components.ems_home.const import DATA_COORDINATOR, DOMAIN
from custom_components.ems_home.coordinator import EMSHomeCoordinator
from custom_components.ems_home.history import ChargingHistory, history_key

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 24, 12, tzinfo=BERLIN)


@pytest.fixture(autouse=True)
def local_time(monkeypatch):
    previous = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(BERLIN)
    monkeypatch.setattr(dt_util, "now", lambda: NOW)
    yield
    dt_util.set_default_time_zone(previous)


class MemoryStore:
    def __init__(self, sessions):
        self.data = {"sessions": deepcopy(sessions)}
        self.delayed = []

    async def async_load(self):
        return deepcopy(self.data)

    def async_delay_save(self, data, delay):
        self.delayed.append(data)

    async def async_save(self, data):
        self.data = deepcopy(data)


def record(session_id="one", **overrides):
    return {
        "id": session_id,
        "started_at": "2026-11-23T23:00:00+00:00",
        "ended_at": "2026-11-24T01:00:00+00:00",
        "duration_s": 3600,
        "energy_wh": 8000,
        "grid_wh": 6000,
        "cost": 2.1,
        "saved": 0.7,
        "mode_start": "hybrid",
        "mode_end": "hybrid",
        "vehicle": "Seat",
        "end_reason": "idle",
        "flags": [],
        **overrides,
    }


async def setup(tmp_path, sessions=None):
    hass = HomeAssistant(str(tmp_path))
    # The manifest depends on http, so a loaded integration always has it.
    hass.http = SimpleNamespace()
    history = ChargingHistory(MemoryStore([record()] if sessions is None else sessions))
    await history.async_load()
    coordinator = EMSHomeCoordinator(
        hass,
        SimpleNamespace(uses_https=False, host="localhost", port=80),
        20,
        history=history,
    )
    coordinator.async_stop_websockets = AsyncMock()
    hass.data[DOMAIN] = {"first": {DATA_COORDINATOR: coordinator}}
    # The http component seeds this at startup; the signed export link needs it.
    hass.data["http.auth"] = "test-refresh-token"
    integration._async_register_services(hass)
    return hass, coordinator


async def call(hass, name="get_history", **data):
    return await hass.services.async_call(
        DOMAIN, name, data, blocking=True, return_response=True
    )


def test_pagination_count_sorting_and_snapshot_isolation(tmp_path):
    async def run():
        entries = [
            record(str(i), started_at=f"2026-11-{i + 1:02}T10:00:00+00:00")
            for i in range(25)
        ]
        hass, coordinator = await setup(tmp_path, entries)
        result = await call(hass)
        assert result["count"] == 25 and len(result["sessions"]) == 20
        assert result["limit"] == 20 and result["offset"] == 0
        result = await call(hass, limit=3, offset=2)
        assert [s["id"] for s in result["sessions"]] == ["22", "21", "20"]
        assert result["count"] == 25 and result["limit"] == 3 and result["offset"] == 2
        result["sessions"][0]["flags"].append("changed")
        assert coordinator._history.sessions[22]["flags"] == []
        assert (await call(hass, offset=200))["sessions"] == []
        assert len((await call(hass, limit=200))["sessions"]) == 25

    asyncio.run(run())


@pytest.mark.parametrize(
    "bounds",
    [
        {"start": "2026-11-24", "end": "2026-11-24"},
        {"start": date(2026, 11, 24), "end": date(2026, 11, 24)},
        {"start": "2026-11-24T00:00:00", "end": "2026-11-25T00:00:00"},
        {"start": "2026-11-23T23:00:00Z", "end": "2026-11-24T23:00:00Z"},
    ],
)
def test_period_and_vehicle_filter_count_and_unfiltered_months(tmp_path, bounds):
    async def run():
        entries = [
            record("before", started_at="2026-11-23T22:59:59Z"),
            record("first"),
            record("second", started_at="2026-11-24T22:59:59Z"),
            record("other", vehicle="BMW"),
            record("after", started_at="2026-11-24T23:00:00Z"),
            record("october", started_at="2026-10-01T10:00:00Z"),
        ]
        hass, _ = await setup(tmp_path, entries)
        result = await call(hass, **bounds, vehicle="Seat", limit=1, offset=1)
        assert result["count"] == 2 and [s["id"] for s in result["sessions"]] == [
            "first"
        ]
        months = result["months"]
        assert len(months) == 12
        assert months[0]["month"] == "2025-12" and months[-1]["month"] == "2026-11"
        assert months[-1] == {
            "month": "2026-11", "key": "2026-11",
            "sessions": 5, "energy_kwh": 40, "energy_grid_kwh": 30, "energy_pv_kwh": 10,
            "cost": 10.5, "saved": 3.5,
        }
        assert months[-2]["sessions"] == 1
        assert months[0]["sessions"] == 0 and months[0]["cost"] is None
        assert (await call(hass, vehicle="missing"))["months"] == months

    asyncio.run(run())


@pytest.mark.parametrize(
    ("day", "start", "end"),
    [
        ("2026-03-29", "2026-03-28T23:00:00Z", "2026-03-29T22:00:00Z"),
        ("2026-10-25", "2026-10-24T22:00:00Z", "2026-10-25T23:00:00Z"),
    ],
)
def test_dst_local_date_bounds(tmp_path, day, start, end):
    async def run():
        hass, _ = await setup(
            tmp_path, [record("start", started_at=start), record("end", started_at=end)]
        )
        result = await call(hass, start=day, end=day)
        assert [s["id"] for s in result["sessions"]] == ["start"]

    asyncio.run(run())


def test_sort_uses_instants_and_legacy_missing_dates(tmp_path):
    async def run():
        hass, _ = await setup(
            tmp_path,
            [
                record("later", started_at="2026-11-24T01:00:00+01:00"),
                record("earlier", started_at="2026-11-23T23:30:00Z"),
                record("unknown", started_at=None),
            ],
        )
        assert [s["id"] for s in (await call(hass))["sessions"]] == [
            "later",
            "earlier",
            "unknown",
        ]
        assert (await call(hass, start="2026-11-24"))["count"] == 2

    asyncio.run(run())


@pytest.mark.parametrize(
    "data",
    [
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
        {"limit": 1.5},
        {"months": 5},
        {"months": 25},
        {"months": 6.5},
        {"months": "6"},
        {"months": True},
        {"start": "yesterday"},
        {"end": "2026-99-01"},
        {"start": "2026-12-01", "end": "2026-11-01"},
    ],
)
def test_invalid_query_is_rejected(tmp_path, data):
    async def run():
        hass, _ = await setup(tmp_path)
        with pytest.raises(vol.Invalid):
            await call(hass, **data)

    asyncio.run(run())


@pytest.mark.parametrize(
    "data",
    [
        {"session_id": "one"},
        {"session_id": "one", "confirm": False},
        {"session_id": "one", "confirm": "true"},
        {"confirm": True},
    ],
)
def test_delete_requires_explicit_true_confirmation_and_id(tmp_path, data):
    async def run():
        hass, coordinator = await setup(tmp_path)
        with pytest.raises(vol.Invalid):
            await call(hass, "delete_session", **data)
        assert coordinator._history.has("one")
        assert not coordinator._history._store.delayed

    asyncio.run(run())


def test_delete_one_immediately_refreshes_all_periods_and_persists(tmp_path):
    async def run():
        hass, coordinator = await setup(tmp_path, [record(), record("two")])
        entities = [
            sensor.EMSHistorySensor(
                coordinator, SimpleNamespace(entry_id="first"), desc
            )
            for desc in sensor.SENSOR_DESCRIPTIONS
            if desc.key.startswith("history_")
        ]
        assert [entity.native_value for entity in entities] == [16] * 4
        observed = []
        remove = coordinator.async_add_listener(
            lambda: observed.append([e.native_value for e in entities])
        )
        try:
            before = coordinator._history.last_write_at
            assert await call(
                hass, "delete_session", session_id="one", confirm=True
            ) == {"deleted": True}
            assert observed == [[8] * 4]
            assert coordinator._history.last_write_at != before
            for entity in entities:
                assert entity.extra_state_attributes["cost"] == 2.1
                assert entity.extra_state_attributes["sessions"] == 1
            assert [s["id"] for s in coordinator._history._store.data["sessions"]] == [
                "two"
            ]
            assert await call(
                hass, "delete_session", session_id="one", confirm=True
            ) == {"deleted": False}
            assert len(observed) == 1
            # Simulate the session store still carrying the deleted pending_record.
            restored = ChargingHistory(coordinator._history._store)
            await restored.async_load()
            coordinator._history = restored
            coordinator._pending_record = record()
            coordinator._reconcile_history()
            assert not restored.has("one") and restored.has("two")
            assert not restored.upsert(record())
            assert not restored.has("one")
        finally:
            remove()

    asyncio.run(run())


@pytest.mark.parametrize(
    "name", [n for n in services.HISTORY_SERVICES if n != "cleanup_exports"]
)
def test_unknown_entry_warns_and_never_targets_other_entries(tmp_path, caplog, name):
    async def run():
        hass, coordinator = await setup(tmp_path)
        data = {"entry_id": "unknown"}
        if name == "delete_session":
            data.update(session_id="one", confirm=True)
        if name == "update_session":
            data.update(session_id="one", vehicle="X")
        if name == "export_history":
            data["format"] = "csv"
        result = await call(hass, name, **data)
        if name == "get_history":
            assert (
                result["sessions"] == []
                and result["count"] == 0
                and len(result["months"]) == 12
            )
        elif name == "delete_session":
            assert result == {"deleted": False}
        elif name == "update_session":
            assert result == {"updated": False}
        else:
            assert result == {}
        assert coordinator._history.has("one")
        assert not (tmp_path / DOMAIN).exists()
        assert "Unknown entry_id unknown" in caplog.text

    asyncio.run(run())


@pytest.mark.parametrize("entry_id", ["second", None])
def test_multiple_entries_target_selection_and_delete_exactly_one(tmp_path, entry_id):
    async def run():
        hass, first = await setup(tmp_path)
        history = ChargingHistory(MemoryStore([record()]))
        await history.async_load()
        second = SimpleNamespace(_history=history, async_update_listeners=lambda: None)
        hass.data[DOMAIN]["second"] = {DATA_COORDINATOR: second}
        assert (await call(hass))["count"] == 2
        assert (await call(hass, entry_id="second"))["count"] == 1
        selection = {"entry_id": entry_id} if entry_id is not None else {}
        assert await call(
            hass, "delete_session", **selection, session_id="one", confirm=True
        ) == {"deleted": True}
        assert first._history.has("one") is (entry_id == "second")
        assert history.has("one") is (entry_id is None)

    asyncio.run(run())


@pytest.mark.parametrize("state", ["disabled", "absent"])
def test_unavailable_history_is_empty_and_not_modified(tmp_path, state):
    async def run():
        hass, coordinator = await setup(tmp_path)
        original = coordinator._history
        if state == "absent":
            coordinator._history = None
        else:
            original.enabled = False
        assert (await call(hass))["count"] == 0
        assert await call(hass, "delete_session", session_id="one", confirm=True) == {
            "deleted": False
        }
        assert original.has("one") and not original._store.delayed

    asyncio.run(run())


@pytest.mark.parametrize("file_format", ["csv", "json"])
def test_export_private_file_all_rows_columns_and_collision(tmp_path, file_format):
    async def run():
        entries = [
            record(str(i), vehicle="Seat, ä\nTest", flags=["gap", "restarted"])
            for i in range(25)
        ]
        hass, _ = await setup(tmp_path, entries)
        response = await call(hass, "export_history", format=file_format)
        path = Path(response["path"])
        assert path.parent == tmp_path / DOMAIN
        assert path.name == f"history-20261124-120000.{file_format}"
        assert "www" not in path.parts and path.stat().st_mode & 0o777 == 0o600
        content = path.read_text(encoding="utf-8")
        if file_format == "csv":
            with path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                assert reader.fieldnames == list(services.CSV_COLUMNS)
            assert len(rows) == 25
            assert rows[0] == {
                "started_at": entries[0]["started_at"],
                "ended_at": entries[0]["ended_at"],
                "duration_min": "60.0",
                "energy_kwh": "8.0",
                "energy_grid_kwh": "6.0",
                "energy_pv_kwh": "2.0",
                "cost": "2.1",
                "saved": "0.7",
                "mode": "hybrid",
                "vehicle": "Seat, ä\nTest",
                "end_reason": "idle",
                "flags": "gap;restarted",
                "session_id": "0",
            }
        else:
            assert json.loads(content) == entries
        second = Path((await call(hass, "export_history", format=file_format))["path"])
        assert second != path and path.read_text(encoding="utf-8") == content
        assert second.is_file()

    asyncio.run(run())


@pytest.mark.parametrize("file_format", ["csv", "json"])
def test_export_filters_and_empty_export(tmp_path, file_format):
    async def run():
        hass, _ = await setup(
            tmp_path, [record(), record("old", started_at="2025-01-01T10:00:00Z")]
        )
        for start, expected in [("2026-11-24", 1), ("2027-01-01", 0)]:
            path = Path(
                (
                    await call(
                        hass,
                        "export_history",
                        format=file_format,
                        start=start,
                        end="2027-12-31",
                    )
                )["path"]
            )
            with path.open(encoding="utf-8", newline="") as handle:
                rows = (
                    json.load(handle)
                    if file_format == "json"
                    else list(csv.DictReader(handle))
                )
            assert len(rows) == expected

    asyncio.run(run())


def test_export_rejects_public_directory_symlink_and_invalid_format(tmp_path):
    async def run():
        hass, _ = await setup(tmp_path)
        with pytest.raises(vol.Invalid):
            await call(hass, "export_history", format="../www")
        public = tmp_path / "www"
        public.mkdir()
        (tmp_path / DOMAIN).symlink_to(public, target_is_directory=True)
        with pytest.raises(ServiceValidationError, match="symbolic link"):
            await call(hass, "export_history", format="csv")
        assert list(public.iterdir()) == []

    asyncio.run(run())


def test_csv_escapes_formula_like_vehicle_without_changing_json(tmp_path):
    async def run():
        hass, _ = await setup(tmp_path, [record(vehicle="=1+1")])
        path = Path((await call(hass, "export_history", format="csv"))["path"])
        with path.open(newline="") as handle:
            assert list(csv.DictReader(handle))[0]["vehicle"] == "'=1+1"
        assert (await call(hass))["sessions"][0]["vehicle"] == "=1+1"

    asyncio.run(run())


def test_registration_response_support_unload_failure_last_unload_and_reload(tmp_path):
    async def run():
        hass, coordinator = await setup(tmp_path)
        hass.config_entries = SimpleNamespace(
            async_unload_platforms=AsyncMock(return_value=True)
        )
        hass.data[DOMAIN]["second"] = {DATA_COORDINATOR: coordinator}
        integration._async_register_services(hass)
        for name in ("get_history", "export_history"):
            assert (
                hass.services.supports_response(DOMAIN, name) == SupportsResponse.ONLY
            )
        assert (
            hass.services.supports_response(DOMAIN, "delete_session")
            == SupportsResponse.OPTIONAL
        )
        assert await integration.async_unload_entry(
            hass, SimpleNamespace(entry_id="first")
        )
        assert (await call(hass))["count"] == 1
        hass.config_entries.async_unload_platforms.return_value = False
        assert not await integration.async_unload_entry(
            hass, SimpleNamespace(entry_id="second")
        )
        assert all(
            hass.services.has_service(DOMAIN, n) for n in services.HISTORY_SERVICES
        )
        hass.config_entries.async_unload_platforms.return_value = True
        assert await integration.async_unload_entry(
            hass, SimpleNamespace(entry_id="second")
        )
        assert not any(
            hass.services.has_service(DOMAIN, n) for n in services.HISTORY_SERVICES
        )
        hass.data[DOMAIN]["new"] = {DATA_COORDINATOR: coordinator}
        integration._async_register_services(hass)
        assert (await call(hass, entry_id="new"))["count"] == 1

    asyncio.run(run())


def test_service_metadata_matches_schema_fields():
    path = Path(services.__file__).with_name("services.yaml")
    metadata = yaml.safe_load(path.read_text())
    schemas = {
        "get_history": services.GET_HISTORY_SCHEMA.validators[0],
        "delete_session": services.DELETE_SESSION_SCHEMA,
        "export_history": services.EXPORT_HISTORY_SCHEMA.validators[0],
        "update_session": services.UPDATE_SESSION_SCHEMA,
    }
    for name, schema in schemas.items():
        fields = metadata[name]["fields"]
        assert set(fields) == {str(key.schema) for key in schema.schema}
        assert metadata[name]["name"] and metadata[name]["description"]
        assert all(
            field.get("name") and field.get("description") for field in fields.values()
        )


@pytest.mark.parametrize("months", [6, 12, 24])
def test_chart_month_count_includes_archives_and_ignores_filters(tmp_path, months):
    async def run():
        hass, coordinator = await setup(tmp_path, [
            record("old", started_at="2025-01-10T12:00:00Z"),
            record("january", started_at="2026-01-10T12:00:00Z"),
            record(),
        ])
        history = coordinator._history
        assert history is not None
        history.retention_months = 1
        assert history.apply_retention(NOW)
        assert len(history.sessions) == 1
        assert "2025-01" in history.archive and "2026-01" in history.archive
        result = await call(hass, months=months, vehicle="missing", offset=100)
        assert result["sessions"] == [] and result["count"] == 0
        buckets = result["months"]
        assert len(buckets) == months
        assert buckets[0]["month"] == {6: "2026-06", 12: "2025-12", 24: "2024-12"}[months]
        assert buckets[-1]["month"] == "2026-11"
        assert buckets[-1]["energy_kwh"] == 8
        assert buckets[-1]["cost"] == 2.1
        by_month = {bucket["month"]: bucket for bucket in buckets}
        for key in ("2025-01", "2026-01"):
            if key in by_month:
                assert by_month[key]["energy_kwh"] == 8
                assert by_month[key]["sessions"] == 1
                assert by_month[key]["saved"] == 0.7
        assert result["months"] == (await call(hass, months=months))["months"]
        assert len((await call(hass))["months"]) == 12

    asyncio.run(run())


def test_both_card_modules_are_registered_once_without_changing_version(monkeypatch):
    extra = Mock()
    resources = AsyncMock(return_value=True)
    static_paths = AsyncMock()
    monkeypatch.setattr(integration, "_CARD_REGISTERED", False)
    monkeypatch.setattr(integration, "_async_add_lovelace_resource", resources)
    monkeypatch.setattr("homeassistant.components.frontend.add_extra_js_url", extra)
    async def _run_inline(function, *args):
        return function(*args)

    hass = SimpleNamespace(
        http=SimpleNamespace(async_register_static_paths=static_paths),
        async_add_executor_job=_run_inline,
    )

    async def run():
        await integration._async_register_card(hass)
        await integration._async_register_card(hass)

    asyncio.run(run())
    # The URL carries version *and* a content hash, so a CDN cannot keep an older
    # file or a cached 404 after an update that did not change the version string.
    expected = [
        f"{integration.CARD_URL}?v={integration._asset_version()}",
        f"{integration.STATIC_URL_PATH}/ems-home-history-cards.js?v={integration._asset_version()}",
    ]
    assert integration._asset_version().startswith(f"{integration.VERSION}-")
    assert len(integration._asset_version().rsplit("-", 1)[1]) == 8
    assert [item.args[1] for item in extra.call_args_list] == expected
    assert [item.args[1] for item in resources.call_args_list] == expected
    static_paths.assert_awaited_once()
    frontend = Path(integration.__file__).with_name("frontend")
    for url in expected:
        filename = url.split("/")[-1].split("?")[0]
        assert (frontend / filename).is_file()

def test_update_session_corrects_only_what_was_given(tmp_path):
    async def run():
        hass, coordinator = await setup(tmp_path, [record(grid_price=0.35, pv_price=0.0)])
        session_id = coordinator._history.sessions[0]["id"]
        result = await call(hass, "update_session", session_id=session_id, vehicle="Polestar 2")
        assert result["updated"] is True
        session = result["session"]
        assert session["vehicle"] == "Polestar 2"
        # No price was given, so the stored cost must not be recalculated.
        assert session["cost"] == 2.1 and session["saved"] == 0.7
        assert session["edited_at"]
        stored = (await call(hass))["sessions"][0]
        assert stored["vehicle"] == "Polestar 2" and stored["id"] == session_id
        # The period sensors must see the edit, so the write has to be persisted.
        assert coordinator._history.enabled

    asyncio.run(run())


def test_update_session_recalculates_cost_from_the_stored_energy(tmp_path):
    async def run():
        hass, coordinator = await setup(tmp_path, [record(grid_price=0.30, pv_price=0.10)])
        session_id = coordinator._history.sessions[0]["id"]
        result = await call(hass, "update_session", session_id=session_id, grid_price=0.42, pv_price=0.12)
        session = result["session"]
        # 6 kWh grid × 0,42 + 2 kWh PV × 0,12 = 2,52 + 0,24
        assert session["cost"] == 2.76
        # Same rule as the recording path: PV share × (grid − PV tariff) = 2 × 0,30
        assert session["saved"] == 0.6
        summary = (await call(hass))["sessions"][0]
        assert summary["cost"] == 2.76

    asyncio.run(run())


def test_update_session_without_fields_does_not_touch_the_entry(tmp_path):
    async def run():
        hass, coordinator = await setup(tmp_path)
        session_id = coordinator._history.sessions[0]["id"]
        assert await call(hass, "update_session", session_id=session_id) == {"updated": False}
        assert "edited_at" not in coordinator._history.sessions[0]

    asyncio.run(run())


def test_update_session_of_an_unknown_id_changes_nothing(tmp_path):
    async def run():
        hass, coordinator = await setup(tmp_path)
        before = deepcopy(coordinator._history.sessions)
        assert await call(hass, "update_session", session_id="missing", vehicle="X") == {
            "updated": False
        }
        assert coordinator._history.sessions == before

    asyncio.run(run())


def test_update_session_refuses_archived_sessions(tmp_path):
    async def run():
        hass, coordinator = await setup(tmp_path)
        session_id = coordinator._history.sessions[0]["id"]
        # Archived months keep totals only, so the individual record is immutable.
        coordinator._history._other["archived_session_ids"] = [session_id]
        assert await call(hass, "update_session", session_id=session_id, vehicle="X") == {
            "updated": False
        }

    asyncio.run(run())


def test_update_session_clears_an_empty_vehicle_name(tmp_path):
    async def run():
        hass, coordinator = await setup(tmp_path)
        session_id = coordinator._history.sessions[0]["id"]
        result = await call(hass, "update_session", session_id=session_id, vehicle="  ")
        assert result["session"]["vehicle"] is None

    asyncio.run(run())

def test_price_per_kwh_ignores_unpriced_energy(tmp_path):
    async def run():
        hass, _ = await setup(tmp_path, [
            record("priced", grid_price=0.35, pv_price=0.0),
            record("unpriced", started_at="2026-11-22T10:00:00Z",
                   cost=None, saved=None, grid_price=None, pv_price=None),
        ])
        sensor_state = (await call(hass))["sessions"]
        assert len(sensor_state) == 2
        from custom_components.ems_home.aggregate import summarise
        summary = summarise(sensor_state, None, None)
        # One priced charge of 8 kWh costs 2,10 € (6 kWh grid, 2 kWh PV at 0), so the
        # average is 0,2625 €/kWh. The unpriced 8 kWh must not halve it to 0,13125.
        assert summary["priced_sessions"] == 1
        assert summary["price_per_kwh"] == 0.2625

    asyncio.run(run())


def test_daily_buckets_cover_the_window_oldest_first(tmp_path):
    async def run():
        hass, _ = await setup(tmp_path, [
            record("today", started_at="2026-11-24T10:00:00+00:00"),
            record("yesterday", started_at="2026-11-23T10:00:00+00:00"),
        ])
        result = await call(hass, resolution="day", days=7)
        buckets = result["buckets"]
        assert len(buckets) == 7
        assert buckets[-1]["day"] == "2026-11-24" and buckets[-2]["day"] == "2026-11-23"
        assert buckets[-1]["sessions"] == 1 and buckets[-2]["sessions"] == 1
        assert sum(bucket["sessions"] for bucket in buckets) == 2
        assert buckets[0]["sessions"] == 0
        # Months stay available next to the daily buckets for the yearly view.
        assert len(result["months"]) == 12

    asyncio.run(run())


@pytest.mark.parametrize("days", [0, 93])
def test_daily_bucket_window_is_validated(tmp_path, days):
    async def run():
        hass, _ = await setup(tmp_path)
        with pytest.raises(vol.Invalid):
            await call(hass, resolution="day", days=days)

    asyncio.run(run())


def test_month_buckets_carry_the_energy_split(tmp_path):
    async def run():
        hass, _ = await setup(tmp_path, [record("one", grid_price=0.35, pv_price=0.0)])
        bucket = (await call(hass))["months"][-1]
        assert bucket["energy_grid_kwh"] == 6 and bucket["energy_pv_kwh"] == 2

    asyncio.run(run())


def test_update_session_with_a_cleared_tariff_marks_the_money_unknown(tmp_path):
    """A tariff set to null cannot price the charge; the old amount must not survive."""

    async def run():
        hass, coordinator = await setup(tmp_path, [record(grid_price=0.30, pv_price=0.10)])
        session_id = coordinator._history.sessions[0]["id"]
        result = await call(hass, "update_session", session_id=session_id, pv_price=None)
        session = result["session"]
        assert result["updated"] is True
        assert session["pv_price"] is None
        assert session["cost"] is None and session["saved"] is None

    asyncio.run(run())


def test_export_hands_out_a_signed_download_link(tmp_path):
    """The service keeps its file path and adds a link a phone can open."""

    async def run():
        hass, coordinator = await setup(tmp_path)
        result = await call(hass, "export_history", format="csv")

        assert result["rows"] == 1
        assert Path(result["path"]).is_file()
        assert result["url"].startswith("/api/ems_home/export/")
        assert "authSig=" in result["url"]
        assert datetime.fromisoformat(result["expires_at"]) > dt_util.utcnow()
        assert "warnings" not in result

        from custom_components.ems_home.export import registry

        export_id = result["url"].split("/api/ems_home/export/")[1].split("?")[0]
        ticket, reason = registry(hass).claim(export_id)
        assert ticket is not None and reason == "ok"
        assert ticket.rows == 1
        assert ticket.path == Path(result["path"])

    asyncio.run(run())


def test_export_of_an_empty_range_is_valid_and_says_so(tmp_path):
    async def run():
        hass, coordinator = await setup(tmp_path)
        result = await call(
            hass,
            "export_history",
            format="csv",
            start=datetime(2020, 1, 1),
            end=datetime(2020, 2, 1),
        )
        assert result["rows"] == 0
        assert result["warnings"] == ["no_sessions_in_range"]
        text = Path(result["path"]).read_text(encoding="utf-8")
        assert text.strip() == ",".join(services.CSV_COLUMNS)

    asyncio.run(run())


def test_export_warns_when_only_archive_months_remain(tmp_path):
    """An unbounded export cannot contain details that were rolled into the archive."""

    async def run():
        hass, coordinator = await setup(tmp_path, [])
        coordinator._history._other["archive"] = {
            "2026-10": {
                "count": 1, "energy_wh": 1000, "grid_wh": 800, "cost": 0.3,
                "saved": 0.1, "priced_sessions": 1, "saved_sessions": 1,
                "priced_energy_wh": 1000,
            }
        }
        result = await call(hass, "export_history", format="csv")
        assert result["rows"] == 0
        assert "archived_details_unavailable" in result["warnings"]
        assert "no_sessions_in_range" in result["warnings"]

    asyncio.run(run())


def test_the_month_warning_spans_a_year_boundary(tmp_path):
    from custom_components.ems_home.history_services import _range_months

    months = _range_months(
        {"start": datetime(2025, 12, 31, 23), "end": datetime(2026, 1, 1, 12)}
    )
    assert months == {"2025-12", "2026-01"}


def test_an_end_only_range_does_not_warn_about_later_archive_months(tmp_path):
    """A filter that stops in September cannot be missing October's details."""

    async def run():
        hass, coordinator = await setup(tmp_path, [])
        coordinator._history._other["archive"] = {
            "2026-10": {
                "count": 1, "energy_wh": 1000, "grid_wh": 800, "cost": 0.3,
                "saved": 0.1, "priced_sessions": 1, "saved_sessions": 1,
                "priced_energy_wh": 1000,
            }
        }
        result = await call(hass, "export_history", format="csv", end=date(2026, 9, 30))
        assert "archived_details_unavailable" not in result.get("warnings", [])
        assert "no_sessions_in_range" in result["warnings"]

        inside = await call(hass, "export_history", format="csv", end=date(2026, 10, 31))
        assert "archived_details_unavailable" in inside["warnings"]

    asyncio.run(run())


def test_a_broken_record_does_not_abort_the_export(tmp_path):
    """A half written session is skipped and reported, not turned into HTTP 500."""

    async def run():
        broken = record("broken")
        broken.pop("duration_s")
        hass, coordinator = await setup(tmp_path, [record("good"), broken])
        result = await call(hass, "export_history", format="csv")

        assert result["rows"] == 1
        assert result["skipped"] == 1
        assert "incomplete_records_skipped" in result["warnings"]
        body = Path(result["path"]).read_text(encoding="utf-8")
        assert "good" in body and "broken" not in body

    asyncio.run(run())


def test_an_export_without_http_is_refused_before_writing(tmp_path):
    """Without the http component there is no link, so nothing should be written."""

    async def run():
        from homeassistant.exceptions import HomeAssistantError

        hass, coordinator = await setup(tmp_path)
        hass.http = None
        with pytest.raises(HomeAssistantError, match="HTTP"):
            await call(hass, "export_history", format="csv")
        directory = Path(hass.config.path("ems_home"))
        assert not directory.exists() or not list(directory.glob("history-*"))

    asyncio.run(run())


def test_a_corrupt_flags_field_does_not_cost_the_session_its_row(tmp_path):
    """flags is a list of strings, but a broken store must not raise on the way out."""

    async def run():
        sessions = [
            record("a", flags=[None]),
            record("b", flags=17),
            record("c", flags="pv"),
            record("d", flags=None),
            record("e", flags=["pv", "estimated"]),
        ]
        hass, coordinator = await setup(tmp_path, sessions)
        result = await call(hass, "export_history", format="csv")

        assert result["rows"] == 5 and "skipped" not in result
        body = Path(result["path"]).read_text(encoding="utf-8")
        assert "a,pv" not in body  # the None flag is not a value
        assert "pv;estimated" in body

    asyncio.run(run())


def test_a_boolean_id_is_not_an_id(tmp_path):
    """JSON true is not a session id, and a row with one would look like a real id."""

    async def run():
        hass, coordinator = await setup(tmp_path, [record("ok"), record("bool", id=True)])
        result = await call(hass, "export_history", format="csv")
        assert result["rows"] == 1
        assert result["skipped"] == 1

    asyncio.run(run())


def test_removing_the_entry_deletes_the_history_file(tmp_path):
    """The README promises the store goes away with the integration; check the hook."""

    async def run():
        from custom_components.ems_home.history import (
            HISTORY_MINOR_VERSION,
            HISTORY_VERSION,
            HistoryStore,
        )

        hass, coordinator = await setup(tmp_path)
        store = HistoryStore(
            hass, HISTORY_VERSION, history_key("first"),
            minor_version=HISTORY_MINOR_VERSION,
        )
        path = Path(store.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

        await integration.async_remove_entry(hass, SimpleNamespace(entry_id="first"))
        assert not path.exists()

    asyncio.run(run())


def test_the_history_sensors_refresh_at_midnight(tmp_path, monkeypatch):
    """The calendar moves on even when the charger never answers."""
    from homeassistant.helpers import event as ha_event

    captured = {}

    def fake_track(hass, action, **kwargs):
        captured["action"] = action
        captured["kwargs"] = kwargs
        return lambda: captured.setdefault("unsub", True)

    monkeypatch.setattr(ha_event, "async_track_time_change", fake_track)

    async def run():
        hass, coordinator = await setup(tmp_path)
        entry = SimpleNamespace(entry_id="first", async_on_unload=lambda fn: None)
        calls = []
        coordinator.async_update_listeners = lambda: calls.append(1)

        integration._async_register_midnight_refresh(hass, entry, coordinator)
        assert captured["kwargs"] == {"hour": 0, "minute": 0, "second": 30}
        captured["action"](None)
        assert calls == [1]

    asyncio.run(run())


def test_a_flush_cancels_the_pending_write_and_keeps_dirty_on_failure(tmp_path):
    """The bug: a scheduled store write survived the unload and recreated the file."""

    async def run():
        hass, coordinator = await setup(tmp_path)
        history = coordinator._history
        history.enabled = True
        history._hass = hass  # the fixture builds the history without one

        history._schedule_save()
        assert history._save_unsub is not None, "a write must be scheduled"
        await history.async_flush()
        assert history._save_unsub is None and not history._dirty

        # A failed write must not pretend the data is safe, and must not kill the
        # timer or the unload path: keep the data and retry.
        history._dirty = True
        history._store.async_save = AsyncMock(side_effect=OSError("disk full"))
        await history.async_flush()
        assert history._dirty is True
        assert history._save_unsub is not None, "a failed write has to be retried"

    asyncio.run(run())


def test_removing_the_entry_uses_its_own_store(tmp_path):
    """async_remove on a look-alike Store cannot cancel the real one's writes."""

    async def run():
        hass, coordinator = await setup(tmp_path)
        store = coordinator._history._store
        store.async_remove = AsyncMock()
        hass.data["history_stores"] = {"first": store}

        await integration.async_remove_entry(hass, SimpleNamespace(entry_id="first"))
        store.async_remove.assert_awaited_once()
        assert "first" not in hass.data["history_stores"]

    asyncio.run(run())


def test_a_removed_store_stays_removed_even_after_a_pending_write(tmp_path):
    """Reproduction of the review: the file must not come back after the entry is gone."""

    async def run():
        from custom_components.ems_home.history import (
            HISTORY_MINOR_VERSION,
            HISTORY_VERSION,
            HistoryStore,
        )

        hass = HomeAssistant(str(tmp_path))
        hass.http = SimpleNamespace()
        store = HistoryStore(
            hass, HISTORY_VERSION, history_key("gone"),
            minor_version=HISTORY_MINOR_VERSION,
        )
        history = ChargingHistory(store, hass, enabled=True)
        await history.async_load()
        history.sessions.append(record("late"))
        history._schedule_save()

        hass.data["history_stores"] = {"gone": store}
        await history.async_flush()  # what unload does
        await integration.async_remove_entry(hass, SimpleNamespace(entry_id="gone"))

        path = Path(store.path)
        assert not path.exists()
        await asyncio.sleep(0.1)  # the debounce would fire here
        assert not path.exists(), "the scheduled write recreated a removed store"

    asyncio.run(run())


def _old_export(tmp_path) -> Path:
    folder = tmp_path / "ems_home"
    folder.mkdir(exist_ok=True)
    path = folder / "history-20260101-120000.csv"
    path.write_text("started_at\n", encoding="utf-8")
    stale = datetime.now(timezone.utc) - timedelta(days=3)
    os.utime(path, (stale.timestamp(), stale.timestamp()))
    return path


def test_cleanup_service_reports_before_it_deletes(tmp_path):
    """The folder is invisible to the MCP file tools, so this service is the eyes."""

    async def run():
        hass, _ = await setup(tmp_path)
        path = _old_export(tmp_path)
        result = await call(hass, "cleanup_exports")
        assert result["applied"] is False
        assert result["removed"] == 1 and result["files"] == 1
        assert result["path"].endswith("ems_home")
        assert path.exists(), "a dry run must not delete anything"

    asyncio.run(run())


def test_cleanup_service_deletes_when_applied(tmp_path):
    async def run():
        hass, _ = await setup(tmp_path)
        path = _old_export(tmp_path)
        result = await call(hass, "cleanup_exports", apply=True, keep_hours=24)
        assert result["applied"] is True and result["removed"] == 1
        assert result["files"] == 0 and result["bytes"] == 0
        assert not path.exists()

    asyncio.run(run())
