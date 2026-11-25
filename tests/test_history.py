"""Charging history: one durable entry per finished charge.

Covers the store rules (upsert, reconcile, damaged files) and the coordinator
bookkeeping that feeds them.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from uuid import UUID

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
    c.data = None
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


class SnapshotStore:
    """Control which of the delayed stores reaches disk before a crash."""

    def __init__(self, data=None):
        self.data = deepcopy(data)
        self.pending = None

    async def async_load(self):
        return deepcopy(self.data)

    def async_delay_save(self, payload, delay):
        self.pending = payload

    def commit(self):
        if self.pending:
            self.data = deepcopy(self.pending())
            self.pending = None

    async def async_save(self, data):
        self.data = deepcopy(data)


@pytest.fixture
def lifecycle(monkeypatch):
    from custom_components.ems_home import coordinator as module
    from test_cycle_regressions import coordinator
    from test_notifications import hass

    clock = SimpleNamespace(t=10000.0, wall=NOW)
    monkeypatch.setattr(module.time, "monotonic", lambda: clock.t)
    monkeypatch.setattr(module, "_utcnow", lambda: clock.wall)

    def make(session_store=None, history_store=None):
        c = coordinator()
        c.hass = hass(language="en")
        c.data = SimpleNamespace(charge_mode=SimpleNamespace(mode="hybrid"))
        c._latest_evse = SimpleNamespace(uuid="test-wallbox")
        c._plugged = True
        c._store = session_store or SnapshotStore()
        c._history = ChargingHistory(history_store or SnapshotStore())
        c._cycle = None
        c._pending_record = None
        c.async_update_listeners = lambda: None
        asyncio.run(c._history.async_load())
        return c

    return clock, make


def feed_cycle(c, clock, power, count=1, step=20):
    from test_cycle_regressions import sample

    for _ in range(count):
        clock.t += step
        clock.wall += timedelta(seconds=step)
        c._accumulate_session_energy(sample(power))


def start_cycle(c, clock):
    feed_cycle(c, clock, 3.6, count=7)
    assert not c._session_ended


def finish_cycle(c, clock, reason="unplugged"):
    c._plugged = reason == "idle"
    feed_cycle(c, clock, 0, count=17 if c._plugged else 3)
    assert c._session_ended


@pytest.mark.parametrize("reason", ["unplugged", "idle"])
def test_lifecycle_record_fields_and_start_persistence(lifecycle, reason):
    clock, make = lifecycle
    c = make()
    first = clock.wall + timedelta(seconds=20)
    start_cycle(c, clock)
    c._store.commit()
    metadata = c._store.data["cycle"]
    assert UUID(hex=metadata["id"]).version == 4
    assert len(metadata["id"]) == 32
    assert metadata["started_at"] == first.isoformat()
    last_flow = clock.wall.isoformat()
    finish_cycle(c, clock, reason)
    entry, = c._history.sessions
    assert set(entry) == {
        "id", "wallbox_uuid", "started_at", "ended_at", "last_flow_at", "duration_s",
        "energy_wh", "grid_wh", "grid_price", "pv_price", "cost", "saved",
        "mode_start", "mode_end", "vehicle", "end_reason", "still_plugged", "gap_s",
        "restarts", "flags", "estimated", "source",
    }
    assert entry["id"] == metadata["id"]
    assert entry["wallbox_uuid"] == "test-wallbox"
    assert entry["started_at"] == first.isoformat()
    assert entry["last_flow_at"] == last_flow
    assert entry["ended_at"] == c._last_session["ended_at"]
    assert entry["end_reason"] == reason
    assert entry["still_plugged"] is (reason == "idle")
    assert entry["energy_wh"] == entry["grid_wh"] == 120
    assert entry["duration_s"] == 120
    assert entry["flags"] == []
    c._store.commit()
    assert c._store.data["pending_record"] == entry
    assert "id" not in c._last_session
    asyncio.run(c.async_flush_history())
    assert c._history._store.data == {"sessions": [entry]}


def test_lifecycle_restart_preserves_id_and_start(lifecycle):
    clock, make = lifecycle
    c = make()
    start_cycle(c, clock)
    original = deepcopy(c._cycle)
    c._store.commit()
    restored = make(c._store)
    asyncio.run(restored.async_load_session())
    feed_cycle(restored, clock, 3.6, 3)
    finish_cycle(restored, clock)
    entry, = restored._history.sessions
    assert entry["id"] == original["id"]
    assert entry["started_at"] == original["started_at"]
    assert entry["restarts"] == 1
    assert entry["flags"] == ["restarted"]


def test_lifecycle_duplicate_finish_and_idle_polls(lifecycle):
    clock, make = lifecycle
    c = make()
    start_cycle(c, clock)
    finish_cycle(c, clock)
    original = deepcopy(c._history.sessions)
    c._record_history("unplugged", False)
    feed_cycle(c, clock, 0, 30)
    assert c._history.sessions == original


def test_lifecycle_crash_session_saved_history_missing(lifecycle):
    clock, make = lifecycle
    c = make()
    start_cycle(c, clock)
    finish_cycle(c, clock)
    c._store.commit()
    restored = make(c._store)
    asyncio.run(restored.async_load_session())
    assert restored._history.sessions == c._history.sessions
    assert restored._history.reconciled == 1
    asyncio.run(restored.async_load_session())
    assert restored._history.reconciled == 1
    asyncio.run(restored.async_flush_history())
    assert restored._history._store.data["sessions"] == c._history.sessions


def test_lifecycle_crash_history_saved_session_still_running(lifecycle):
    clock, make = lifecycle
    c = make()
    start_cycle(c, clock)
    c._store.commit()
    old_session = deepcopy(c._store.data)
    finish_cycle(c, clock)
    asyncio.run(c.async_flush_history())
    restored = make(SnapshotStore(old_session), c._history._store)
    asyncio.run(restored.async_load_session())
    feed_cycle(restored, clock, 3.6, 3)
    finish_cycle(restored, clock)
    entry, = restored._history.sessions
    assert entry["id"] == old_session["cycle"]["id"]
    assert entry["restarts"] == 1


@pytest.mark.parametrize("power", [0, 3.6])
@pytest.mark.parametrize("restart", [False, True])
def test_lifecycle_gap_boundary_with_zero_power_and_restart(lifecycle, power, restart):
    clock, make = lifecycle
    c = make()
    start_cycle(c, clock)
    before = c._session_energy_wh
    if restart:
        c._store.commit()
        c = make(c._store)
        asyncio.run(c.async_load_session())
    feed_cycle(c, clock, power, step=300)
    assert c._session_energy_wh == before
    finish_cycle(c, clock)
    entry, = c._history.sessions
    assert entry["gap_s"] == 300
    assert "gap" in entry["flags"]


def test_lifecycle_manual_snapshot_and_test_notification_are_not_recorded(lifecycle):
    clock, make = lifecycle
    c = make()
    start_cycle(c, clock)
    finish_cycle(c, clock)
    before = deepcopy(c._history.sessions)
    c.async_set_last_session(energy_kwh=12, energy_grid_kwh=6, duration_min=60)
    asyncio.run(c.async_send_test(send=False))
    assert c.hass.bus.events[-1][1]["test"] is True
    c._store.commit()
    restored = make(c._store, SnapshotStore({"sessions": before}))
    asyncio.run(restored.async_load_session())
    assert c._history.sessions == restored._history.sessions == before
    assert restored._history.reconciled == 0
    assert c._store.data["cycle"] is None
    assert c._store.data["pending_record"] is None


def test_lifecycle_finish_event_exact_legacy_snapshot_plus_two_fields(lifecycle):
    clock, make = lifecycle
    c = make()
    start_cycle(c, clock)
    finish_cycle(c, clock)
    event, payload = c.hass.bus.events[-1]
    assert event == "ems_home_charging_finished"
    assert payload == {
        "energy_kwh": 0.12, "energy_grid_kwh": 0.12, "energy_pv_kwh": 0.0,
        "duration_min": 2.0, "cost": 0.042, "saved": 0.0,
        "mode": "hybrid", "mode_label": "Hybrid", "vehicle": "",
        "ended_at": c._last_session["ended_at"],
        "session_id": c._cycle["id"], "started_at": c._cycle["started_at"],
    }


@pytest.mark.parametrize("raw", [
    "{broken",
    json.dumps({"version": 2, "data": {"sessions": []}}),
    json.dumps({"version": 1, "minor_version": 9, "data": {"sessions": "broken"}}),
])
def test_actual_history_file_is_untouched_after_load_failure(tmp_path, raw):
    from homeassistant.core import HomeAssistant
    from custom_components.ems_home.history import HistoryStore, HISTORY_VERSION

    async def run():
        h = HomeAssistant(str(tmp_path))
        store = HistoryStore(h, HISTORY_VERSION, history_key("test"))
        path = tmp_path / ".storage" / store.key
        path.parent.mkdir(exist_ok=True)
        path.write_text(raw)
        obj = ChargingHistory(store, h)
        await obj.async_load()
        assert not obj.enabled
        assert obj.load_error
        assert not obj.upsert({"id": "not-written"})
        assert not obj.reconcile({"id": "not-written"})
        await obj.async_flush()
        assert path.read_text() == raw
        assert list(path.parent.iterdir()) == [path]

    asyncio.run(run())


def test_actual_history_store_roundtrip(tmp_path, lifecycle):
    from homeassistant.core import HomeAssistant
    from custom_components.ems_home.history import HistoryStore, HISTORY_VERSION

    clock, make = lifecycle
    c = make()
    start_cycle(c, clock)
    finish_cycle(c, clock, "idle")
    entry, = c._history.sessions

    async def run():
        h = HomeAssistant(str(tmp_path))
        key = history_key("roundtrip")
        obj = ChargingHistory(HistoryStore(h, HISTORY_VERSION, key), h)
        await obj.async_load()
        assert obj.enabled
        obj.upsert(entry)
        await obj.async_flush()
        path = tmp_path / ".storage" / key
        persisted = json.loads(path.read_text())
        assert persisted["data"]["sessions"] == [entry]
        restored = ChargingHistory(HistoryStore(h, HISTORY_VERSION, key), h)
        await restored.async_load()
        assert restored.sessions == [entry]

    asyncio.run(run())


def test_lifecycle_no_tariff_mode_change_clock_jump(lifecycle):
    clock, make = lifecycle
    c = make()
    c.grid_price = c.pv_price = 0
    start_cycle(c, clock)
    c.data.charge_mode.mode = "grid"
    clock.wall -= timedelta(hours=1)
    finish_cycle(c, clock)
    entry, = c._history.sessions
    assert entry["grid_price"] is entry["pv_price"] is None
    assert entry["cost"] is entry["saved"] is None
    assert entry["mode_start"] == "hybrid"
    assert entry["mode_end"] == "grid"
    assert set(entry["flags"]) == {"mode_changed", "clock_suspect"}


def test_history_sensor_keeps_its_state_class():
    """The sensor must report a state class, or HA drops the long-term statistics.

    EMSHistorySensor once overrode capability_attributes to publish "history_disabled",
    which replaced the {"state_class": ...} payload. HA then reported "entity has no
    state class" and stopped building statistics for every period sensor.
    """
    from types import SimpleNamespace

    from custom_components.ems_home.sensor import EMSHistorySensor, SENSOR_DESCRIPTIONS

    class History:
        enabled = False

    class Client:
        uses_https = False
        host = "127.0.0.1"
        port = 80

    class Coordinator:
        _history = History()
        client = Client()

    description = next(d for d in SENSOR_DESCRIPTIONS if d.key == "history_week")
    entity = EMSHistorySensor(Coordinator(), SimpleNamespace(entry_id="test"), description)

    assert entity.capability_attributes == {"state_class": "total", "history_disabled": True}
    assert entity.extra_state_attributes == {"history_disabled": True}
