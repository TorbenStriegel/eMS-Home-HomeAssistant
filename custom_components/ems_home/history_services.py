"""Response services for querying, deleting and privately exporting history."""

from __future__ import annotations

from copy import deepcopy
import csv
from datetime import date, datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .aggregate import merge_archives, period_bounds, summarise
from .const import DATA_COORDINATOR, DOMAIN
from .export import async_cleanup, async_create_export
from .history import parse_utc

_LOGGER = logging.getLogger(__name__)
HISTORY_SERVICES = (
    "get_history",
    "delete_session",
    "export_history",
    "update_session",
    "cleanup_exports",
)
CSV_COLUMNS = (
    "started_at",
    "ended_at",
    "duration_min",
    "energy_kwh",
    "energy_grid_kwh",
    "energy_pv_kwh",
    "cost",
    "saved",
    "mode",
    "vehicle",
    "end_reason",
    "flags",
    "session_id",
)


def _local_bound(value, *, end=False):
    """Dates include the entire end day; datetime bounds are half-open."""
    if isinstance(value, str):
        try:
            value = (
                date.fromisoformat(value)
                if len(value) == 10
                else datetime.fromisoformat(value)
            )
        except ValueError as exc:
            raise vol.Invalid("Expected an ISO date or datetime") from exc
    if isinstance(value, datetime):
        bound = value
    elif isinstance(value, date):
        bound = datetime.combine(value, datetime.min.time())
        if end:
            bound += timedelta(days=1)
    else:
        raise vol.Invalid("Expected an ISO date or datetime")
    if bound.tzinfo is None:
        bound = bound.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return dt_util.as_utc(bound)


def _date_value(value):
    _local_bound(value)
    return value


def _validate_range(data):
    if "start" in data and "end" in data:
        if _local_bound(data["start"]) >= _local_bound(data["end"], end=True):
            raise vol.Invalid("start must be before end")
    return data


_RANGE_FIELDS = {
    vol.Optional("entry_id"): str,
    vol.Optional("start"): _date_value,
    vol.Optional("end"): _date_value,
}
GET_HISTORY_SCHEMA = vol.All(
    vol.Schema(
        {
            **_RANGE_FIELDS,
            vol.Optional("vehicle"): str,
            vol.Optional("months", default=12): vol.All(int, vol.Range(min=6, max=24)),
            # "day" gives short windows (a week, a month) instead of twelve months.
            vol.Optional("resolution", default="month"): vol.In(("month", "day")),
            vol.Optional("days", default=30): vol.All(int, vol.Range(min=1, max=92)),
            vol.Optional("limit", default=20): vol.All(int, vol.Range(min=1, max=200)),
            vol.Optional("offset", default=0): vol.All(int, vol.Range(min=0)),
        }
    ),
    _validate_range,
)
DELETE_SESSION_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("session_id"): vol.All(str, vol.Length(min=1)),
        vol.Required("confirm"): vol.All(bool, vol.Equal(True)),
    }
)
EXPORT_HISTORY_SCHEMA = vol.All(
    vol.Schema(
        {
            **_RANGE_FIELDS,
            vol.Required("format"): vol.In(("csv", "json")),
        }
    ),
    _validate_range,
)
CLEANUP_EXPORTS_SCHEMA = vol.Schema(
    {
        # Off by default: a call without apply reports what the sweep would remove.
        vol.Optional("apply", default=False): vol.Coerce(bool),
        vol.Optional("keep_hours", default=24): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=24 * 365)
        ),
    }
)
UPDATE_SESSION_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("session_id"): vol.All(str, vol.Length(min=1)),
        # An empty vehicle name clears it; a price is re-applied to the stored energy.
        vol.Optional("vehicle"): vol.Any(None, str),
        vol.Optional("grid_price"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=10))
        ),
        vol.Optional("pv_price"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=10))
        ),
        vol.Optional("note"): vol.Any(None, vol.All(str, vol.Length(max=200))),
    }
)

UPDATABLE_FIELDS = ("vehicle", "grid_price", "pv_price", "note")


