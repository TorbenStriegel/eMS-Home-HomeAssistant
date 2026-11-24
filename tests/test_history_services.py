"""History service contracts exercised through the real HA service registry."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import csv
from datetime import date, datetime
import json
from pathlib import Path
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
from custom_components.ems_home.history import ChargingHistory

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
            "month": "2026-11",
            "sessions": 5,
            "energy_kwh": 40,
            "cost": 10.5,
            "saved": 3.5,
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


@pytest.mark.parametrize("name", services.HISTORY_SERVICES)
def test_unknown_entry_warns_and_never_targets_other_entries(tmp_path, caplog, name):
    async def run():
        hass, coordinator = await setup(tmp_path)
        data = {"entry_id": "unknown"}
        if name == "delete_session":
            data.update(session_id="one", confirm=True)
        if name == "export_history":
            data["format"] = "csv"
        result = await call(hass, name, **data)
        if name == "get_history":
            assert (
                result["sessions"] == []
                and result["count"] == 0
                and len(result["months"]) == 12
            )
        else:
            assert result == ({"deleted": False} if name == "delete_session" else {})
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
    hass = SimpleNamespace(http=SimpleNamespace(async_register_static_paths=static_paths))

    async def run():
        await integration._async_register_card(hass)
        await integration._async_register_card(hass)

    asyncio.run(run())
    expected = [
        f"{integration.CARD_URL}?v={integration.VERSION}",
        f"{integration.STATIC_URL_PATH}/ems-home-history-cards.js?v={integration.VERSION}",
    ]
    assert [item.args[1] for item in extra.call_args_list] == expected
    assert [item.args[1] for item in resources.call_args_list] == expected
    static_paths.assert_awaited_once()
    frontend = Path(integration.__file__).with_name("frontend")
    for url in expected:
        filename = url.split("/")[-1].split("?")[0]
        assert (frontend / filename).is_file()
