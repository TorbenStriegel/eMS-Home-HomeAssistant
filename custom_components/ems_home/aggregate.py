"""Local-calendar summaries of finished charges, without storage or entity I/O."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Sequence

from homeassistant.util import dt as dt_util

PERIODS = ("week", "month", "year", "total")


def period_bounds(
    period: str, now_local: datetime,
) -> tuple[datetime | None, datetime | None]:
    """Return local, half-open calendar bounds; total has no bounds."""
    if period == "total":
        return None, None
    midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        start = midnight - timedelta(days=midnight.weekday())
        return start, start + timedelta(days=7)
    if period == "month":
        start = midnight.replace(day=1)
        end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
        return start, end
    if period == "year":
        start = midnight.replace(month=1, day=1)
        return start, start.replace(year=start.year + 1)
    raise ValueError(f"Unknown history period: {period}")


class _Totals:
    """Accumulate integers and stored monetary values before rounding."""

    def __init__(self) -> None:
        self.count = self.energy = self.grid = self.seconds = self.priced = 0
        self.minimum: int | None = None
        self.maximum = 0
        self.cost = Decimal(0)
        self.saved = Decimal(0)
        self.saved_count = 0

    def add(self, session: dict[str, Any]) -> None:
        energy = session["energy_wh"]
        self.count += 1
        self.energy += energy
        self.grid += session["grid_wh"]
        self.seconds += session["duration_s"]
        self.minimum = energy if self.minimum is None else min(self.minimum, energy)
        self.maximum = max(self.maximum, energy)
        if session.get("cost") is not None:
            self.priced += 1
            self.cost += Decimal(str(session["cost"]))
            if session.get("saved") is not None:
                self.saved_count += 1
                self.saved += Decimal(str(session["saved"]))

    def merge(self, bucket: dict[str, Any]) -> None:
        """Merge lossless monthly totals, including legacy optional counters."""
        count = bucket.get("count", 0)
        self.count += count
        self.energy += bucket.get("energy_wh", 0)
        self.grid += bucket.get("grid_wh", 0)
        self.seconds += bucket.get("duration_s", 0)
        minimum = bucket.get("min_wh")
        if minimum is not None:
            self.minimum = minimum if self.minimum is None else min(self.minimum, minimum)
        self.maximum = max(self.maximum, bucket.get("max_wh", 0))
        if bucket.get("cost") is not None:
            self.priced += bucket.get("priced_sessions", count)
            self.cost += Decimal(str(bucket["cost"]))
        if bucket.get("saved") is not None:
            self.saved_count += bucket.get("saved_sessions", count)
            self.saved += Decimal(str(bucket["saved"]))

    def archive_result(self) -> dict[str, Any]:
        """Keep integer units and unrounded money, not display-rounded values."""
        return {
            "count": self.count, "energy_wh": self.energy, "grid_wh": self.grid,
            "duration_s": self.seconds, "min_wh": self.minimum, "max_wh": self.maximum,
            "cost": float(self.cost) if self.priced else None,
            "saved": float(self.saved) if self.saved_count else None,
            "priced_sessions": self.priced, "saved_sessions": self.saved_count,
        }

    def result(self) -> dict[str, Any]:
        return {
            "sessions": self.count,
            "energy_kwh": round(self.energy / 1000, 3),
            "energy_grid_kwh": round(self.grid / 1000, 3),
            "energy_pv_kwh": round((self.energy - self.grid) / 1000, 3),
            "cost": float(round(self.cost, 3)) if self.priced else None,
            "saved": float(round(self.saved, 3)) if self.saved_count else None,
            "priced_sessions": self.priced,
            "avg_kwh": round(self.energy / (1000 * self.count), 3) if self.count else 0,
            "max_kwh": round(self.maximum / 1000, 3),
            "min_kwh": round((self.minimum or 0) / 1000, 3),
            "duration_min": round(self.seconds / 60, 1),
        }


def archive_session(bucket: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    """Add one session to a monthly bucket without mutating saved snapshots."""
    totals = _Totals()
    totals.merge(bucket)
    totals.add(session)
    result = {**deepcopy(bucket), **totals.archive_result()}
    vehicles = result.setdefault("by_vehicle", {})
    name = session.get("vehicle")
    if isinstance(name, str) and name.strip():
        vehicle = _Totals()
        vehicle.merge(vehicles.get(name, {}))
        vehicle.add(session)
        vehicles[name] = {**vehicles.get(name, {}), **vehicle.archive_result()}
    return result


def merge_archives(archives: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Combine entry-local monthly metrics for the chart (no vehicle grouping)."""
    totals: dict[str, _Totals] = {}
    for archive in archives:
        for month, bucket in archive.items():
            totals.setdefault(month, _Totals()).merge(bucket)
    return {month: bucket.archive_result() for month, bucket in totals.items()}


def summarise(
    sessions: Sequence[dict[str, Any]], start: datetime | None, end: datetime | None,
    *, archive: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assign the complete charge to its local start, never split at midnight.

    Missing or invalid timestamps cannot be assigned to a calendar period, but
    still contribute to the unbounded total (e.g. an older restored cycle).
    Prices are never recalculated: only stored cost/saving values are summed.
    """
    totals = _Totals()
    vehicles: dict[str, _Totals] = {}
    for session in sessions:
        if start is not None or end is not None:
            value = session.get("started_at")
            if not isinstance(value, str):
                continue
            try:
                timestamp = datetime.fromisoformat(value)
            except ValueError:
                continue
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            local_start = dt_util.as_local(timestamp)
            if start is not None and local_start < start:
                continue
            if end is not None and local_start >= end:
                continue
        totals.add(session)
        vehicle = session.get("vehicle")
        if isinstance(vehicle, str) and vehicle.strip():
            vehicles.setdefault(vehicle, _Totals()).add(session)
    for month, bucket in (archive or {}).items():
        # Monthly data cannot be split into days: include only complete months.
        local_month = datetime.strptime(month, "%Y-%m").replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        lower, upper = period_bounds("month", local_month)
        if start is not None and lower < start:
            continue
        if end is not None and upper > end:
            continue
        totals.merge(bucket)
        for name, values in bucket.get("by_vehicle", {}).items():
            vehicles.setdefault(name, _Totals()).merge(values)
    result = totals.result()
    if vehicles:
        result["by_vehicle"] = {}
        for name, bucket in vehicles.items():
            values = bucket.result()
            result["by_vehicle"][name] = {
                key: values[key] for key in ("sessions", "energy_kwh", "cost")
            }
    return result


class HistoryAggregateCache:
    """Keep one result per period and entry, including rollover and upserts."""

    def __init__(self) -> None:
        self._results: dict[str, tuple[tuple, dict[str, Any]]] = {}

    def get(
        self, period: str, sessions: Sequence[dict[str, Any]], now_local: datetime,
        *, revision: Any = None, archive: dict[str, Any] | None = None,
    ) -> tuple[datetime | None, datetime | None, dict[str, Any]]:
        """Revision additionally invalidates same-length replacements by the store."""
        start, end = period_bounds(period, now_local)
        key = (start, end, str(now_local.tzinfo), len(sessions), sessions[-1].get("id") if sessions else None, revision)
        cached = self._results.get(period)
        if cached is None or cached[0] != key:
            cached = (key, summarise(sessions, start, end, archive=archive))
            self._results[period] = cached
        # Entity consumers must not be able to mutate the cached nested dict.
        return start, end, deepcopy(cached[1])
