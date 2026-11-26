"""A year of the automatic, with reboots: no hang, no growth, no drift.

The core only uses a monotonic clock, so a DST change is not a special case; a
reboot is, because monotonic restarts at zero. This test walks a synthetic year in
five-minute steps and reboots every week, including in the middle of a release.
"""
from __future__ import annotations

import math

from custom_components.ems_home.const import AUTO_CHARGE_STATES
from custom_components.ems_home.controller import (
    AutoChargeCore,
    AutoChargeSettings,
    Snapshot,
    validate_settings,
)

STEP = 300.0
WEEK = 7 * 24 * 3600.0
STORE_KEYS = {"armed", "released", "charge_seen", "state", "reason", "run_id", "finished"}


def export_at(hour: float) -> float:
    """A sunny day: no export at night, a bell around noon."""
    if hour < 7 or hour > 20:
        return 0.0
    return 6500.0 * math.sin(math.pi * (hour - 7) / 13) ** 2


def test_a_year_of_automatic_charging_stays_sane():
    core = AutoChargeCore(settings=validate_settings(AutoChargeSettings()))
    uptime = 0.0
    reboot_at = WEEK
    released = 0
    states = set()
    store_shapes = set()
    hung = 0
    actions = []
    released_at = None
    for day in range(365):
        for slot in range(24 * 12):
            hour = slot / 12
            if not core.released and not core.armed and hour == 18:
                core.arm(now=uptime)          # a user arms the order in the evening
            soc = 92.0 + 8.0 * math.sin(2 * math.pi * (slot / 24 - 0.25))
            charging = core.released and released_at is not None and uptime - released_at < 3600
            ended = core.released and released_at is not None and uptime - released_at >= 7200
            snap = Snapshot(
                mode="hybrid" if core.released else "lock",
                plugged=True,
                soc=min(soc, 100.0),
                surplus_w=export_at(hour),
                charging=charging,
                session_ended=ended,
            )
            decision = core.step(snap, now=uptime)
            states.add(decision.state)
            store_shapes.add(frozenset(core.as_store()))
            if decision.action:
                assert decision.action in ("lock", "pv", "hybrid"), decision
                actions.append(decision.action)
                if decision.action != "lock":
                    released += 1
                    released_at = uptime
            if decision.state == "finished":
                released_at = None
            # a release must never hang: starting needs the confirm timeout, released
            # either charges or ends; three hours is generous for both
            if core.state in ("starting", "released") and released_at is not None \
                    and uptime - released_at > 3 * 3600:
                hung += 1
            # a reboot every week, sometimes in the middle of a release
            if uptime >= reboot_at:
                stored = core.as_store()
                assert set(stored) == STORE_KEYS, "the store must not grow a key"
                fresh = AutoChargeCore(settings=core.settings)
                fresh.restore(stored, now=0.0)
                core = fresh
                reboot_at += WEEK
                if core.released:
                    released_at = 0.0
            uptime += STEP
    assert states <= set(AUTO_CHARGE_STATES), states
    assert released > 200, f"a daily order in a sunny year releases often, got {released}"
    assert released < 3650, "every five minutes cannot be a new order"
    assert hung == 0, "an order that never charges has to expire, also after a reboot"
    assert len(store_shapes) == 1, "the store shape is constant, so the file cannot grow"
