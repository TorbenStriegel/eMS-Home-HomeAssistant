"""Optional: switch the wallbox to "lock" when a charge ends.

Requested feature. Off by default, because the change blocks the wallbox for the next
driver until somebody unlocks it.
"""
from __future__ import annotations

import asyncio
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


def run_finish(c):
    c._announce_finish_inner()
    for coro in c.tasks:
        asyncio.run(coro)
    c.tasks.clear()


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
