"""Tests for the automatic charge release, without Home Assistant."""
from __future__ import annotations

from custom_components.ems_home.const import AUTO_CHARGE_STATES
from custom_components.ems_home.controller import (
    CONFIRM_TIMEOUT,
    NO_CHARGE_TIMEOUT,
    AutoChargeCore,
    AutoChargeSettings,
    Snapshot,
    validate_settings,
)

LOCKED = Snapshot(mode="lock", plugged=True, soc=95, surplus_w=0)
RELEASED = Snapshot(mode="hybrid", plugged=True, soc=95, surplus_w=0)


def settings(**changes) -> AutoChargeSettings:
    return validate_settings(AutoChargeSettings(**changes))


def armed_core(**changes) -> AutoChargeCore:
    core = AutoChargeCore(settings=settings(**changes))
    core.arm(now=0.0)
    core.step(Snapshot(mode="lock", plugged=True, soc=95, surplus_w=0), now=1.0)
    assert core.state == "armed"
    return core


def test_arm_holds_the_wallbox_and_waits_for_confirmation():
    core = AutoChargeCore()
    decision = core.arm(now=0.0)
    assert decision.action == "lock"
    assert core.armed and core.state == "arming"
    # The device still reports the old mode: not confirmed, nothing else happens.
    assert core.step(Snapshot(mode="hybrid", plugged=True, soc=95), now=5.0).state == "arming"
    confirmed = core.step(LOCKED, now=6.0)
    assert confirmed.state == "armed" and core.armed


def test_unconfirmed_write_ends_the_order_instead_of_guessing():
    core = AutoChargeCore()
    core.arm(now=0.0)
    decision = core.step(Snapshot(mode="hybrid", plugged=True, soc=95), now=CONFIRM_TIMEOUT + 1)
    assert decision.state == "conflict_external"
    assert decision.reason == "mode_not_confirmed"
    assert core.armed is False


def test_a_foreign_mode_change_wins_and_is_never_written_back():
    core = armed_core()
    decision = core.step(Snapshot(mode="pv", plugged=True, soc=95), now=10.0)
    assert decision.state == "conflict_external"
    assert decision.action is None
    assert core.armed is False


def test_waiting_states_follow_soc_then_surplus():
    core = armed_core()
    assert core.step(Snapshot(mode="lock", plugged=True, soc=50, surplus_w=9000), now=10).state == "waiting_soc"
    low = core.step(Snapshot(mode="lock", plugged=True, soc=95, surplus_w=1000), now=11)
    assert low.state == "waiting_surplus" and low.action is None


def test_surplus_has_to_hold_before_the_release():
    core = armed_core(surplus_hold_s=60)
    core.step(Snapshot(mode="lock", plugged=True, soc=95, surplus_w=5000), now=100)
    assert core.state == "waiting_surplus"  # the clock just started
    assert core.step(Snapshot(mode="lock", plugged=True, soc=95, surplus_w=5000), now=130).state == "waiting_surplus"
    released = core.step(Snapshot(mode="lock", plugged=True, soc=95, surplus_w=5000), now=161)
    assert released.action == "hybrid"
    assert released.state == "starting"
    assert core.armed is False and core.released is True


def test_a_short_dip_restarts_the_hold():
    core = armed_core(surplus_hold_s=60)
    core.step(Snapshot(mode="lock", plugged=True, soc=95, surplus_w=5000), now=100)
    core.step(Snapshot(mode="lock", plugged=True, soc=95, surplus_w=1000), now=120)
    assert core.surplus_since is None
    core.step(Snapshot(mode="lock", plugged=True, soc=95, surplus_w=5000), now=130)
    assert core.step(Snapshot(mode="lock", plugged=True, soc=95, surplus_w=5000), now=170).state == "waiting_surplus"


def test_a_full_battery_releases_without_surplus_but_still_needs_a_valid_soc():
    core = armed_core()
    released = core.step(Snapshot(mode="lock", plugged=True, soc=100, surplus_w=0), now=10)
    assert released.action == "hybrid" and released.reason == "battery_full"


