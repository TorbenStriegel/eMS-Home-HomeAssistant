"""Optional: switch the wallbox to "lock" when a charge ends.

Requested feature. Off by default, because the change blocks the wallbox for the next
driver until somebody unlocks it.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.ems_home.const import (  # noqa: E402
    DEFAULT_LOCK_AFTER_CHARGE,
    DEFAULT_NOTIFY_ON_FINISH,
)


def coordinator(**kwargs):
    from custom_components.ems_home.coordinator import EMSHomeCoordinator

    c = object.__new__(EMSHomeCoordinator)
    c.lock_after_charge = kwargs.get("lock_after_charge", DEFAULT_LOCK_AFTER_CHARGE)
    c.notify_enabled = False
    c.notify_on_finish = DEFAULT_NOTIFY_ON_FINISH
    c.notify_service = None
    c._last_session = {
        "energy_kwh": 5.0, "energy_grid_kwh": 4.0, "energy_pv_kwh": 1.0,
        "duration_min": 60.0, "cost": 1.4, "vehicle": "Seat", "ended_at": None,
    }
    c.grid_price = 0.35
    c.pv_price = 0.0
    c._fired = []
    c._fire = lambda event, data: c._fired.append(event)
    c._mode = lambda: "grid"
    c.locked = []
    c.tasks = []
    c.hass = SimpleNamespace(
        config=SimpleNamespace(language="de"),
        states={},
        # Collect instead of scheduling: the test then runs the coroutine in its own
        # loop, so it does not depend on a loop being alive somewhere else.
        async_create_task=c.tasks.append,
    )

    async def fake_set_mode(mode):
        c.locked.append(mode)

    c.async_set_charge_mode = fake_set_mode
    return c


def drain_tasks(c):
    for coro in c.tasks:
        asyncio.run(coro)
    c.tasks.clear()


def run_finish(c):
    c._announce_finish_inner()
    drain_tasks(c)


def test_start_does_not_write_mode_when_lock_after_charge_is_enabled():
    c = coordinator(lock_after_charge=True)
    c._announce_start_inner()
    drain_tasks(c)
    assert c.locked == []


def test_start_then_finish_writes_mode_exactly_once():
    c = coordinator(lock_after_charge=True)
    c._announce_start()
    drain_tasks(c)
    run_finish(c)
    assert c.locked == ["lock"]


@pytest.mark.parametrize("name", ["_lock_after_charge_if_wanted", "_lock_after_charge"])
def test_lock_helpers_are_defined_only_once_in_the_class_body(name):
    from custom_components.ems_home.coordinator import EMSHomeCoordinator

    # vars() cannot detect overwritten definitions: inspect the entire class AST.
    tree = ast.parse(inspect.getsource(EMSHomeCoordinator))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    definitions = [node for node in cls.body
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and node.name == name]
    assert len(definitions) == 1, f"{name}: {len(definitions)} definitions"


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("end", ["unplug", "idle"])
def test_real_state_machine_locks_only_once_per_finished_cycle(monkeypatch, enabled, end):
    from custom_components.ems_home import coordinator as coord_mod
    from custom_components.ems_home import notifications
    from test_cycle_regressions import Clock, coordinator as cycle_coordinator, sample

    clock = Clock()
    monkeypatch.setattr(coord_mod.time, "monotonic", clock.monotonic)
    c = cycle_coordinator()
    io = coordinator(lock_after_charge=enabled)
    for name in ("hass", "lock_after_charge", "notify_enabled", "notify_on_finish",
                 "notify_service", "_fire", "_mode", "async_set_charge_mode"):
        setattr(c, name, getattr(io, name))

    def feed(power, seconds):
        for _ in range(0, seconds, 20):
            clock.advance(20)
            c._accumulate_session_energy(sample(power))
            drain_tasks(io)  # Run the scheduled write after every poll, not just at the end.

    for cycle in range(2):
        c._plugged = True
        feed(3.6, 240)
        assert not c._session_ended
        assert io._fired.count(notifications.EVENT_STARTED) == cycle + 1
        during = list(io.locked)
        assert during == (["lock"] * cycle if enabled else [])
        c._plugged = end == "idle"
        feed(0, 360)
        assert c._session_ended
        assert io._fired.count(notifications.EVENT_FINISHED) == cycle + 1
        expected = ["lock"] * (cycle + 1) if enabled else []
        assert io.locked == expected
        feed(0, 600)  # Further polls after completion must not write again.
        assert io.locked == expected
        print(f"state-machine enabled={enabled} end={end} cycle={cycle + 1}: "
              f"after 240s={during}, after finish+600s polls={io.locked}")


def test_it_is_off_by_default():
    assert DEFAULT_LOCK_AFTER_CHARGE is False
    c = coordinator()
    run_finish(c)
    assert c.locked == []


def test_the_option_locks_the_wallbox_after_a_charge():
    c = coordinator(lock_after_charge=True)
    run_finish(c)
    assert c.locked == ["lock"]


def test_no_second_write_when_it_is_already_locked():
    c = coordinator(lock_after_charge=True)
    c._mode = lambda: "lock"
    run_finish(c)
    assert c.locked == []


def test_a_failing_write_does_not_break_the_finish_path():
    c = coordinator(lock_after_charge=True)

    async def boom(mode):
        raise RuntimeError("device away")

    c.async_set_charge_mode = boom
    run_finish(c)  # must not raise
    assert c._fired, "the finish event still went out"


def test_the_option_is_part_of_the_options_schema():
    """The dialog must offer it, otherwise the option is unreachable.

    The switch sits in the notification section, because it fires together with the
    end-of-charge message.
    """
    import inspect

    from custom_components.ems_home import config_flow
    from custom_components.ems_home.const import CONF_LOCK_AFTER_CHARGE

    source = inspect.getsource(config_flow.notify_schema)
    assert "CONF_LOCK_AFTER_CHARGE" in source, "the switch is not in the dialog"
    assert CONF_LOCK_AFTER_CHARGE == "lock_after_charge"


def test_the_option_survives_a_save_without_the_notify_section():
    """Older flows do not submit the section; the stored value must survive."""
    from custom_components.ems_home.config_flow import _notify_input as _notify_section
    from custom_components.ems_home.const import CONF_LOCK_AFTER_CHARGE

    entry = SimpleNamespace(options={CONF_LOCK_AFTER_CHARGE: True})
    result = _notify_section({}, entry)
    assert result[CONF_LOCK_AFTER_CHARGE] is True
