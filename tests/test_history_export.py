"""The download ticket and its cleanup rules."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from custom_components.ems_home import export
from custom_components.ems_home.export import (
    EXPORT_TTL,
    MAX_DOWNLOADS,
    ExportRegistry,
    ExportTicket,
    _delete_files,
    _download_headers,
    _ident,
)


def ticket(tmp_path, **overrides) -> ExportTicket:
    """A fresh, valid ticket pointing at a real file."""
    path = tmp_path / "history-20260101-120000.csv"
    path.write_text("started_at\n", encoding="utf-8")
    now = overrides.pop("now", datetime.now(timezone.utc))
    export_id = overrides.pop("export_id", "abc")
    entry_ids = frozenset(overrides.pop("entry_ids", {"first"}))
    return ExportTicket(
        export_id=export_id,
        path=path,
        file_format="csv",
        entry_ids=entry_ids,
        rows=1,
        created_at=now,
        expires_at=now + EXPORT_TTL,
        dir_ident=_ident(path.parent),
        file_ident=_ident(path),
        **overrides,
    )


def test_an_unknown_id_is_reported_as_missing():
    assert ExportRegistry().claim("nope") == (None, "missing")


def test_an_expired_ticket_is_dropped_and_reported(tmp_path):
    registry = ExportRegistry()
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    registry.add(ticket(tmp_path, now=old))
    assert registry.claim("abc") == (None, "expired")
    assert len(registry) == 0


def test_a_ticket_has_a_small_download_budget(tmp_path):
    registry = ExportRegistry()
    registry.add(ticket(tmp_path))
    for _ in range(MAX_DOWNLOADS):
        claimed, reason = registry.claim("abc")
        assert claimed is not None and reason == "ok"
    assert registry.claim("abc") == (None, "spent")


def test_a_deleted_file_is_reported_as_missing(tmp_path):
    registry = ExportRegistry()
    entry = ticket(tmp_path)
    registry.add(entry)
    entry.path.unlink()
    assert registry.claim("abc") == (None, "missing")
    assert len(registry) == 0


def test_unloading_an_entry_revokes_its_tickets(tmp_path):
    registry = ExportRegistry()
    registry.add(ticket(tmp_path))
    registry.add(ticket(tmp_path, export_id="def", entry_ids={"second"}))
    registry.add(ticket(tmp_path, export_id="ghi", entry_ids={"first", "second"}))
    registry.drop_entry("first")
    assert registry.get("abc") is None
    assert registry.get("ghi") is None, "a combined export must not survive either"
    assert registry.get("def") is not None


def test_cleanup_only_removes_our_own_old_files(tmp_path, monkeypatch):
    old = tmp_path / "history-20260101-120000.csv"
    fresh = tmp_path / "history-20260101-120000.json"
    foreign = tmp_path / "backup-20260101-120000.csv"
    other_suffix = tmp_path / "history-20260101-120000.txt"
    for path in (old, fresh, foreign, other_suffix):
        path.write_text("x", encoding="utf-8")

    stale = datetime.now(timezone.utc) - timedelta(hours=48)
    fresh_time = datetime.now(timezone.utc) - timedelta(hours=1)
    for path in (old, foreign):
        os.utime(path, (stale.timestamp(), stale.timestamp()))
    for path in (fresh, other_suffix):
        os.utime(path, (fresh_time.timestamp(), fresh_time.timestamp()))

    assert _delete_files(tmp_path, timedelta(hours=24)) == 1
    assert not old.exists()
    assert fresh.exists() and foreign.exists() and other_suffix.exists()


def test_the_download_headers_never_leak_a_vehicle_name(tmp_path):
    headers = _download_headers(ticket(tmp_path))
    assert headers["Content-Disposition"].startswith('attachment; filename="ems-home-history-')
    assert "Seat" not in headers["Content-Disposition"]
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"


def test_the_view_streams_the_file_and_then_refuses(tmp_path):
    """End to end through aiohttp: headers, body, then 410 on the third try."""
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    from homeassistant.core import HomeAssistant

    from custom_components.ems_home.export import HistoryExportView, registry

    async def run():
        hass = HomeAssistant(str(tmp_path))
        entry = ticket(tmp_path)
        entry.path.write_text("started_at;energy_kwh\n2026-01-01;4,2\n", encoding="utf-8")
        registry(hass).add(entry)

        view = HistoryExportView(hass)

        async def handler(request):
            return await view.get(request, request.match_info["export_id"])

        app = web.Application()
        app.router.add_get("/api/ems_home/export/{export_id}", handler)
        async with TestClient(TestServer(app)) as client:
            first = await client.get("/api/ems_home/export/abc")
            assert first.status == 200
            assert first.headers["Content-Disposition"].startswith("attachment;")
            assert first.headers["Cache-Control"] == "no-store"
            assert "energy_kwh" in await first.text()
            for _ in range(MAX_DOWNLOADS):
                await client.get("/api/ems_home/export/abc")
            refused = await client.get("/api/ems_home/export/abc")
            assert refused.status == 410
            unknown = await client.get("/api/ems_home/export/does-not-exist")
            assert unknown.status == 404

    import asyncio

    asyncio.run(run())


def test_the_button_writes_a_file_and_announces_it(tmp_path):
    """The button is the path without YAML: press, get a notification with a link."""
    import asyncio
    from types import SimpleNamespace

    from homeassistant.exceptions import HomeAssistantError

    from custom_components.ems_home.button import EMSHistoryExportButton
    from tests.test_history_services import record, setup

    async def run():
        hass, coordinator = await setup(tmp_path)
        pressed = []

        async def _create(call):
            pressed.append(call.data)

        hass.services.async_register("persistent_notification", "create", _create)
        entry = SimpleNamespace(entry_id="first", title="eMS Home")
        button = EMSHistoryExportButton(coordinator, entry)

        await button.async_press()
        assert pressed, "no notification was created"
        assert "authSig=" in pressed[0]["message"]
        assert pressed[0]["notification_id"] == "ems_home_export_first"

        # An empty history is refused instead of writing an empty file.
        coordinator._history.sessions.clear()
        try:
            await button.async_press()
        except HomeAssistantError as exc:
            assert "Ladevorg" in str(exc) or "charging sessions" in str(exc)
        else:  # pragma: no cover - the assertion below explains the failure
            raise AssertionError("an empty history must not produce an export")

        assert record  # keep the imported fixture used

    asyncio.run(run())


def test_a_symlink_is_never_served(tmp_path):
    """A file that was replaced by a symlink must not leak its target."""
    import asyncio

    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    from homeassistant.core import HomeAssistant

    from custom_components.ems_home.export import HistoryExportView, registry

    async def run():
        hass = HomeAssistant(str(tmp_path))
        entry = ticket(tmp_path)
        secret = tmp_path / "outside.txt"
        secret.write_text("do not serve", encoding="utf-8")
        entry.path.unlink()
        entry.path.symlink_to(secret)
        registry(hass).add(entry)

        view = HistoryExportView(hass)

        async def handler(request):
            return await view.get(request, request.match_info["export_id"])

        app = web.Application()
        app.router.add_get("/api/ems_home/export/{export_id}", handler)
        async with TestClient(TestServer(app)) as client:
            response = await client.get("/api/ems_home/export/abc")
            assert response.status == 404
            assert "do not serve" not in await response.text()

    asyncio.run(run())


def test_the_sweep_refuses_a_symlinked_directory(tmp_path):
    inside = tmp_path / "exports"
    inside.mkdir()
    victim = inside / "history-20200101-000000.csv"
    victim.write_text("x", encoding="utf-8")
    os.utime(victim, (0, 0))

    link = tmp_path / "link"
    link.symlink_to(inside)

    assert _delete_files(link, timedelta(hours=24)) == 0
    assert victim.exists(), "a symlinked directory must never be swept"


def test_an_oversized_export_is_refused_without_leaving_a_file(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from homeassistant.core import HomeAssistant

    from custom_components.ems_home.const import DATA_COORDINATOR, DOMAIN
    from custom_components.ems_home.export import async_create_export

    async def run():
        hass = HomeAssistant(str(tmp_path))
        hass.http = SimpleNamespace()
        hass.data["http.auth"] = "test-refresh-token"
        coordinator = object()
        hass.data[DOMAIN] = {"first": {DATA_COORDINATOR: coordinator}}
        from tests.test_history_services import record

        sessions = [record(str(n)) for n in range(30)]

        monkeypatch.setattr(export, "MAX_SESSIONS", 10)
        with pytest.raises(ValueError, match="export limit"):
            await async_create_export(hass, [coordinator], sessions, "csv", {"first"})

        monkeypatch.setattr(export, "MAX_SESSIONS", 10_000)
        monkeypatch.setattr(export, "MAX_BYTES", 10)
        with pytest.raises(ValueError, match="MiB"):
            await async_create_export(hass, [coordinator], sessions, "csv", {"first"})

        leftovers = list((tmp_path / "ems_home").glob("history-*")) if (tmp_path / "ems_home").exists() else []
        assert leftovers == [], "a refused export must not leave a file behind"

    asyncio.run(run())


def test_the_archive_warning_uses_half_open_months():
    from datetime import date

    from custom_components.ems_home.history_services import _range_months

    assert _range_months({"start": date(2026, 1, 1), "end": date(2026, 1, 31)}) == {"2026-01"}
    # A date as end includes that whole day; a datetime is half-open.
    assert _range_months({"start": date(2026, 1, 1), "end": date(2026, 2, 1)}) == {
        "2026-01",
        "2026-02",
    }
    assert _range_months(
        {"start": date(2026, 1, 1), "end": datetime(2026, 2, 1, tzinfo=timezone.utc)}
    ) == {"2026-01"}
    assert _range_months(
        {"start": date(2026, 1, 31), "end": datetime(2026, 3, 1, tzinfo=timezone.utc)}
    ) == {"2026-01", "2026-02"}


def test_a_swapped_directory_is_never_served(tmp_path):
    """Replacing the export directory with a symlink must not serve a foreign file."""
    real = tmp_path / "ems_home"
    real.mkdir()
    entry = ticket(real)
    moved = tmp_path / "moved"
    real.rename(moved)
    real.symlink_to(moved)

    registry = ExportRegistry()
    registry.add(entry)
    assert registry.claim("abc") == (None, "missing")
    assert entry.path.exists(), "the file itself is fine, only the path is gone"


def test_the_open_refuses_a_directory_that_was_swapped_after_the_claim(tmp_path):
    """The claim checks inodes; the open uses a directory handle so the swap loses."""
    real = tmp_path / "ems_home"
    real.mkdir()
    entry = ticket(real)
    identity = entry.file_ident

    moved = tmp_path / "moved"
    real.rename(moved)
    real.symlink_to(moved)
    (moved / entry.path.name).write_text("foreign", encoding="utf-8")

    with pytest.raises(OSError):
        export._open_export(entry.path, identity)


def test_the_sweep_never_unlinks_a_replaced_file(tmp_path):
    """A file swapped for a symlink (or another file) is not ours to delete."""
    path = tmp_path / "history-20200101-000000.csv"
    path.write_text("x", encoding="utf-8")
    identity = _ident(path)

    path.unlink()
    victim = tmp_path / "victim.csv"
    victim.write_text("do not delete", encoding="utf-8")
    path.symlink_to(victim)

    assert export._unlink_export(tmp_path, path, identity) is False
    assert victim.exists()

    # A regular file with the recorded inode is deleted as expected.
    path.unlink()
    path.write_text("ours", encoding="utf-8")
    assert export._unlink_export(tmp_path, path, _ident(path)) is True
    assert not path.exists()


def test_the_button_leaves_nothing_behind_when_every_record_is_broken(tmp_path):
    import asyncio
    from types import SimpleNamespace

    from homeassistant.exceptions import HomeAssistantError

    from custom_components.ems_home.button import EMSHistoryExportButton
    from tests.test_history_services import record, setup

    async def run():
        broken = record("broken")
        broken.pop("energy_wh")
        hass, coordinator = await setup(tmp_path, [broken])
        hass.services.async_register("persistent_notification", "create", lambda call: None)
        button = EMSHistoryExportButton(coordinator, SimpleNamespace(entry_id="first", title="eMS Home"))

        try:
            await button.async_press()
        except HomeAssistantError:
            pass
        else:  # pragma: no cover
            raise AssertionError("an entirely broken history must not be announced")

        directory = tmp_path / "ems_home"
        assert not directory.exists() or not list(directory.glob("history-*")), "no file may stay"
        assert not export.registry(hass)._tickets, "no ticket may stay"

    asyncio.run(run())


def test_the_button_reports_skipped_records(tmp_path):
    """One good and one broken record: the file has one row, the note says so."""
    import asyncio
    from types import SimpleNamespace

    from custom_components.ems_home.button import EMSHistoryExportButton
    from tests.test_history_services import record, setup

    async def run():
        broken = record("broken")
        broken.pop("grid_wh")
        hass, coordinator = await setup(tmp_path, [record("good"), broken])
        notes = []

        async def _create(call):
            notes.append(call.data)

        hass.services.async_register("persistent_notification", "create", _create)
        button = EMSHistoryExportButton(coordinator, SimpleNamespace(entry_id="first", title="eMS Home"))

        await button.async_press()
        assert notes, "no notification was created"
        message = notes[0]["message"]
        assert "1 charging sessions" in message or "1 Ladevorgänge" in message
        assert "Skipped: 1" in message or "Übersprungen: 1" in message

    asyncio.run(run())


def _aged_files(tmp_path, count, *, minutes, size=2):
    """Our own export files with a given age, oldest name first."""
    paths = []
    stamp = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    for index in range(count):
        path = tmp_path / f"history-20260101-12{index:04d}.csv"
        path.write_bytes(b"x" * size)
        os.utime(path, (stamp.timestamp(), stamp.timestamp()))
        stamp += timedelta(seconds=30)
        paths.append(path)
    return paths


def test_the_folder_keeps_only_the_newest_files(tmp_path, monkeypatch):
    """Age alone does not bound the folder: a loop of exports fills it within a day."""
    import custom_components.ems_home.export as export

    monkeypatch.setattr(export, "MAX_EXPORT_FILES", 5)
    paths = _aged_files(tmp_path, 12, minutes=30)

    assert export._delete_files(tmp_path, timedelta(hours=24)) == 7
    rest = sorted(p.name for p in tmp_path.iterdir())
    assert len(rest) == 5
    assert all(old.name not in rest for old in paths[:7])   # the oldest went first
    assert all(new.name in rest for new in paths[7:])


def test_the_folder_stays_inside_its_byte_budget(tmp_path, monkeypatch):
    import custom_components.ems_home.export as export

    monkeypatch.setattr(export, "MAX_EXPORT_BYTES", 10)
    paths = _aged_files(tmp_path, 6, minutes=30, size=4)

    export._delete_files(tmp_path, timedelta(hours=24))
    rest = list(tmp_path.iterdir())
    assert sum(p.stat().st_size for p in rest) <= 10
    assert len(rest) < len(paths)


def test_a_fresh_file_survives_the_budget(tmp_path, monkeypatch):
    """A file that may belong to a running download is never removed by the budget."""
    import custom_components.ems_home.export as export

    monkeypatch.setattr(export, "MAX_EXPORT_FILES", 1)
    paths = _aged_files(tmp_path, 4, minutes=1)

    assert export._delete_files(tmp_path, timedelta(hours=24)) == 0
    assert all(path.exists() for path in paths)


def test_even_keep_zero_never_deletes_a_file_that_is_still_fresh(tmp_path):
    """A download can be in flight; keep_hours=0 must not cut it off."""
    fresh = tmp_path / "history-20260101-120000.csv"
    older = tmp_path / "history-20260101-110000.csv"
    for path in (fresh, older):
        path.write_text("x", encoding="utf-8")
    stamp = datetime.now(timezone.utc) - timedelta(minutes=20)
    os.utime(older, (stamp.timestamp(), stamp.timestamp()))

    assert _delete_files(tmp_path, timedelta(0)) == 1
    assert fresh.exists() and not older.exists()
