"""Charging history: one entry per finished charge, kept in its own store.

The history store is written only when a charge ends (a few times a day at
most) and is therefore separate from the session store, which follows a running
charge every 20 s. Every entry corresponds to exactly one
``ems_home_charging_finished`` event and is identified by the cycle id that the
coordinator assigns when the charge is confirmed.
"""
from __future__ import annotations

from copy import deepcopy
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .aggregate import archive_session
from .const import DOMAIN, DEFAULT_HISTORY_ENABLED, DEFAULT_HISTORY_RETENTION_MONTHS

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


def validate_archive(archive: Any) -> None:
    """Reject malformed monthly data before HA can auto-save a migration."""
    if not isinstance(archive, dict):
        raise ValueError("archive must be a mapping")
    for month, bucket in archive.items():
        if not isinstance(month, str) or len(month) != 7:
            raise ValueError("invalid archive month")
        datetime.strptime(month, "%Y-%m")
        if not isinstance(bucket, dict):
            raise ValueError("invalid archive bucket")
        for key in ("count", "energy_wh"):
            value = bucket.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"invalid archive {key}")
        # priced_energy_wh was added later: a damaged counter used to slip through and
        # made the period sensors add an int to a string.
        for key in ("grid_wh", "duration_s", "min_wh", "max_wh", "priced_sessions",
                    "saved_sessions", "priced_energy_wh"):
            value = bucket.get(key)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"invalid archive {key}")
        for key in ("cost", "saved"):
            if bucket.get(key) is not None and not isinstance(bucket[key], (int, float)):
                raise ValueError(f"invalid archive {key}")
        vehicles = bucket.get("by_vehicle", {})
        if not isinstance(vehicles, dict) or not all(isinstance(name, str) for name in vehicles):
            raise ValueError("invalid archive vehicles")
        for values in vehicles.values():
            validate_archive({month: values})


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
        sessions = envelope["data"].get("sessions", [])
        if not isinstance(sessions, list) or not all(isinstance(s, dict) for s in sessions):
            raise ValueError("unexpected history sessions")
        validate_archive(envelope["data"].get("archive", {}))

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

    def __init__(
        self, store, hass=None, *, enabled: bool = DEFAULT_HISTORY_ENABLED,
        retention_months: int = DEFAULT_HISTORY_RETENTION_MONTHS,
    ) -> None:
        self._store = store
        self._hass = hass
        self.configured_enabled = enabled
        self.retention_months = retention_months
        self.enabled = False
        self.load_error: str | None = None
        self.sessions: list[dict[str, Any]] = []
        #: Unknown top-level keys and the optional monthly archive are preserved.
        self._other: dict[str, Any] = {}
        #: When the last write was handed to the store (UTC, ISO 8601).
        self.last_write_at: str | None = None
        #: Entries added at startup because the history store missed them.
        self.reconciled = 0
        self._dirty = False
        #: Bumped on every change, so a write that overlapped one is not marked clean.
        self._revision = 0
        #: Our own debounce handle. Store.async_delay_save leaves a scheduled write
        #: behind that a plain async_save cannot cancel, which brought deleted stores
        #: back after an unload. The timer is ours, so we can cancel it.
        self._save_unsub = None
        self._save_lock = asyncio.Lock()

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
        if not self.configured_enabled:
            return
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
        try:
            validate_archive(data.get("archive", {}))
        except (ValueError, TypeError, KeyError) as exc:
            self._disable(f"unexpected archive structure: {exc}")
            return
        self._other = {k: v for k, v in data.items() if k != "sessions"}
        self.sessions = sessions
        self.load_error = None
        self.enabled = True
        if self._compaction_ok():
            self._schedule_save()

    @property
    def archive(self) -> dict[str, Any]:
        return self._other.get("archive", {})

    def has(self, session_id: str | None) -> bool:
        return bool(session_id) and (
            session_id in self._other.get("archived_session_ids", [])
            or any(s.get("id") == session_id for s in self.sessions)
        )

    def _compaction_ok(self) -> bool:
        """Run the retention and disable the history if a bucket is damaged.

        A half-merged archive is worse than none: the caller keeps the file untouched
        and the user sees a warning instead of silently wrong totals.
        """
        try:
            return self.apply_retention()
        except Exception as exc:  # noqa: BLE001 - any damaged entry
            self._disable(f"compacting the archive failed: {type(exc).__name__}: {exc}")
            return False

    def apply_retention(self, now: datetime | None = None) -> bool:
        """Compact complete local months older than the detail-retention window.

        Keep the cutoff month intact so week/month totals never need to split a
        monthly bucket. Unassignable timestamps remain detailed rather than lost.
        IDs alone survive compaction to make pending-record replay idempotent.
        """
        if not self.enabled or self.retention_months == 0:
            return False
        local_now = dt_util.as_local(now) if now is not None else dt_util.now()
        month_index = local_now.year * 12 + local_now.month - 1 - self.retention_months
        year, month = divmod(month_index, 12)
        cutoff = local_now.replace(year=year, month=month + 1, day=1,
                                   hour=0, minute=0, second=0, microsecond=0)
        kept = []
        archive = deepcopy(self.archive)
        archived_ids = list(self._other.get("archived_session_ids", []))
        known_ids = set(archived_ids)
        changed = False
        for session in self.sessions:
            started = parse_utc(session.get("started_at"))
            if started is None or dt_util.as_local(started) >= cutoff:
                kept.append(session)
                continue
            month_key = dt_util.as_local(started).strftime("%Y-%m")
            if session.get("id") not in known_ids:
                archive[month_key] = archive_session(archive.get(month_key, {}), session)
                if session.get("id"):
                    archived_ids.append(session["id"])
                    known_ids.add(session["id"])
            changed = True
        if changed:
            self.sessions = kept
            self._other["archive"] = archive
            self._other["archived_session_ids"] = archived_ids
        return changed

    def upsert(self, record: dict[str, Any]) -> bool:
        """Insert the entry or replace the one with the same id. False if disabled."""
        if not self.enabled or not record or not record.get("id"):
            return False
        if record["id"] in self._other.get("archived_session_ids", []):
            return False
        if record["id"] in self._other.get("deleted_session_ids", []):
            return False
        for index, existing in enumerate(self.sessions):
            if existing.get("id") == record["id"]:
                # Unknown fields of the stored entry survive the replacement.
                self.sessions[index] = {**existing, **record}
                break
        else:
            self.sessions.append(dict(record))
        # A damaged bucket disables the history; nothing is written then.
        self._compaction_ok()
        if not self.enabled:
            return False
        self._schedule_save()
        return True

    def delete(self, session_id: str) -> bool:
        """Delete one entry and remember it across session-store reconciliation."""
        if not self.enabled:
            return False
        for index, session in enumerate(self.sessions):
            if session.get("id") == session_id:
                self.sessions.pop(index)
                # The session store may still contain this finished pending_record.
                deleted = list(self._other.get("deleted_session_ids", []))
                if session_id not in deleted:
                    deleted.append(session_id)
                self._other["deleted_session_ids"] = deleted
                self._schedule_save()
                return True
        return False

    def reconcile(self, record: dict[str, Any] | None) -> bool:
        """Add a finished entry the history missed (crash between the two stores)."""
        if not self.enabled or not record or not record.get("id") or self.has(record["id"]):
            return False
        if record["id"] in self._other.get("deleted_session_ids", []):
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
        return deepcopy({**self._other, "sessions": self.sessions})

    def _schedule_save(self) -> None:
        """Debounce a write; a second change only moves the deadline."""
        self._dirty = True
        self._revision += 1
        self.last_write_at = datetime.now(timezone.utc).isoformat()
        if self._save_unsub is not None:
            return  # an earlier call already scheduled the same write
        if self._hass is None:
            self._store.async_delay_save(lambda: self._data(), HISTORY_SAVE_DELAY)
            return
        from homeassistant.helpers.event import async_call_later

        self._save_unsub = async_call_later(
            self._hass, HISTORY_SAVE_DELAY, self._async_save_timer
        )

    async def _async_save_timer(self, _now=None) -> None:
        self._save_unsub = None
        await self._async_write()

    async def _async_write(self) -> None:
        """Write pending changes. The dirty flag clears only after a real write."""
        async with self._save_lock:
            if not self.enabled or not self._dirty:
                return
            revision = self._revision
            snapshot = self._data()
            try:
                await self._store.async_save(snapshot)
            except Exception as exc:  # noqa: BLE001 - a full disk must not break the UI
                # Keep the data and the dirty flag: the next timer or flush retries.
                _LOGGER.warning("Could not store the charging history: %s", exc)
                self._schedule_save()
                return
            if revision == self._revision:
                self._dirty = False
            else:
                # A change landed while the file was written: write again later.
                self._schedule_save()

    async def async_flush(self) -> None:
        """Write pending changes now (unload / reload) and cancel the debounce."""
        if self._save_unsub is not None:
            self._save_unsub()
            self._save_unsub = None
        await self._async_write()

    def diagnostics(self) -> dict[str, Any]:
        """Counts and state only – no vehicle names, no entries."""
        return {
            "enabled": self.enabled,
            "sessions": len(self.sessions),
            "load_error": self.load_error,
            "last_write_at": self.last_write_at,
            "reconciled": self.reconciled,
        }
