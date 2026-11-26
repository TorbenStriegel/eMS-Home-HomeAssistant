"""Tests for the automatic charge release, without Home Assistant."""
from __future__ import annotations

from custom_components.ems_home.const import AUTO_CHARGE_STATES
from types import SimpleNamespace

from custom_components.ems_home.config_flow import _auto_input
from custom_components.ems_home.const import (
    CONF_AUTO_CHARGE_ENABLED,
    CONF_AUTO_GUARD_ENTITY,
    CONF_AUTO_NO_VEHICLE,
    CONF_AUTO_SOC_ENTITY,
    CONF_AUTO_SOC_FULL,
    CONF_AUTO_SOC_MIN,
    CONF_AUTO_SURPLUS_ENTITY,
    CONF_AUTO_SURPLUS_HOLD,
    CONF_AUTO_SURPLUS_START,
    CONF_AUTO_TARGET,
)
from custom_components.ems_home.controller import (
    CONFIRM_TIMEOUT,
    NO_CHARGE_TIMEOUT,
    AutoChargeCore,
    AutoChargeSettings,
    Snapshot,
    settings_from_options,
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


def test_a_full_battery_with_an_unknown_export_does_not_release():
    """Found by the beta.3 review: the battery path skipped the export check."""
    core = armed_core()
    decision = core.step(Snapshot(mode="lock", plugged=True, soc=100, surplus_w=None), now=10)
    assert decision.state == "degraded_unavailable"
    assert decision.reason == "surplus_unavailable"
    assert decision.action is None
    assert core.armed and not core.released
    # once the value is back, the full battery releases as before
    assert core.step(Snapshot(mode="lock", plugged=True, soc=100, surplus_w=0), now=11).state == "starting"


def test_unknown_soc_never_counts_as_full():
    core = armed_core()
    decision = core.step(Snapshot(mode="lock", plugged=True, soc=None, surplus_w=9000), now=10)
    assert decision.state == "degraded_unavailable"
    assert decision.reason == "soc_unavailable"
    assert core.armed is True  # the order survives, nothing is released


def test_unknown_vehicle_blocks_instead_of_releasing_into_the_void():
    core = armed_core()
    assert core.step(Snapshot(mode="lock", plugged=None, soc=100), now=10).state == "degraded_unavailable"
    blocked = core.step(Snapshot(mode="lock", plugged=False, soc=100, surplus_w=0), now=11)
    assert blocked.state == "blocked_no_vehicle"
    assert blocked.action is None


def test_release_anyway_policy_ignores_the_missing_vehicle():
    core = armed_core(no_vehicle="allow_release")
    decision = core.step(Snapshot(mode="lock", plugged=False, soc=100, surplus_w=0), now=10)
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
    core.step(Snapshot(mode="lock", plugged=True, soc=100, surplus_w=0), now=10)
    core.step(RELEASED, now=11)
    assert core.step(RELEASED, now=11 + NO_CHARGE_TIMEOUT + 1).reason == "no_charge"


def test_disarming_during_a_charge_does_not_stop_it():
    core = armed_core()
    core.step(Snapshot(mode="lock", plugged=True, soc=100, surplus_w=0), now=10)
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


def test_options_are_the_only_source_for_thresholds():
    defaults = settings_from_options({})
    assert defaults.surplus_hold_s == 120, "the calmer default"
    parsed = settings_from_options(
        {
            CONF_AUTO_SURPLUS_START: 5200,
            CONF_AUTO_SURPLUS_HOLD: 180,
            CONF_AUTO_SOC_FULL: 98,
            CONF_AUTO_SOC_MIN: 85,
            CONF_AUTO_TARGET: "pv",
            CONF_AUTO_NO_VEHICLE: "allow_release",
        }
    )
    assert parsed == AutoChargeSettings(5200.0, 180, 98, 85, "pv", "allow_release")
    # Junk in the store must not crash or release on guessed values.
    broken = settings_from_options({CONF_AUTO_SURPLUS_START: "abc", CONF_AUTO_TARGET: "grid"})
    assert broken == AutoChargeSettings()


def test_a_store_from_beta_one_cannot_override_the_options():
    core = AutoChargeCore(settings=settings_from_options({CONF_AUTO_SURPLUS_HOLD: 240}))
    core.restore({"armed": False, "settings": {"surplus_hold_s": 60}})
    assert core.settings.surplus_hold_s == 240


def test_the_form_keeps_stored_values_when_a_section_is_missing():
    entry = SimpleNamespace(
        options={
            CONF_AUTO_CHARGE_ENABLED: True,
            CONF_AUTO_SURPLUS_ENTITY: "sensor.export",
            CONF_AUTO_SOC_ENTITY: "sensor.soc",
            CONF_AUTO_GUARD_ENTITY: "automation.old",
            CONF_AUTO_SURPLUS_START: 4500,
            CONF_AUTO_SURPLUS_HOLD: 90,
            CONF_AUTO_SOC_FULL: 98,
            CONF_AUTO_SOC_MIN: 88,
            CONF_AUTO_TARGET: "pv",
            CONF_AUTO_NO_VEHICLE: "allow_release",
        }
    )
    # Only the threshold section was submitted.
    values = _auto_input(
        {"auto_thresholds": {CONF_AUTO_SURPLUS_START: 5000}}, entry
    )
    assert values[CONF_AUTO_SURPLUS_START] == 5000
    assert values[CONF_AUTO_SURPLUS_HOLD] == 90, "unchanged section value survives"
    assert values[CONF_AUTO_SURPLUS_ENTITY] == "sensor.export"
    assert values[CONF_AUTO_TARGET] == "pv"


def test_the_form_shows_booleans_and_stores_enums():
    values = _auto_input(
        {
            "auto": {CONF_AUTO_CHARGE_ENABLED: True, CONF_AUTO_SURPLUS_ENTITY: "sensor.x"},
            "auto_advanced": {"auto_solar_only": True, "auto_release_without_vehicle": True},
        }
    )
    assert values[CONF_AUTO_TARGET] == "pv"
    assert values[CONF_AUTO_NO_VEHICLE] == "allow_release"
    back = _auto_input({"auto_advanced": {"auto_solar_only": False}}, SimpleNamespace(options=values))
    assert back[CONF_AUTO_TARGET] == "hybrid"


def test_a_gap_in_the_data_restarts_the_hold():
    """Uninterrupted means uninterrupted: a blind minute cannot count towards it."""
    core = armed_core()
    core.step(Snapshot(mode="lock", plugged=True, soc=95, surplus_w=5000), now=100)
    # data missing in the middle of the hold
    core.step(Snapshot(mode="lock", plugged=True, soc=None, surplus_w=5000), now=140)
    # export is back and above the threshold, but the hold has to start over
    decision = core.step(Snapshot(mode="lock", plugged=True, soc=95, surplus_w=5000), now=200)
    assert decision.state == "waiting_surplus"
    assert decision.action is None
    # a full hold after the gap releases as usual
    released = core.step(Snapshot(mode="lock", plugged=True, soc=95, surplus_w=5000), now=321)
    assert released.state == "starting"


def test_a_failed_store_write_is_retried_on_the_next_tick():
    from custom_components.ems_home.controller import AutoChargeController

    class Store:
        def __init__(self):
            self.calls = 0

        async def async_load(self):
            return None

        async def async_save(self, payload):
            self.calls += 1
            if self.calls == 1:
                raise PermissionError("disk full")

    import asyncio

    class Hass:
        states = SimpleNamespace(get=lambda entity: None)
        data = {}
        config = SimpleNamespace(config_dir="/tmp", path=lambda *parts: "/tmp/" + "/".join(parts))

    controller = AutoChargeController(Hass(), SimpleNamespace(data=None), "e",
                                      surplus_entity=None, soc_entity=None, guard_entity=None)
    controller._store = Store()
    asyncio.run(controller._persist())
    asyncio.run(controller._persist())
    assert controller._store.calls == 2, "a failed write must be tried again"
