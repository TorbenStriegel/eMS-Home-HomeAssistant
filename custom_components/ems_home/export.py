"""Downloadable exports of the charging history.

The file itself stays private in ``<config>/ems_home`` and never enters ``www``.
Home Assistant signs the download path for us (``authSig``), so the notification can
carry a plain link that works on a phone without a token in the URL. Each link is
short-lived and limited in downloads; an export that nobody fetches is removed after a
day.
"""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import DATA_COORDINATOR, DOMAIN

_LOGGER = logging.getLogger(__name__)

EXPORT_URL = "/api/ems_home/export/"
EXPORT_ROUTE = EXPORT_URL + "{export_id}"
#: Long enough for a notification to be opened, short enough to be worthless later.
EXPORT_TTL = timedelta(minutes=5)
#: Two, not one: a mobile download manager sometimes asks twice for the same file.
MAX_DOWNLOADS = 2
MAX_SESSIONS = 10_000
MAX_BYTES = 16 * 1024 * 1024
KEEP_FILES = timedelta(hours=24)
CHUNK_SIZE = 64 * 1024
#: Kept outside hass.data[DOMAIN]: that dict maps entry ids to coordinators, and a
#: second kind of value there breaks every lookup that iterates it.
DATA_EXPORTS = f"{DOMAIN}_history_exports"
DATA_VIEW = "history_export_view"

TEXTS = {
    "de": {
        "title": "Ladehistorie exportiert",
        "body": (
            "**{rows} Ladevorgänge** liegen als {format} bereit.\n\n"
            "[Jetzt herunterladen]({url})\n\n"
            "Der Link gilt bis {until} und höchstens für zwei Downloads."
        ),
        "expired": "Der Download-Link ist abgelaufen. Bitte den Export erneut starten.",
        "spent": "Dieser Download-Link wurde bereits verwendet. Bitte den Export erneut starten.",
        "missing": "Die Exportdatei ist nicht mehr vorhanden. Bitte neu exportieren.",
        "archived": (
            "Für den gewählten Zeitraum liegen nur noch Monatssummen vor. "
            "Einzelne Ladevorgänge lassen sich dafür nicht mehr exportieren."
        ),
        "nothing": "Es gibt noch keine abgeschlossenen Ladevorgänge zum Exportieren.",
    },
    "en": {
        "title": "Charging history exported",
        "body": (
            "**{rows} charging sessions** are ready as {format}.\n\n"
            "[Download now]({url})\n\n"
            "The link is valid until {until} and for at most two downloads."
        ),
        "expired": "The download link expired. Please start the export again.",
        "spent": "This download link was already used. Please start the export again.",
        "missing": "The export file is gone. Please export again.",
        "archived": (
            "Only monthly totals are left for that period. Individual sessions can no "
            "longer be exported."
        ),
        "nothing": "There are no finished charging sessions to export yet.",
    },
}


def texts(hass: HomeAssistant) -> dict[str, str]:
    """German or English, following the configured language."""
    language = (getattr(hass.config, "language", "en") or "en").lower()
    return TEXTS["de"] if language.startswith("de") else TEXTS["en"]


def notification_key(entry_id: str) -> str:
    """One notification per config entry, so a new export replaces the old one."""
    return f"ems_home_export_{entry_id}"


@dataclass(slots=True)
class ExportTicket:
    """A prepared file plus the rules under which it may be downloaded."""

    export_id: str
    path: Path
    file_format: str
    entry_ids: frozenset[str]
    rows: int
    created_at: datetime
    expires_at: datetime
    downloads: int = 0
    #: Inode of the export directory and of the file, captured when the export was
    #: written. A directory swapped for a symlink changes its inode, so the check
    #: catches it without walking the whole path.
    dir_ident: tuple[int, int] = (0, 0)
    file_ident: tuple[int, int] = (0, 0)

    @property
    def entry_id(self) -> str:
        """The entry a notification belongs to (the first of a combined export)."""
        return sorted(self.entry_ids)[0] if self.entry_ids else "all"

    @property
    def size(self) -> int:
        return self.path.stat().st_size

    def expired(self, now: datetime | None = None) -> bool:
        return (now or dt_util.utcnow()) >= self.expires_at


