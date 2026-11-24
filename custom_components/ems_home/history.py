"""Charging history: one entry per finished charge, kept in its own store.

The history store is written only when a charge ends (a few times a day at
most) and is therefore separate from the session store, which follows a running
charge every 20 s. Every entry corresponds to exactly one
``ems_home_charging_finished`` event and is identified by the cycle id that the
coordinator assigns when the charge is confirmed.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

HISTORY_VERSION = 1
HISTORY_MINOR_VERSION = 1
#: A charge ends a few times a day; the delay only merges a finish and a
#: reconciliation that happen right after each other.
HISTORY_SAVE_DELAY = 1.0

END_UNPLUGGED = "unplugged"
END_IDLE = "idle"

FLAG_GAP = "gap"
FLAG_RESTARTED = "restarted"
FLAG_MODE_CHANGED = "mode_changed"
FLAG_CLOCK_SUSPECT = "clock_suspect"

#: started_at may lie this far after the wall clock before it counts as suspect.
CLOCK_AHEAD_TOLERANCE = timedelta(minutes=10)
#: Wall-clock span may be this much shorter than the charging time.
CLOCK_SPAN_TOLERANCE_S = 60


def history_key(entry_id: str) -> str:
    """Storage key of the history file of one config entry."""
    return f"{DOMAIN}.{entry_id}.history"


class HistoryVersionError(Exception):
    """The file was written by a newer major version and must not be touched."""


class HistoryStore(Store):
    """Store for the charging history with an explicit migration policy.

    Minor versions only add optional fields: readers set defaults and unknown
    fields are passed through unchanged. A newer major version (downgrade) is
    refused, so the caller disables the history instead of overwriting the file.
    """

    def _validate_file(self) -> None:
        """Reject broken files before HA can rename them as corrupt."""
        try:
            with open(self.path, encoding="utf-8") as handle:
                envelope = json.load(handle)
        except FileNotFoundError:
            return
        if not isinstance(envelope, dict) or not isinstance(envelope.get("data"), dict):
            raise ValueError("unexpected history envelope")
        major = envelope.get("version")
        if not isinstance(major, int):
            raise ValueError("missing history version")
        if major > HISTORY_VERSION:
            raise HistoryVersionError(f"history file has major version {major}")

    async def async_load(self):
        await self.hass.async_add_executor_job(self._validate_file)
        return await super().async_load()

    async def _async_migrate_func(self, old_major_version, old_minor_version, old_data):
        if old_major_version > HISTORY_VERSION:
            raise HistoryVersionError(
                f"history file has version {old_major_version}.{old_minor_version}, "
                f"this release reads {HISTORY_VERSION}.x"
            )
        return old_data


def parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def clock_suspect(started_at: Any, ended_at: Any, duration_s: int, now: datetime) -> bool:
    """Do the wall-clock times contradict each other or the monotonic duration?"""
    start = parse_utc(started_at)
    end = parse_utc(ended_at)
    if start is None or end is None:
        return True
    if end < start:
        return True
    if start > now + CLOCK_AHEAD_TOLERANCE:
        return True
    return (end - start).total_seconds() < duration_s - CLOCK_SPAN_TOLERANCE_S


def build_record(
    *,
    cycle: dict,
    ended_at: str | None,
    energy_wh: float,
    grid_wh: float,
    seconds: float,
    grid_price: float | None,
    pv_price: float | None,
    cost: float | None,
    saved: float | None,
    mode_end: str | None,
    vehicle: str | None,
    end_reason: str,
    still_plugged: bool,
    now: datetime,
) -> dict[str, Any]:
    """One history entry, schema v1 (integers for Wh and seconds, UTC times)."""
    duration_s = int(round(seconds))
    energy = int(round(energy_wh))
    gap_s = int(round(float(cycle.get("gap_s") or 0)))
    restarts = int(cycle.get("restarts") or 0)
    mode_start = cycle.get("mode_start")
    started_at = cycle.get("started_at")

    flags: list[str] = []
    if gap_s > 0:
        flags.append(FLAG_GAP)
    if restarts > 0:
        flags.append(FLAG_RESTARTED)
    if mode_start is not None and mode_end is not None and mode_start != mode_end:
        flags.append(FLAG_MODE_CHANGED)
    if clock_suspect(started_at, ended_at, duration_s, now):
        flags.append(FLAG_CLOCK_SUSPECT)

    return {
        "id": cycle["id"],
        "wallbox_uuid": cycle.get("wallbox_uuid"),
        "started_at": started_at,
        "ended_at": ended_at,
        # A cycle restored from an older release may not know its last flow.
        "last_flow_at": cycle.get("last_flow_at") or ended_at,
        "duration_s": duration_s,
        "energy_wh": energy,
        "grid_wh": int(round(min(grid_wh, energy_wh))),
        "grid_price": grid_price,
        "pv_price": pv_price,
        "cost": cost,
        "saved": saved,
        "mode_start": mode_start,
        "mode_end": mode_end,
        "vehicle": vehicle,
        "end_reason": end_reason,
        "still_plugged": bool(still_plugged),
        "gap_s": gap_s,
        "restarts": restarts,
        "flags": flags,
        "estimated": True,
        "source": "live",
    }


class ChargingHistory:
    """In-memory view of the history file plus the rules for writing it.

    If loading fails for any reason the history stays disabled for this run and
    nothing is written, so a damaged or newer file is never overwritten.
    """

    def __init__(self, store, hass=None) -> None:
        self._store = store
        self._hass = hass
        self.enabled = False
        self.load_error: str | None = None
        self.sessions: list[dict[str, Any]] = []
        #: Top-level keys other than "sessions" (e.g. a future archive), kept as-is.
        self._other: dict[str, Any] = {}
        #: When the last write was handed to the store (UTC, ISO 8601).
        self.last_write_at: str | None = None
        #: Entries added at startup because the history store missed them.
        self.reconciled = 0
        self._dirty = False

    async def _file_exists(self) -> bool:
        path = getattr(self._store, "path", None) if self._hass is not None else None
        if not path:
            return False
        try:
            return await self._hass.async_add_executor_job(os.path.exists, path)
        except Exception:  # noqa: BLE001 - only a hint for the error message
            return False

    def _disable(self, reason: str) -> None:
        self.enabled = False
        self.load_error = reason
        self.sessions = []
        _LOGGER.warning(
            "Charging history is disabled for this run, the file is left untouched: %s",
            reason,
        )

    async def async_load(self) -> None:
        existed = await self._file_exists()
        try:
            data = await self._store.async_load()
        except Exception as exc:  # noqa: BLE001 - a broken file must not block setup
            self._disable(f"{type(exc).__name__}: {exc}")
            return
        if data is None:
            if existed:
                # Home Assistant moves an undecodable file aside and returns None;
                # starting an empty history would hide that the old one is gone.
                self._disable("the file could not be decoded")
                return
            data = {}
        sessions = data.get("sessions", []) if isinstance(data, dict) else None
        if not isinstance(sessions, list) or not all(isinstance(s, dict) for s in sessions):
            self._disable("unexpected file structure")
            return
        self._other = {k: v for k, v in data.items() if k != "sessions"}
        self.sessions = sessions
        self.load_error = None
        self.enabled = True

    def has(self, session_id: str | None) -> bool:
        return bool(session_id) and any(s.get("id") == session_id for s in self.sessions)

    def upsert(self, record: dict[str, Any]) -> bool:
        """Insert the entry or replace the one with the same id. False if disabled."""
        if not self.enabled or not record or not record.get("id"):
            return False
        for index, existing in enumerate(self.sessions):
            if existing.get("id") == record["id"]:
                # Unknown fields of the stored entry survive the replacement.
                self.sessions[index] = {**existing, **record}
                break
        else:
            self.sessions.append(dict(record))
        self._schedule_save()
        return True

    def reconcile(self, record: dict[str, Any] | None) -> bool:
        """Add a finished entry the history missed (crash between the two stores)."""
        if not self.enabled or not record or not record.get("id") or self.has(record["id"]):
            return False
        if not self.upsert(record):
            return False
        self.reconciled += 1
        _LOGGER.info(
            "Charging history: added the charge that ended at %s, it was missing after a restart",
            record.get("ended_at"),
        )
        return True

    def _data(self) -> dict[str, Any]:
        # Copied in the event loop: the store serialises in the executor.
        return {**self._other, "sessions": [dict(s) for s in self.sessions]}

    def _schedule_save(self) -> None:
        snapshot = self._data()
        self._dirty = True
        self.last_write_at = datetime.now(timezone.utc).isoformat()
        self._store.async_delay_save(lambda: snapshot, HISTORY_SAVE_DELAY)

    async def async_flush(self) -> None:
        """Write pending changes now (unload / reload)."""
        if not self.enabled or not self._dirty:
            return
        self._dirty = False
        await self._store.async_save(self._data())

    def diagnostics(self) -> dict[str, Any]:
        """Counts and state only – no vehicle names, no entries."""
        return {
            "enabled": self.enabled,
            "sessions": len(self.sessions),
            "load_error": self.load_error,
            "last_write_at": self.last_write_at,
            "reconciled": self.reconciled,
        }
