"""Long-term behaviour of the automatic controller: reboots, bursts, unload.

These are the failures that only show up after weeks: a release that never leaves
"starting" after a reboot, a burst of frames that writes twice, a task that writes
to the device after the entry was unloaded, or a state read that quietly changes
the unplug timer.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.ems_home import controller as mod  # noqa: E402
from custom_components.ems_home.controller import (  # noqa: E402
    CONFIRM_TIMEOUT,
    NO_CHARGE_TIMEOUT,
    AutoChargeController,
    AutoChargeCore,
    AutoChargeSettings,
    Snapshot,
    validate_settings,
)


# ---------------------------------------------------------------- fakes
class FakeStore:
    def __init__(self, data=None):
        self.data = data
        self.saves = []

    async def async_load(self):
        return self.data

    async def async_save(self, payload):
        self.saves.append(payload)


class FakeStates:
    def __init__(self, values):
        self.values = values

    def get(self, entity_id):
        value = self.values.get(entity_id)
        if value is None:
            return None
        if isinstance(value, str):
            return SimpleNamespace(state=value, attributes={})
        return value


class FakeHass:
    def __init__(self, states):
        self.states = FakeStates(states)
        self.tasks = []
        self.data = {}       # the real Store constructor looks up its manager here
        self.config = SimpleNamespace(config_dir="/tmp", path=lambda *parts: "/tmp/" + "/".join(parts))

    def async_create_task(self, coro):
        task = asyncio.ensure_future(coro)
        self.tasks.append(task)
        return task


class FakeCoordinator:
    def __init__(self, evse=None, mode="lock", power=0.0, session_ended=False):
        self.evse = evse
        self.mode = mode
        self.power = power
        self.session_ended = session_ended
        self.writes = []
        self.listeners = []
        self.data = self._data()

    def _data(self):
        return SimpleNamespace(
            evse=self.evse,
            charge_mode=SimpleNamespace(mode=self.mode),
            charging_power_kw=self.power,
            session_ended=self.session_ended,
        )

    def async_add_listener(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    async def async_set_charge_mode(self, mode):
        self.writes.append(mode)
        self.mode = mode
        self.data = self._data()


def evse(plugged=True, charging=False):
    return SimpleNamespace(is_plugged=plugged, is_charging=charging)


def settings(**changes):
    return validate_settings(AutoChargeSettings(**changes))


def build(stored=None, *, coordinator=None, states=None, settings_=None, **kwargs):
    # No timers in these tests: the scheduler needs a running loop and a real hass.
    mod.async_call_later = lambda hass, delay, callback: (lambda: None)
    hass = FakeHass(states or {"sensor.export": "5000", "sensor.soc": "96"})
    coord = coordinator or FakeCoordinator()
    ctrl = AutoChargeController(
        hass, coord, "entry", surplus_entity="sensor.export",
        soc_entity=kwargs.pop("soc_entity", "sensor.soc"),
        guard_entity=kwargs.pop("guard", None), settings=settings_ or settings(),
    )
    store = FakeStore(stored)
    ctrl._store = store
    return ctrl, hass, coord, store


# ---------------------------------------------------------------- the core
def test_a_reboot_mid_release_does_not_reuse_the_old_clock():
    """time.monotonic() restarts with the machine: a stored expected_until is poison."""
    core = AutoChargeCore(settings=settings())
    core.restore(
        {
            "released": True,
            "state": "starting",
            "reason": "surplus_reached",
            "run_id": "abc",
            # a boot that ran for 500000 s before this one
            "expected_mode": "hybrid",
            "expected_until": 500000.0,
            "released_at": 499600.0,
            "surplus_since": 499590.0,
        },
        now=5.0,
    )
    assert core.expected_mode is None, "a write from the previous boot cannot be confirmed"
    assert core.expected_until is None
    assert core.surplus_since is None
    assert core.released_at == 5.0
    assert (core.state, core.reason) == ("released", "restarted_mid_release")
    # The device is not charging: the order must expire on this boot's clock, not hang.
    decision = core.step(Snapshot(mode="hybrid", plugged=True, soc=99, surplus_w=0), now=5.0 + NO_CHARGE_TIMEOUT + 1)
    assert decision.state == "finished"
    assert decision.reason == "no_charge"


def test_a_reboot_while_charging_keeps_watching():
    core = AutoChargeCore(settings=settings())
    core.restore({"released": True, "state": "starting"}, now=5.0)
    decision = core.step(Snapshot(mode="hybrid", plugged=True, charging=True), now=6.0)
    assert decision.state == "charging"


def test_the_store_carries_no_monotonic_timestamps():
    core = AutoChargeCore(settings=settings())
    core.arm(now=0.0)
    core.step(Snapshot(mode="lock", plugged=True, soc=99, surplus_w=9000), now=10.0)
    stored = core.as_store()
    for key in ("surplus_since", "released_at", "expected_mode", "expected_until"):
        assert key not in stored


# ---------------------------------------------------------------- controller
def test_a_burst_of_updates_produces_one_evaluation_and_one_write():
    """Stream frames arrive faster than a write; they must coalesce, not queue."""

    async def scenario():
        coordinator = FakeCoordinator(evse=evse(plugged=True))
        ctrl, hass, _, _ = build(coordinator=coordinator)
        await ctrl.async_start()
        await ctrl.async_set_armed(True)          # locks the wallbox
        await ctrl.async_evaluate()                # the device confirms the lock
        assert coordinator.writes == ["lock"]
        # released by a full battery, the write confirms the mode
        hass.states.values["sensor.soc"] = "100"
        await ctrl.async_evaluate()
        assert coordinator.writes == ["lock", "hybrid"]
        # five frames while the write is still unconfirmed
        for _ in range(5):
            ctrl._on_update()
        await asyncio.gather(*hass.tasks)
        assert coordinator.writes == ["lock", "hybrid"], "a burst must not write the mode twice"
        return ctrl

    asyncio.run(scenario())


def test_unload_cancels_a_running_evaluation_before_it_writes():
    async def scenario():
        coordinator = FakeCoordinator()
        ctrl, hass, _, _ = build(coordinator=coordinator)
        await ctrl.async_start()
        gate = asyncio.Event()

        async def slow_locked():
            await gate.wait()
            coordinator.writes.append("late")

        ctrl._evaluate_locked = slow_locked
        ctrl._on_update()
        await asyncio.sleep(0)
        assert ctrl._task is not None and not ctrl._task.done()
        ctrl.async_stop()
        gate.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert coordinator.writes == [], "a write after unload reaches a device nobody watches"
        assert ctrl._task is None
        # a late frame after unload does nothing
        ctrl._on_update()
        await asyncio.sleep(0)
        assert ctrl._task is None

    asyncio.run(scenario())


def test_reading_attributes_does_not_start_the_unplug_timer():
    coordinator = FakeCoordinator(evse=evse(plugged=False))
    ctrl, _, _, _ = build(coordinator=coordinator)
    ctrl.attributes()
    ctrl.attributes()
    assert ctrl._unplug_since is None, "a state read must not change the machine"

    async def run():
        await ctrl.async_start()
        assert ctrl._unplug_since is not None

    asyncio.run(run())


def test_a_restart_with_a_stored_order_locks_again_without_a_second_arm():
    async def scenario():
        coordinator = FakeCoordinator()
        ctrl, hass, _, _ = build(stored={"armed": True, "state": "armed"},
                                 coordinator=FakeCoordinator(evse=evse(plugged=True)),
                                 states={"sensor.export": "0", "sensor.soc": "96"})
        await ctrl.async_start()
        assert ctrl.armed is True
        # the device is already locked: an armed order must not write again
        assert coordinator.writes == []
        assert ctrl.state in ("waiting_soc", "waiting_surplus", "blocked_no_vehicle")
        stored = await ctrl._store.async_load()
        assert stored["armed"] is True

    asyncio.run(scenario())


def test_an_unconfirmed_write_ends_in_conflict_instead_of_waiting_forever():
    async def scenario():
        coordinator = FakeCoordinator(evse=evse(plugged=True))
        ctrl, hass, _, _ = build(coordinator=coordinator)
        await ctrl.async_start()
        await ctrl.async_set_armed(True)
        await ctrl.async_evaluate()                # lock confirmed
        hass.states.values["sensor.soc"] = "100"

        async def silent_write(mode):
            coordinator.writes.append(mode)  # the device never adopts it
            ctrl._monotonic = lambda: 10_000.0
            ctrl.core.expected_until = 10.0

        coordinator.async_set_charge_mode = silent_write
        await ctrl.async_evaluate()
        assert ctrl.core.expected_mode == "hybrid", ctrl.core.expected_mode
        ctrl._monotonic = lambda: 10_000.0
        ctrl.core.expected_until = 10.0
        await ctrl.async_evaluate()
        assert ctrl.state == "conflict_external"
        assert ctrl.armed is False

    asyncio.run(scenario())


def test_a_guard_blocks_arming_without_touching_the_wallbox():
    async def scenario():
        coordinator = FakeCoordinator()
        ctrl, _, _, _ = build(coordinator=coordinator, guard="input_boolean.other",
                              states={"sensor.export": "5000", "sensor.soc": "96",
                                      "input_boolean.other": "on"})
        await ctrl.async_start()
        await ctrl.async_set_armed(True)
        assert coordinator.writes == []
        assert ctrl.state == "conflict_external"
        assert ctrl.armed is False
        assert ctrl.blocking_entity == "input_boolean.other"

    asyncio.run(scenario())


def test_confirmed_timeout_is_shorter_than_the_no_charge_timeout():
    """A stuck confirmation must heal before the order expires, or the card lies."""
    assert CONFIRM_TIMEOUT < NO_CHARGE_TIMEOUT


def test_without_a_battery_sensor_the_export_alone_releases():
    """Export-only setups: the controller tells the core there is no battery."""

    async def scenario():
        coordinator = FakeCoordinator(evse=evse(plugged=True))
        ctrl, hass, _, _ = build(
            coordinator=coordinator,
            states={"sensor.export": "5000"},
            settings_=settings(surplus_hold_s=0),
            soc_entity=None,
        )
        assert ctrl.attributes()["settings"]["battery"] is False
        await ctrl.async_start()
        await ctrl.async_set_armed(True)
        await ctrl.async_evaluate()                # lock confirmed
        await ctrl.async_evaluate()                # export above 4000 W, hold 0 s
        assert coordinator.writes == ["lock", "hybrid"]
        assert ctrl.core.reason != "soc_unavailable"

    asyncio.run(scenario())


def test_with_a_battery_sensor_the_card_is_told_so():
    ctrl, _, _, _ = build()
    assert ctrl.attributes()["settings"]["battery"] is True