class ExportRegistry:
    """Tickets live in memory: a restart makes every outstanding link worthless."""

    def __init__(self) -> None:
        self._tickets: dict[str, ExportTicket] = {}

    def __len__(self) -> int:
        return len(self._tickets)

    def add(self, ticket: ExportTicket) -> None:
        self._tickets[ticket.export_id] = ticket

    def get(self, export_id: str) -> ExportTicket | None:
        return self._tickets.get(export_id)

    def claim(self, export_id: str) -> tuple[ExportTicket | None, str]:
        """Hand out the ticket once (twice, see MAX_DOWNLOADS) or explain why not."""
        ticket = self._tickets.get(export_id)
        if ticket is None:
            return None, "missing"
        if ticket.expired():
            self._tickets.pop(export_id, None)
            return None, "expired"
        if ticket.downloads >= MAX_DOWNLOADS:
            return None, "spent"
        if not _still_ours(ticket):
            self._tickets.pop(export_id, None)
            return None, "missing"
        ticket.downloads += 1
        return ticket, "ok"

    def drop_entry(self, entry_id: str) -> None:
        """Revoke every ticket that carries data of this entry, not just its own."""
        for export_id, ticket in list(self._tickets.items()):
            if entry_id in ticket.entry_ids:
                self._tickets.pop(export_id, None)

    @callback
    def prune(self) -> list[Path]:
        """Forget expired tickets and return the files that may be deleted."""
        now = dt_util.utcnow()
        dropped: list[Path] = []
        for export_id, ticket in list(self._tickets.items()):
            if ticket.expired(now):
                if _still_ours(ticket):
                    dropped.append(ticket.path)
                self._tickets.pop(export_id, None)
        return dropped


def registry(hass: HomeAssistant) -> ExportRegistry:
    """The registry of the running instance, created on first use."""
    return hass.data.setdefault(DATA_EXPORTS, ExportRegistry())


def _delete_files(directory: Path, keep: timedelta) -> int:
    """Remove only our own export files, never the history store.

    A symlinked directory is refused: the sweep must not delete files outside the
    config directory just because somebody pointed the export folder elsewhere.
    """
    removed = 0
    cutoff = dt_util.utcnow() - keep
    if directory.is_symlink():
        _LOGGER.warning("Refusing to clean a symlinked export directory: %s", directory)
        return 0
    try:
        entries = list(directory.iterdir())
    except OSError:
        return 0
    for path in entries:
        if path.is_symlink():
            continue  # whether it points inside or outside: not ours to delete
        if path.suffix not in (".csv", ".json") or not path.stem.startswith("history-"):
            continue
        try:
            if dt_util.utc_from_timestamp(path.stat().st_mtime) >= cutoff:
                continue
            path.unlink()
            removed += 1
        except OSError:  # a file in use stays until the next run
            continue
    return removed


async def async_cleanup(hass: HomeAssistant, directory: Path) -> None:
    """Drop expired tickets and files that nobody fetched."""
    dropped = registry(hass).prune()
    for path in dropped:
        await hass.async_add_executor_job(lambda p=path: p.unlink(missing_ok=True))
    await hass.async_add_executor_job(_delete_files, directory, KEEP_FILES)


async def async_create_export(
    hass: HomeAssistant,
    coordinators: list[Any],
    sessions: list[dict[str, Any]],
    file_format: str,
    entry_ids: set[str] | frozenset[str],
) -> tuple[ExportTicket, str]:
    """Write the file, register the ticket and return a signed URL.

    Raises ``ValueError`` for an oversized export: a silently truncated file would look
    like a complete one.
    """
    from .history_services import _write_export  # local: history_services imports us

    if len(sessions) > MAX_SESSIONS:
        raise ValueError(
            f"{len(sessions)} sessions exceed the export limit of {MAX_SESSIONS}"
        )
    directory = Path(hass.config.path(DOMAIN))
    path = Path(
        await hass.async_add_executor_job(
            _write_export, directory, file_format, sessions, dt_util.now()
        )
    )
    size = await hass.async_add_executor_job(lambda: path.stat().st_size)
    if size > MAX_BYTES:
        await hass.async_add_executor_job(lambda: path.unlink(missing_ok=True))
        raise ValueError(f"The export exceeds the limit of {MAX_BYTES // 1024 // 1024} MiB")

    now = dt_util.utcnow()
    # An entry can be unloaded (and even reloaded) while the file is being written; the
    # ids alone would still match after a reload, so compare the coordinators.
    current = {
        entry_id: data.get(DATA_COORDINATOR)
        for entry_id, data in hass.data.get(DOMAIN, {}).items()
        if isinstance(data, dict)
    }
    expected = {id(coordinator) for coordinator in coordinators}
    if any(
        entry_id not in current or id(current[entry_id]) not in expected
        for entry_id in entry_ids
    ):
        await hass.async_add_executor_job(lambda: path.unlink(missing_ok=True))
        raise ValueError("The config entry was unloaded during the export")

    ticket = ExportTicket(
        export_id=secrets.token_urlsafe(16),
        path=path,
        file_format=file_format,
        entry_ids=frozenset(entry_ids),
        rows=len(sessions),
        created_at=now,
        expires_at=now + EXPORT_TTL,
        dir_ident=await hass.async_add_executor_job(_ident, directory),
        file_ident=await hass.async_add_executor_job(_ident, path),
    )
    registry(hass).add(ticket)
    url = async_sign_path(hass, f"{EXPORT_URL}{ticket.export_id}", EXPORT_TTL)
    return ticket, url


