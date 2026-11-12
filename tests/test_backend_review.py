"""Local regressions for the backend review; no device or network needed."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, create_autospec

import pytest
import voluptuous as vol
import yaml

pytest.importorskip("homeassistant")

from homeassistant.core import HomeAssistant  # noqa: E402

from custom_components import ems_home as integration  # noqa: E402
from custom_components.ems_home.config_flow import (  # noqa: E402
    EMSHomeOptionsFlow,
    options_schema,
)
from custom_components.ems_home.const import (  # noqa: E402
    DATA_COORDINATOR,
    DEFAULT_IDLE_END_SECONDS,
    DOMAIN,
)
from custom_components.ems_home.coordinator import EMSHomeCoordinator  # noqa: E402


def _save_options(options, submitted):
    """Run the real options handler with schema-validated form input."""
    entry = SimpleNamespace(options=options, data={}, entry_id="first")
    flow = EMSHomeOptionsFlow()
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_known_entry=lambda _: entry)
    )
    flow.handler = "first"
    validated = options_schema(entry)(submitted)
    return asyncio.run(flow.async_step_init(validated))["data"]


@pytest.mark.parametrize("seconds", [30, 1200, 7200])
def test_idle_end_seconds_survives_options_save(seconds):
    saved = _save_options({}, {"tuning": {"idle_end_seconds": seconds}})
    assert saved["idle_end_seconds"] == seconds
    saved_again = _save_options(saved, {"tuning": {}})
    assert saved_again["idle_end_seconds"] == seconds


def test_idle_end_seconds_save_uses_default_when_tuning_is_omitted():
    saved = _save_options({}, {})
    assert saved["idle_end_seconds"] == DEFAULT_IDLE_END_SECONDS


def test_set_last_session_entry_id_is_only_a_target_selector(tmp_path):
    async def run():
        hass = HomeAssistant(str(tmp_path))
        first = create_autospec(EMSHomeCoordinator, instance=True)
        second = create_autospec(EMSHomeCoordinator, instance=True)
        hass.data[DOMAIN] = {
            "first": {DATA_COORDINATOR: first},
            "second": {DATA_COORDINATOR: second},
        }
        integration._async_register_services(hass)
        await hass.services.async_call(
            DOMAIN, "set_last_session", {"entry_id": "second", "energy_kwh": 12},
            blocking=True,
        )
        first.async_set_last_session.assert_not_called()
        second.async_set_last_session.assert_called_once_with(energy_kwh=12.0)
        second.async_set_last_session.reset_mock()
        await hass.services.async_call(
            DOMAIN, "set_last_session", {"energy_kwh": 3}, blocking=True,
        )
        first.async_set_last_session.assert_called_once_with(energy_kwh=3.0)
        second.async_set_last_session.assert_called_once_with(energy_kwh=3.0)
        await hass.services.async_call(
            DOMAIN, "test_notification",
            {"entry_id": "second", "kind": "start", "send": False}, blocking=True,
        )
        first.async_send_test.assert_not_called()
        second.async_send_test.assert_awaited_once_with(kind="start", send=False)
        first.async_set_last_session.reset_mock()
        second.async_set_last_session.reset_mock()
        await hass.services.async_call(
            DOMAIN, "set_last_session", {"entry_id": "unknown"}, blocking=True,
        )
        first.async_set_last_session.assert_not_called()
        second.async_set_last_session.assert_not_called()

    asyncio.run(run())


def test_services_follow_last_successfully_unloaded_entry(tmp_path):
    async def run():
        hass = HomeAssistant(str(tmp_path))
        hass.config_entries = SimpleNamespace(async_unload_platforms=AsyncMock(return_value=True))
        first = create_autospec(EMSHomeCoordinator, instance=True)
        second = create_autospec(EMSHomeCoordinator, instance=True)
        hass.data[DOMAIN] = {
            "first": {DATA_COORDINATOR: first},
            "second": {DATA_COORDINATOR: second},
        }
        integration._async_register_services(hass)
        integration._async_register_services(hass)
        names = ("set_last_session", "test_notification")
        assert all(hass.services.has_service(DOMAIN, name) for name in names)
        assert await integration.async_unload_entry(hass, SimpleNamespace(entry_id="first"))
        assert all(hass.services.has_service(DOMAIN, name) for name in names)
        await hass.services.async_call(
            DOMAIN, "test_notification", {"send": False}, blocking=True,
        )
        first.async_send_test.assert_not_called()
        second.async_send_test.assert_awaited_once_with(kind="finish", send=False)
        hass.config_entries.async_unload_platforms.return_value = False
        assert not await integration.async_unload_entry(hass, SimpleNamespace(entry_id="second"))
        assert "second" in hass.data[DOMAIN]
        assert all(hass.services.has_service(DOMAIN, name) for name in names)
        hass.config_entries.async_unload_platforms.return_value = True
        assert await integration.async_unload_entry(hass, SimpleNamespace(entry_id="second"))
        assert not any(hass.services.has_service(DOMAIN, name) for name in names)
        # Reload registers fresh handlers which target the new runtime state.
        hass.data[DOMAIN]["first"] = {DATA_COORDINATOR: first}
        integration._async_register_services(hass)
        assert all(hass.services.has_service(DOMAIN, name) for name in names)
        await hass.services.async_call(
            DOMAIN, "test_notification", {"send": False}, blocking=True,
        )
        first.async_send_test.assert_awaited_once_with(kind="finish", send=False)

    asyncio.run(run())


def test_service_yaml_cost_limits_match_runtime_validation():
    descriptions = yaml.safe_load(Path(integration.__file__).with_name("services.yaml").read_text())
    limits = descriptions["set_last_session"]["fields"]["cost"]["selector"]["number"]
    schema = integration.SERVICE_SET_LAST_SESSION_SCHEMA
    assert schema({"cost": limits["min"]})["cost"] == limits["min"]
    assert schema({"cost": limits["max"]})["cost"] == limits["max"]
    with pytest.raises(vol.Invalid):
        schema({"cost": limits["max"] + 0.01})


@pytest.mark.parametrize("legacy", [None, "sensor.car"])
def test_legacy_vehicle_option_is_migrated_without_losing_the_sensor(legacy):
    saved = _save_options({"notify_vehicle_entity": legacy}, {"notify": {}})
    assert saved["vehicle_entity"] == legacy
    # A null compatibility key is harmless and must not be deleted blindly.
    assert saved["notify_vehicle_entity"] is None
    cleared = _save_options(saved, {"vehicle_entity": None, "notify": {}})
    assert cleared["vehicle_entity"] is None
    assert _save_options(cleared, {})["vehicle_entity"] is None