def _recost(session: dict[str, Any]) -> dict[str, Any]:
    """Recompute cost and saving from the stored energy after a tariff correction.

    Only a corrected price triggers this: unchanged prices keep whatever the device
    reported at the time, so a later recalculation cannot rewrite history silently.
    """
    values = (
        session.get("grid_price"), session.get("pv_price"),
        session.get("energy_wh"), session.get("grid_wh"),
    )
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool)
               for value in values):
        return {}
    grid_price, pv_price, energy, grid = (float(value) for value in values)  # type: ignore[arg-type]
    pv = max(0.0, energy - grid)
    return {
        "cost": round(grid / 1000 * grid_price + pv / 1000 * pv_price, 3),
        # Identical to the recording path: saving is the avoided grid price minus the
        # PV tariff, never the full grid price.
        "saved": round(pv / 1000 * max(grid_price - pv_price, 0), 3),
    }


def _filtered(sessions, data):
    start = _local_bound(data["start"]) if "start" in data else None
    end = _local_bound(data["end"], end=True) if "end" in data else None
    result = []
    for session in sessions:
        timestamp = parse_utc(session.get("started_at"))
        if (start is not None or end is not None) and timestamp is None:
            continue
        if start is not None and timestamp < start:
            continue
        if end is not None and timestamp >= end:
            continue
        if "vehicle" in data and session.get("vehicle") != data["vehicle"]:
            continue
        result.append(session)
    # Compare instants, not ISO strings with potentially different offsets.
    return sorted(
        result,
        key=lambda s: (
            parse_utc(s.get("started_at")) or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )


def _bucket(key, totals):
    """One chart bucket: energy split where known, otherwise only the total."""
    return {
        "key": key,
        "sessions": totals["sessions"],
        "energy_kwh": totals["energy_kwh"],
        "energy_grid_kwh": totals["energy_grid_kwh"],
        "energy_pv_kwh": totals["energy_pv_kwh"],
        "cost": totals["cost"],
        "saved": totals["saved"],
    }


def _months(sessions, archives=(), count=12):
    start, _ = period_bounds("month", dt_util.now())
    archive = merge_archives(archives)
    buckets = []
    for _ in range(count):
        lower, upper = period_bounds("month", start)
        totals = summarise(sessions, lower, upper, archive=archive)
        buckets.append({"month": lower.strftime("%Y-%m"), **_bucket(lower.strftime("%Y-%m"), totals)})
        start = (start - timedelta(days=1)).replace(day=1)
    return list(reversed(buckets))


def _days(sessions, archives=(), count=30):
    """Daily buckets for the last `count` local days, oldest first."""
    today = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
    archive = merge_archives(archives)
    buckets = []
    for offset in range(count - 1, -1, -1):
        lower = today - timedelta(days=offset)
        totals = summarise(sessions, lower, lower + timedelta(days=1), archive=archive)
        buckets.append({"day": lower.strftime("%Y-%m-%d"), **_bucket(lower.strftime("%Y-%m-%d"), totals)})
    return buckets


#: A CSV row needs these to say anything true about a session.
SESSION_NUMBERS = ("duration_s", "energy_wh", "grid_wh")


def _exportable(sessions):
    """Split into records a row can be built from and records that would raise.

    The history store may hold a half written record (older version, interrupted save);
    one of them must not turn an export of two hundred good sessions into an error.
    """
    valid, skipped = [], 0
    for session in sessions:
        identifier = session.get("id") if isinstance(session, dict) else None
        ok = (
            isinstance(identifier, str) and bool(identifier)
        ) and all(
            isinstance(session.get(key), (int, float))
            and not isinstance(session.get(key), bool)
            for key in SESSION_NUMBERS
        )
        if ok:
            valid.append(session)
        else:
            skipped += 1
    return valid, skipped


def _flags_text(value):
    """A corrupt flags field must not cost the session its row."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ";".join(str(flag) for flag in value if flag is not None)
    return str(value)


def _csv_row(session):
    row = {
        **session,
        "duration_min": round(session["duration_s"] / 60, 1),
        "energy_kwh": session["energy_wh"] / 1000,
        "energy_grid_kwh": session["grid_wh"] / 1000,
        "energy_pv_kwh": (session["energy_wh"] - session["grid_wh"]) / 1000,
        "mode": session.get("mode_end"),
        "flags": _flags_text(session.get("flags")),
        "session_id": session["id"],
    }
    # Vehicle names are external input; do not execute them as spreadsheet formulas.
    return {
        key: (
            "'" + value
            if isinstance(value, str)
            and value.startswith(("=", "+", "-", "@", "\t", "\r", "\n"))
            else value
        )
        for key in CSV_COLUMNS
        if (value := row.get(key)) is not None
    }


def _write_export(directory, file_format, sessions, now):
    """All filesystem and serialization work runs in the executor, never in www."""
    directory = Path(directory)
    if directory.is_symlink():
        raise OSError("The history export directory must not be a symbolic link")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    while True:
        path = directory / f"history-{now:%Y%m%d-%H%M%S}.{file_format}"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            break
        except FileExistsError:
            # Keep the documented filename shape without overwriting another export.
            now += timedelta(seconds=1)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            if file_format == "json":
                json.dump(sessions, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            else:
                writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                writer.writerows(_csv_row(session) for session in sessions)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return str(path)


def _entry_ids(hass: HomeAssistant, coordinators) -> set[str]:
    """Every config entry whose data ends up in the export.

    A combined export must die when any of them unloads, not only the first.
    """
    wanted = {id(coordinator) for coordinator in coordinators}
    return {
        entry_id
        for entry_id, data in hass.data.get(DOMAIN, {}).items()
        if isinstance(data, dict) and id(data.get(DATA_COORDINATOR)) in wanted
    }


def _archive_months(coordinators) -> set[str]:
    """Months that only survive as totals, e.g. {"2026-10"}."""
    months: set[str] = set()
    for coordinator in coordinators:
        history = coordinator._history
        if history is not None and history.enabled and getattr(history, "archive", None):
            months.update(history.archive)
    return months


def _range_months(data) -> set[str]:
    """The local calendar months a start/end filter touches.

    ``start``/``end`` arrive as date, datetime or ISO string depending on how the
    caller filled the form, so normalise through the same helper the filter uses.
    """
    start = data.get("start")
    if not start:
        return set()
    # Whole days: a filter from 31 December 23:00 to 1 January 12:00 touches both months.
    first = dt_util.as_local(_local_bound(start)).date()
    end = data.get("end")
    # end is exclusive: 2026-02-01 already belongs to February, so step back a moment.
    last = (
        (dt_util.as_local(_local_bound(end, end=True)) - timedelta(microseconds=1)).date()
        if end
        else dt_util.now().date()
    )
    months: set[str] = set()
    cursor = first.replace(day=1)
    while cursor <= last:
        months.add(f"{cursor:%Y-%m}")
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months


@callback
def async_register_history_services(hass: HomeAssistant) -> None:
    """Register once; handlers resolve currently loaded entries on every call."""

    def targets(call):
        entries = hass.data.get(DOMAIN, {})
        wanted = call.data.get("entry_id")
        if wanted:
            chosen = entries.get(wanted)
            if chosen is None or DATA_COORDINATOR not in chosen:
                _LOGGER.warning("Unknown entry_id %s", wanted)
                return []
            return [chosen[DATA_COORDINATOR]]
        return [
            entry[DATA_COORDINATOR]
            for entry in entries.values()
            if DATA_COORDINATOR in entry
        ]

    async def cleanup_exports(call: ServiceCall):
        # The export folder is outside every MCP file sandbox, so this service is the
        # way to see and clean it from the outside.
        directory = Path(hass.config.path(DOMAIN))
        hours = call.data["keep_hours"]
        result = await async_cleanup(
            hass,
            directory,
            keep=timedelta(hours=hours) if hours else timedelta(0),
            dry_run=not call.data["apply"],
        )
        return {
            "path": str(directory),
            "applied": bool(call.data["apply"]),
            "keep_hours": hours,
            **result,
        }

    def sessions_for(coordinators):
        return [
            session
            for coordinator in coordinators
            if (history := coordinator._history) is not None and history.enabled
            for session in history.sessions
        ]

    async def get_history(call: ServiceCall):
        coordinators = targets(call)
        sessions = sessions_for(coordinators)
        archives = [c._history.archive for c in coordinators
                    if c._history is not None and c._history.enabled]
        filtered = _filtered(sessions, call.data)
        limit, offset = call.data["limit"], call.data["offset"]
        months = _months(sessions, archives, call.data["months"])
        return {
            "sessions": deepcopy(filtered[offset : offset + limit]),
            "count": len(filtered),
            "offset": offset,
            "limit": limit,
            "months": months,
            "buckets": months
            if call.data["resolution"] == "month"
            else _days(sessions, archives, call.data["days"]),
        }

    async def delete_session(call: ServiceCall):
        for coordinator in targets(call):
            history = coordinator._history
            if history is not None and history.delete(call.data["session_id"]):
                # Period caches key on length and last_write_at; both change here.
                coordinator.async_update_listeners()
                await history.async_flush()
                return {"deleted": True}
        return {"deleted": False}

    async def update_session(call: ServiceCall):
        fields = {key: call.data[key] for key in UPDATABLE_FIELDS if key in call.data}
        if not fields:
            return {"updated": False}
        if "vehicle" in fields:
            fields["vehicle"] = str(fields["vehicle"] or "").strip() or None
        for coordinator in targets(call):
            history = coordinator._history
            if history is None or not history.enabled:
                continue
            for session in history.sessions:
                if session.get("id") != call.data["session_id"]:
                    continue
                merged = {**session, **fields}
                if ("grid_price" in fields and fields["grid_price"] is None) or (
                    "pv_price" in fields and fields["pv_price"] is None
                ):
                    # A cleared tariff cannot price the charge any more. Keeping the old
                    # amount would show money that no longer follows any rate.
                    merged["cost"] = None
                    merged["saved"] = None
                elif "grid_price" in fields or "pv_price" in fields:
                    merged.update(_recost(merged))
                merged["edited_at"] = dt_util.utcnow().isoformat()
                if not history.upsert(merged):
                    # Archived months keep only totals and cannot be edited.
                    return {"updated": False}
                # Period caches key on last_write_at, so persist before notifying.
                await history.async_flush()
                coordinator.async_update_listeners()
                return {"updated": True, "session": deepcopy(merged)}
        return {"updated": False}

    async def export_history(call: ServiceCall):
        coordinators = targets(call)
        if not coordinators:
            return {}
        sessions = deepcopy(_filtered(sessions_for(coordinators), call.data))
        try:
            ticket, url = await async_create_export(
                hass,
                coordinators,
                sessions,
                call.data["format"],
                _entry_ids(hass, coordinators),
            )
        except (OSError, ValueError) as exc:
            raise ServiceValidationError(
                f"Could not export charging history: {exc}"
            ) from exc
        result = {
            "path": str(ticket.path),
            "url": url,
            "expires_at": ticket.expires_at.isoformat(),
            "rows": ticket.rows,
        }
        warnings: list[str] = []
        if call.data.get("start"):
            months = _range_months(call.data)
        else:
            months = _archive_months(coordinators)  # unbounded start
            if call.data.get("end"):
                # An end alone still bounds the range: only months up to it.
                last = dt_util.as_local(
                    _local_bound(call.data["end"], end=True) - timedelta(microseconds=1)
                )
                months = {month for month in months if month <= f"{last:%Y-%m}"}
        archived = months & _archive_months(coordinators)
        if archived:
            # Those months only exist as totals; no filter can bring their details back.
            warnings.append("archived_details_unavailable")
        if not sessions:
            # The file is valid (header only / empty list); say that it is empty.
            warnings.append("no_sessions_in_range")
        if ticket.skipped:
            # Say it out loud instead of silently shipping a shorter file.
            warnings.append("incomplete_records_skipped")
            result["skipped"] = ticket.skipped
        if warnings:
            result["warnings"] = warnings
        return result

    for name, handler, schema, response in (
        ("get_history", get_history, GET_HISTORY_SCHEMA, SupportsResponse.ONLY),
        (
            "delete_session",
            delete_session,
            DELETE_SESSION_SCHEMA,
            SupportsResponse.OPTIONAL,
        ),
        (
            "export_history",
            export_history,
            EXPORT_HISTORY_SCHEMA,
            SupportsResponse.ONLY,
        ),
        (
            "update_session",
            update_session,
            UPDATE_SESSION_SCHEMA,
            SupportsResponse.OPTIONAL,
        ),
        (
            "cleanup_exports",
            cleanup_exports,
            CLEANUP_EXPORTS_SCHEMA,
            SupportsResponse.ONLY,
        ),
    ):
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(
                DOMAIN, name, handler, schema=schema, supports_response=response
            )