async def async_announce(
    hass: HomeAssistant, ticket: ExportTicket, url: str, entry_name: str
) -> None:
    """Put the link into a notification that replaces the previous one."""
    if registry(hass).get(ticket.export_id) is None:
        # The entry was unloaded while the file was written; a link would be dead.
        _LOGGER.debug("Export was revoked before it could be announced")
        return
    text = texts(hass)
    until = dt_util.as_local(ticket.expires_at).strftime("%H:%M")
    await hass.services.async_call(
        "persistent_notification",
        "create",
        {
            "title": f"{text['title']} · {entry_name}",
            "message": text["body"].format(
                rows=ticket.rows, format=ticket.file_format.upper(), url=url, until=until
            ),
            "notification_id": notification_key(ticket.entry_id),
        },
        blocking=True,
    )


def _ident(path: Path) -> tuple[int, int]:
    """Inode of the path itself, without following a symlink."""
    info = os.stat(path, follow_symlinks=False)
    return info.st_dev, info.st_ino


def _still_ours(ticket: ExportTicket) -> bool:
    """Directory and file must still be the ones the export wrote."""
    try:
        return (
            _ident(ticket.path.parent) == ticket.dir_ident
            and _ident(ticket.path) == ticket.file_ident
        )
    except OSError:
        return False


def _open_export(path: Path) -> tuple[Any, int]:
    """Open the file without following a symlink and report its real size."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    handle = os.fdopen(descriptor, "rb")
    return handle, os.fstat(descriptor).st_size


def _download_headers(ticket: ExportTicket) -> dict[str, str]:
    """A download, not a page: no caching, no sniffing, no referrer, no vehicle name."""
    filename = f"ems-home-history-{ticket.created_at:%Y%m%d-%H%M%S}.{ticket.file_format}"
    return {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
    }


class HistoryExportView(HomeAssistantView):
    """Serve one prepared file to a signed link.

    ``requires_auth`` plus HA's own ``authSig`` handling means the request carries no
    bearer token: the signature names the path and expires. The ticket adds the rest
    (one file, a download budget, an entry that still exists).
    """

    url = EXPORT_ROUTE
    name = "api:ems_home:export"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request, export_id: str) -> web.StreamResponse:
        ticket, reason = registry(self.hass).claim(export_id)
        if ticket is None:
            message = texts(self.hass)[reason]
            if reason == "missing":
                raise web.HTTPNotFound(text=message, content_type="text/plain")
            raise web.HTTPGone(text=message, content_type="text/plain")

        # Open before the status line is sent: a file that vanished (or a symlink
        # slipped in after the export) must still become a clean 404, not a 200 that
        # breaks halfway through.
        try:
            handle, size = await self.hass.async_add_executor_job(_open_export, ticket.path)
        except OSError:
            raise web.HTTPNotFound(
                text=texts(self.hass)["missing"], content_type="text/plain"
            ) from None

        response = web.StreamResponse(
            status=200,
            headers={**_download_headers(ticket), "Content-Length": str(size)},
        )
        response.content_type = (
            "application/json" if ticket.file_format == "json" else "text/csv"
        )
        response.charset = "utf-8"
        try:
            await response.prepare(request)
            while chunk := await self.hass.async_add_executor_job(
                handle.read, CHUNK_SIZE
            ):
                await response.write(chunk)
        except (ConnectionResetError, ConnectionError):
            _LOGGER.debug("Client aborted the export download")
        finally:
            await self.hass.async_add_executor_job(handle.close)
        return response


@callback
def async_register_export_view(hass: HomeAssistant) -> None:
    """Registered once per HA run: the router survives config entry reloads."""
    if hass.data.get(DATA_VIEW):
        return
    http = getattr(hass, "http", None)  # absent in unit tests without the http component
    if http is None:
        return
    http.register_view(HistoryExportView(hass))
    hass.data[DATA_VIEW] = True
