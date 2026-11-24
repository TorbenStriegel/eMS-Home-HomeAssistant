"""Charging history: one durable entry per finished charge.

Covers the store rules (upsert, reconcile, damaged files) and the coordinator
bookkeeping that feeds them.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.ems_home.history import (  # noqa: E402
    FLAG_GAP,
    FLAG_MODE_CHANGED,
    FLAG_RESTARTED,
    ChargingHistory,
    HistoryVersionError,
    build_record,
    history_key,
)

NOW = datetime(2026, 11, 10, 18, 22, 3, tzinfo=timezone.utc)


class FakeStore:
    """Minimal stand-in for homeassistant.helpers.storage.Store."""

    def __init__(self, data=None, *, raise_on_load=None):
        self.data = data
        self.saved = []
        self.delayed = []
        self.raise_on_load = raise_on_load

    async def async_load(self):
        if self.raise_on_load is not None:
            raise self.raise_on_load
        return self.data

    def async_delay_save(self, func, delay):
        self.delayed.append((func, delay))

    async def async_save(self, data):
        self.saved.append(data)


def record(session_id="abc123", **over):
    base = {
        "id": session_id,
        "started_at": (NOW - timedelta(minutes=170)).isoformat(),
        "ended_at": NOW.isoformat(),
        "last_flow_at": NOW.isoformat(),
        "duration_s": 10_020,
        "energy_wh": 8_704,
        "grid_wh": 8_408,
        "cost": 2.943,
        "saved": 0.104,
        "vehicle": "Seat",
        "end_reason": "idle",
        "still_plugged": True,
        "gap_s": 0,
        "restarts": 0,
        "flags": [],
    }
    base.update(over)
    return base


def history(data=None, **kw):
    h = ChargingHistory(FakeStore(data, **kw))
    asyncio.run(h.async_load())
    return h


# --------------------------------------------------------------------------- #
# Store rules
# --------------------------------------------------------------------------- #


def test_a_new_file_starts_empty_and_enabled():
    h = history()
    assert h.enabled and h.sessions == [] and h.load_error is None


def test_an_entry_is_written_once():
    h = history()
    assert h.upsert(record()) is True
    assert [s["id"] for s in h.sessions] == ["abc123"]
    assert h._store.delayed, "the write must be handed to the store"


def test_the_same_cycle_twice_does_not_create_a_second_entry():
    h = history()
    h.upsert(record())
    h.upsert(record(energy_wh=8_800))
    assert len(h.sessions) == 1
    assert h.sessions[0]["energy_wh"] == 8_800


def test_unknown_fields_survive_an_upsert():
    h = history({"sessions": [record(reviewer_note="kept")]})
    h.upsert(record(energy_wh=9_000))
    assert h.sessions[0]["reviewer_note"] == "kept"
    assert h.sessions[0]["energy_wh"] == 9_000


def test_reconcile_adds_a_missing_entry_only_once():
    h = history()
    assert h.reconcile(record()) is True
    assert h.reconcile(record()) is False
    assert len(h.sessions) == 1 and h.reconciled == 1


def test_a_damaged_file_is_left_untouched():
    h = history({"sessions": "kaputt"})
    assert h.enabled is False
    assert h.upsert(record()) is False
    assert h._store.saved == []
    assert "structure" in (h.load_error or "")


def test_a_failing_load_disables_the_history():
    h = history(raise_on_load=ValueError("half written"))
    assert h.enabled is False
    assert "ValueError" in (h.load_error or "")


def test_a_newer_major_version_is_refused():
    err = HistoryVersionError("newer")
    store = FakeStore(raise_on_load=err)
    h = ChargingHistory(store)

    async def loader():
        try:
            await h.async_load()
        except HistoryVersionError:
            h._disable("newer major version")

    asyncio.run(loader())
    assert h.enabled is False and h.upsert(record()) is False


def test_flush_writes_pending_changes():
    h = history()
    h.upsert(record())
    asyncio.run(h.async_flush())
    assert h._store.saved and h._store.saved[0]["sessions"][0]["id"] == "abc123"


def test_diagnostics_contain_counts_but_no_vehicle():
    h = history()
    h.upsert(record())
    info = h.diagnostics()
    assert info["sessions"] == 1 and info["enabled"] is True
    assert "Seat" not in str(info)


def test_the_key_is_per_entry():
    assert history_key("abc") == "ems_home.abc.history"
    assert history_key("abc") != history_key("def")


# --------------------------------------------------------------------------- #
# Record content
# --------------------------------------------------------------------------- #


def cycle(**over):
    base = {
        "id": "abc123",
        "started_at": (NOW - timedelta(minutes=170)).isoformat(),
        "wallbox_uuid": "wb-1",
        "mode_start": "grid",
        "last_flow_at": NOW.isoformat(),
        "gap_s": 0.0,
        "restarts": 0,
    }
    base.update(over)
    return base


def build(**over):
    args = dict(
        cycle=cycle(),
        ended_at=NOW.isoformat(),
        energy_wh=8_704.4,
        grid_wh=8_408.2,
        seconds=10_020.4,
        grid_price=0.35,
        pv_price=0.0,
        cost=2.943,
        saved=0.104,
        mode_end="grid",
        vehicle="Seat",
        end_reason="idle",
        still_plugged=True,
        now=NOW,
    )
    args.update(over)
    return build_record(**args)


def test_the_record_uses_integers_for_energy_and_time():
    r = build()
    assert r["energy_wh"] == 8_704 and r["duration_s"] == 10_020
    assert isinstance(r["grid_wh"], int)
    assert r["estimated"] is True and r["source"] == "live"


def test_grid_energy_never_exceeds_the_total():
    r = build(grid_wh=9_000.0, energy_wh=8_704.0)
    assert r["grid_wh"] == 8_704


def test_a_gap_sets_the_flag():
    r = build(cycle=cycle(gap_s=420.0))
    assert r["gap_s"] == 420 and FLAG_GAP in r["flags"]


def test_a_restart_sets_the_flag():
    r = build(cycle=cycle(restarts=2))
    assert r["restarts"] == 2 and FLAG_RESTARTED in r["flags"]


def test_a_mode_change_sets_the_flag():
    r = build(cycle=cycle(mode_start="pv"), mode_end="grid")
    assert FLAG_MODE_CHANGED in r["flags"]


def test_without_prices_cost_and_saving_stay_empty():
    r = build(grid_price=None, pv_price=None, cost=None, saved=None)
    assert r["cost"] is None and r["saved"] is None


def test_the_last_flow_falls_back_to_the_end():
    r = build(cycle=cycle(last_flow_at=None))
    assert r["last_flow_at"] == NOW.isoformat()


def test_a_clock_jump_is_flagged():
    future = NOW + timedelta(hours=2)
    r = build(cycle=cycle(started_at=future.isoformat()), now=NOW)
    assert "clock_suspect" in r["flags"]


# --------------------------------------------------------------------------- #
# Coordinator bookkeeping
# --------------------------------------------------------------------------- #


def make_coordinator(history_obj=None):
    from custom_components.ems_home.coordinator import EMSHomeCoordinator

    c = object.__new__(EMSHomeCoordinator)
    c.hass = SimpleNamespace(
        config=SimpleNamespace(language="de"),
        states={},
        async_create_task=lambda coro: None,
    )
    c.data = None
    c.async_update_listeners = lambda: None
    c._history = history_obj
    c._cycle = None
    c._pending_record = None
    c._last_session = {}
    c._session_energy_wh = 8_704.0
    c._session_grid_wh = 8_408.0
    c._session_seconds = 10_020.0
    c.grid_price = 0.35
    c.pv_price = 0.0
    c.notify_enabled = False
    c.notify_service = None
    c.notify_on_finish = False
    c.lock_after_charge = False
    c._mode = lambda: "grid"
    c._vehicle = lambda: "Seat"
    c._persist_session = lambda **_kw: None
    c._fired = []
    c._fire = lambda event, data: c._fired.append((event, data))
    return c


def test_a_started_charge_gets_an_id_and_a_start_time():
    c = make_coordinator()
    c._start_cycle_record(240.0)
    assert c._cycle["id"] and len(c._cycle["id"]) == 32
    started = datetime.fromisoformat(c._cycle["started_at"])
    age = (datetime.now(timezone.utc) - started).total_seconds()
    assert 230 < age < 260, "the start is reconstructed from the gate time"


def test_the_clock_tracking_remembers_the_last_flow():
    c = make_coordinator()
    c._start_cycle_record(0)
    c._track_cycle_clock(None, 1000.0, True)
    assert c._cycle["last_flow_at"] is not None
    before = c._cycle["last_flow_at"]
    c._track_cycle_clock(1000.0, 1020.0, False)
    assert c._cycle["last_flow_at"] == before, "no flow, no new last-flow time"


def test_a_long_gap_is_summed_up():
    c = make_coordinator()
    c._start_cycle_record(0)
    c._track_cycle_clock(1000.0, 1000.0 + 420.0, True)
    assert c._cycle["gap_s"] >= 420


def test_a_normal_interval_is_not_a_gap():
    c = make_coordinator()
    c._start_cycle_record(0)
    c._track_cycle_clock(1000.0, 1020.0, True)
    assert c._cycle["gap_s"] == 0


def test_finishing_writes_exactly_one_entry():
    h = history()
    c = make_coordinator(h)
    c._start_cycle_record(0)
    c._last_session = {
        "vehicle": "Seat",
        "energy_kwh": 8.704,
        "energy_grid_kwh": 8.408,
        "energy_pv_kwh": 0.296,
        "duration_min": 167.0,
        "ended_at": NOW.isoformat(),
        "cost": 2.943,
    }
    c._record_history("idle", True)
    assert len(h.sessions) == 1
    entry = h.sessions[0]
    assert entry["energy_wh"] == 8_704 and entry["vehicle"] == "Seat"
    assert c._pending_record["id"] == entry["id"]


def test_finishing_twice_updates_the_same_entry():
    h = history()
    c = make_coordinator(h)
    c._start_cycle_record(0)
    c._last_session = {"energy_kwh": 8.704, "ended_at": NOW.isoformat()}
    c._record_history("idle", True)
    c._record_history("idle", True)
    assert len(h.sessions) == 1


def test_without_a_history_nothing_breaks():
    c = make_coordinator(None)
    c._start_cycle_record(0)
    c._last_session = {"energy_kwh": 1.0, "ended_at": NOW.isoformat()}
    c._record_history("idle", True)  # must not raise
    assert c._pending_record["id"] == c._cycle["id"]


def test_a_hand_set_snapshot_creates_no_entry():
    h = history()
    c = make_coordinator(h)
    c._start_cycle_record(0)
    c.async_set_last_session(energy_kwh=4.0, cost=1.4)
    assert c._cycle is None and c._pending_record is None
    assert h.sessions == []


def test_the_finish_event_carries_the_reference():
    c = make_coordinator()
    c._start_cycle_record(0)
    c._last_session = {
        "vehicle": "Seat",
        "energy_kwh": 8.704,
        "energy_grid_kwh": 8.408,
        "energy_pv_kwh": 0.296,
        "duration_min": 167.0,
        "ended_at": NOW.isoformat(),
        "cost": 2.943,
    }
    c._announce_finish_inner()
    event, data = c._fired[-1]
    assert data["session_id"] == c._cycle["id"]
    assert data["started_at"] == c._cycle["started_at"]
    # the long-standing fields are still there
    for key in ("energy_kwh", "energy_grid_kwh", "energy_pv_kwh", "duration_min",
                "cost", "saved", "mode", "mode_label", "vehicle", "ended_at"):
        assert key in data, key


def test_a_restart_counts_once_and_keeps_the_id():
    h = history()
    c = make_coordinator(h)
    c._cycle = {"id": "keep", "started_at": NOW.isoformat(), "restarts": 0,
                "gap_s": 0.0, "mode_start": "grid", "last_flow_at": None,
                "last_sample_at": None, "wallbox_uuid": None}
    c._resume_cycle()
    assert c._cycle["id"] == "keep" and c._cycle["restarts"] == 1


def test_a_missing_entry_is_added_when_the_history_loads():
    h = history()
    c = make_coordinator(h)
    c._pending_record = record("missing")
    c._reconcile_history()
    assert h.has("missing") and h.reconciled == 1
