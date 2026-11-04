"""Writing to the eMS Home must survive the moments where it refuses connections.

The device's web server occasionally stops accepting TCP connections for a few
seconds. Writes are retried, and a failure is logged instead of bubbling up as
"action could not be executed" – the value simply snaps back.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.ems_home.coordinator import EMSHomeCoordinator  # noqa: E402


def coordinator(exec_job) -> EMSHomeCoordinator:
    obj = object.__new__(EMSHomeCoordinator)
    obj.hass = SimpleNamespace(async_add_executor_job=exec_job)
    obj.WRITE_RETRY_DELAY = 0
    obj._pending_mode = None
    obj._pending_quota = None
    return obj


def test_a_stalled_device_is_retried():
    calls = []

    async def exec_job(func, *args):
        calls.append(args)
        if len(calls) < 3:
            raise ConnectionError("connect timeout")
        return None

    ok = asyncio.run(coordinator(exec_job)._write_with_retry(lambda *a: None, "pv", 30))

    assert ok is True
    assert calls == [("pv", 30)] * 3


def test_a_device_that_never_answers_does_not_raise():
    calls = []

    async def exec_job(func, *args):
        calls.append(args)
        raise ConnectionError("connect timeout")

    ok = asyncio.run(coordinator(exec_job)._write_with_retry(lambda *a: None, "pv", 30))

    assert ok is False
    assert len(calls) == EMSHomeCoordinator.WRITE_ATTEMPTS


def test_the_selected_mode_is_visible_before_the_device_confirms():
    """The UI must not wait for a poll – that made the buttons feel dead."""
    from custom_components.ems_home.coordinator import EMSHomeCoordinator as C

    assert isinstance(C.pending_charge_mode, property)
    assert isinstance(C.pending_quota, property)


def test_a_poll_that_reports_the_new_mode_clears_the_optimistic_value():
    async def exec_job(func, *args):
        return None

    c = coordinator(exec_job)
    c.hass = SimpleNamespace(
        async_add_executor_job=exec_job,
        async_create_task=lambda coro: coro.close(),
    )
    c._pending_mode = "pv"
    c._pending_quota = 30

    charge_mode = SimpleNamespace(mode="pv", min_pv_power_quota=30, last_min_pv_power_quota=30)
    resolved = c._pending_mode is not None and charge_mode.mode == c._pending_mode
    resolved_q = c._pending_quota is not None and (
        charge_mode.min_pv_power_quota == c._pending_quota
    )

    assert resolved and resolved_q