def test_unknown_soc_never_counts_as_full():
    core = armed_core()
    decision = core.step(Snapshot(mode="lock", plugged=True, soc=None, surplus_w=9000), now=10)
    assert decision.state == "degraded_unavailable"
    assert decision.reason == "soc_unavailable"
    assert core.armed is True  # the order survives, nothing is released


def test_unknown_vehicle_blocks_instead_of_releasing_into_the_void():
    core = armed_core()
    assert core.step(Snapshot(mode="lock", plugged=None, soc=100), now=10).state == "degraded_unavailable"
    blocked = core.step(Snapshot(mode="lock", plugged=False, soc=100), now=11)
    assert blocked.state == "blocked_no_vehicle"
    assert blocked.action is None


def test_release_anyway_policy_ignores_the_missing_vehicle():
    core = armed_core(no_vehicle="allow_release")
    decision = core.step(Snapshot(mode="lock", plugged=False, soc=100), now=10)
    assert decision.action == "hybrid"


def test_charging_is_observed_and_the_end_is_honest():
    core = armed_core()
    core.step(Snapshot(mode="lock", plugged=True, soc=100, surplus_w=0), now=10)
    core.step(RELEASED, now=11)
    assert core.state == "released"
    charging = core.step(Snapshot(mode="hybrid", plugged=True, soc=99, charging=True), now=20)
    assert charging.state == "charging"
    done = core.step(
        Snapshot(mode="hybrid", plugged=True, soc=99, charging=False, session_ended=True),
        now=4000,
    )
    assert done.state == "finished" and done.reason == "charge_ended"
    assert core.released is False
    # No automatic re-arming, ever.
    assert core.step(RELEASED, now=4100).state == "finished"


def test_a_release_without_any_power_gives_up_instead_of_waiting_forever():
    core = armed_core()
    core.step(Snapshot(mode="lock", plugged=True, soc=100), now=10)
    core.step(RELEASED, now=11)
    assert core.step(RELEASED, now=11 + NO_CHARGE_TIMEOUT + 1).reason == "no_charge"


def test_disarming_during_a_charge_does_not_stop_it():
    core = armed_core()
    core.step(Snapshot(mode="lock", plugged=True, soc=100), now=10)
    core.step(RELEASED, now=11)
    core.step(Snapshot(mode="hybrid", plugged=True, charging=True), now=12)
    decision = core.disarm(now=13)
    assert decision.action is None
    assert core.state == "charging"
    assert core.armed is False


def test_disarming_the_hold_restores_normal_charging():
    core = armed_core()
    decision = core.disarm(now=20)
    assert decision.action == "hybrid"
    assert core.state == "off" and core.armed is False


def test_restore_never_forces_a_mode_after_a_restart():
    core = AutoChargeCore()
    core.restore(
        {
            "armed": True,
            "state": "waiting_surplus",
            "expected_mode": "lock",
            "expected_until": 999.0,
            "settings": {"surplus_start_w": 4000, "surplus_hold_s": 60},
        }
    )
    assert core.armed is True
    assert core.expected_mode is None and core.surplus_since is None
    # If the device came back in another mode, that is a conflict, not a rewrite.
    decision = core.step(Snapshot(mode="hybrid", plugged=True, soc=95), now=1)
    assert decision.state == "conflict_external" and decision.action is None


def test_settings_are_clamped_and_cross_checked():
    fixed = settings(soc_min_pct=95, soc_full_pct=96, target_mode="grid", no_vehicle="whatever")
    assert fixed.target_mode == "hybrid"
    assert fixed.no_vehicle == "wait"
    assert fixed.soc_full_pct == 96
    high = settings(soc_min_pct=95, soc_full_pct=100)
    assert high.soc_full_pct == 99
    assert settings(surplus_start_w=1).surplus_start_w == 200
    assert settings(surplus_hold_s=99999).surplus_hold_s == 3600


def test_every_state_has_a_translation():
    import json

    for language in ("strings", "translations/de", "translations/en"):
        path = (
            "custom_components/ems_home/strings.json"
            if language == "strings"
            else f"custom_components/ems_home/{language}.json"
        )
        data = json.loads(open(path, encoding="utf-8").read())
        states = data["entity"]["sensor"]["auto_charge_state"]["state"]
        assert set(states) == set(AUTO_CHARGE_STATES), f"{path} misses a state"
