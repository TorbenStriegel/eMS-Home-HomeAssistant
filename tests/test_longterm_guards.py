"""Guards that keep the integration honest over years: stale data, bad stores, budgets."""
from __future__ import annotations

import asyncio
import pathlib
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.ems_home import controller as controller_mod  # noqa: E402
from custom_components.ems_home import export as export_mod  # noqa: E402

# The scheduler needs a running hass loop; these tests are about the decisions.
controller_mod.async_call_later = lambda hass, delay, callback: (lambda: None)
from custom_components.ems_home.controller import (  # noqa: E402
    AutoChargeController,
    AutoChargeCore,
    AutoChargeSettings,
    Snapshot,
    validate_settings,
)


class Store:
    def __init__(self, data=None, fail_load=False):
        self.data = data
        self.fail_load = fail_load
        self.saves = []

    async def async_load(self):
        if self.fail_load:
            raise PermissionError("no access")
        return self.data

    async def async_save(self, payload):
        self.saves.append(payload)


class Hass:
    def __init__(self, values=None):
        self.states = SimpleNamespace(get=lambda entity: self._state(entity))
        self._values = values or {}
        self.data = {}       # the real Store constructor looks up its manager here
        self.config = SimpleNamespace(config_dir="/tmp", path=lambda *parts: "/tmp/" + "/".join(parts))

    def _state(self, entity):
        value = self._values.get(entity)
        if value is None:
            return None
        return value if hasattr(value, "state") else SimpleNamespace(state=str(value), attributes={})
        self.data = {}
        self.config = SimpleNamespace(config_dir="/tmp", path=lambda *parts: "/tmp/" + "/".join(parts))


class Coordinator:
    def __init__(self, *, ok=True, mode="lock", evse=None, power=0.0):
        self.last_update_success = ok
        self.evse = evse
        self.power = power
        self.data = SimpleNamespace(
            evse=evse, charge_mode=SimpleNamespace(mode=mode), charging_power_kw=power, session_ended=False
        )
        self.writes = []

    def async_add_listener(self, listener):
        return lambda: None

    async def async_set_charge_mode(self, mode):
        self.writes.append(mode)


def controller(coordinator=None, *, store=None, values=None):
    ctrl = AutoChargeController(
        Hass(values), coordinator or Coordinator(), "entry",
        surplus_entity="sensor.export", soc_entity="sensor.soc", guard_entity=None,
        settings=validate_settings(AutoChargeSettings()),
    )
    ctrl._store = store or Store()
    return ctrl


def test_a_failed_poll_is_not_a_healthy_device():
    """The coordinator keeps its last object; stale data must not release."""
    coordinator = Coordinator(ok=True, evse=SimpleNamespace(is_plugged=True, is_charging=False))
    ctrl = controller(coordinator, values={"sensor.export": "9000", "sensor.soc": "100"})

    async def run():
        await ctrl.async_start()
        await ctrl.async_set_armed(True)
        await ctrl.async_evaluate()          # the device confirms the lock
        assert ctrl.armed is True
        coordinator.last_update_success = False
        await ctrl.async_evaluate()
        assert "hybrid" not in coordinator.writes, "a failed poll must not release"
        assert ctrl.state == "degraded_unavailable"

    asyncio.run(run())


def test_an_old_store_with_wrong_types_does_not_crash_or_arm():
    core = AutoChargeCore(settings=validate_settings(AutoChargeSettings()))
    core.restore({"armed": "false", "released": "0", "released_at": "old",
                  "expected_until": "soon", "state": "nonsense"}, now=5.0)
    assert core.armed is False
    assert core.released is False
    assert core.released_at is None
    assert core.state == "off"
    assert core.step(Snapshot(mode="lock", plugged=True, soc=95, surplus_w=0), now=6).state == "off"


def test_a_broken_store_does_not_abort_the_setup():
    ctrl = controller(store=Store(fail_load=True))
    asyncio.run(ctrl.async_start())
    assert ctrl.state == "off"
    assert ctrl._loaded is True


async def run_in_executor(function, *args):
    return function(*args)


def test_a_full_export_folder_refuses_a_new_export():
    hass = SimpleNamespace(
        http=object(),
        data={"http.auth": object()},
        config=SimpleNamespace(path=lambda *parts: "/tmp/ems-home-test-" + "-".join(parts)),
        async_add_executor_job=run_in_executor,
    )

    async def run():
        with pytest.raises(ValueError, match="folder is full"):
            await export_mod.async_create_export(hass, [], [{"id": "x"}], "csv", {"entry"})

    original_stats = export_mod._folder_stats
    export_mod._folder_stats = lambda directory: {"files": export_mod.MAX_EXPORT_FILES, "bytes": 10}
    try:
        asyncio.run(run())
    finally:
        export_mod._folder_stats = original_stats


def test_the_export_budget_is_checked_after_writing_too(tmp_path):
    """A parallel export must not push the folder past 20 files / 64 MiB."""
    from custom_components.ems_home import history_services

    calls = {"n": 0}

    def stats(directory):
        calls["n"] += 1
        if calls["n"] == 1:            # before writing: one old file
            return {"files": 1, "bytes": 10}
        return {"files": export_mod.MAX_EXPORT_FILES + 1, "bytes": 10}

    def write(directory, file_format, sessions, now):
        target = pathlib.Path(directory) / "history-x.csv"
        target.write_text("a,b\n")
        return target

    hass = SimpleNamespace(
        http=object(), data={"http.auth": object()},
        config=SimpleNamespace(path=lambda *parts: str(tmp_path)),
        async_add_executor_job=run_in_executor,
    )
    original_stats, original_write = export_mod._folder_stats, history_services._write_export
    export_mod._folder_stats, history_services._write_export = stats, write
    try:
        async def run():
            with pytest.raises(ValueError, match="after this export"):
                await export_mod.async_create_export(hass, [], [{"id": "x"}], "csv", {"entry"})
        asyncio.run(run())
        assert not (tmp_path / "history-x.csv").exists(), "the refused file must be removed"
    finally:
        export_mod._folder_stats, history_services._write_export = original_stats, original_write
