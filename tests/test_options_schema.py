"""The options form must build and validate – a broken one shows as HTTP 500."""
from __future__ import annotations

import pytest

pytest.importorskip("homeassistant")

from custom_components.ems_home.config_flow import options_schema  # noqa: E402
from custom_components.ems_home.const import (  # noqa: E402
    CONF_MIN_CYCLE_POWER,
    CONF_MIN_CYCLE_SECONDS,
    CONF_NOISE_FLOOR,
    DEFAULT_MIN_CYCLE_POWER,
    DEFAULT_MIN_CYCLE_SECONDS,
    DEFAULT_NOISE_FLOOR,
)


class FakeEntry:
    options: dict = {}
    data: dict = {}


def test_schema_builds_and_accepts_the_base_fields():
    schema = options_schema(FakeEntry())
    result = schema(
        {
            "scan_interval": 10,
            "timeout": 10,
            "enable_smart_meter_stream": True,
            "enable_evse_stream": True,
        }
    )
    assert result["scan_interval"] == 10


def test_tuning_section_is_nested():
    """The three detection values live in a collapsed section."""
    schema = options_schema(FakeEntry())
    result = schema(
        {
            "scan_interval": 10,
            "timeout": 10,
            "tuning": {
                CONF_MIN_CYCLE_POWER: 2.0,
                CONF_MIN_CYCLE_SECONDS: 60,
                CONF_NOISE_FLOOR: 0.2,
            },
        }
    )
    assert result["tuning"][CONF_MIN_CYCLE_POWER] == 2.0
    assert result["tuning"][CONF_NOISE_FLOOR] == 0.2


def test_every_constant_used_is_imported():
    """A missing import in the module showed up as a 500 in the dialog."""
    import ast
    from pathlib import Path

    import custom_components.ems_home.config_flow as mod

    source = Path(mod.__file__).read_text()
    tree = ast.parse(source)
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    missing = sorted(
        name for name in used if name.startswith(("CONF_", "DEFAULT_")) and not hasattr(mod, name)
    )
    assert missing == []


def _picker_in(validator):
    """Return the selector inside a validator (it may be wrapped in vol.Any)."""
    from homeassistant.helpers import selector

    inner = getattr(validator, "validators", None) or [validator]
    for candidate in inner:
        if isinstance(
            candidate, (selector.EntitySelector, selector.SelectSelector)
        ):
            return candidate
    return None


def test_every_field_appears_exactly_once():
    """A duplicated vol.Optional silently replaced the PV sensor field with a number."""
    schema = options_schema(FakeEntry())
    names = [key.schema for key in schema.schema]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    assert duplicates == [], f"duplicate fields: {duplicates}"


def test_sensor_fields_are_entity_pickers_and_prices_are_numbers():
    from homeassistant.helpers import selector

    schema = options_schema(FakeEntry())
    validators = {key.schema: value for key, value in schema.schema.items()}

    assert _picker_in(validators["pv_power_entity"]) is not None
    assert _picker_in(validators["battery_power_entity"]) is not None
    import voluptuous as vol

    for price in ("grid_price", "pv_price"):
        assert validators[price](0.35) == 0.35
        with pytest.raises(vol.Invalid):
            validators[price]("keine Zahl")


def test_verbose_logging_is_off_by_default():
    from custom_components.ems_home.const import DEFAULT_DEBUG_LOGGING

    import voluptuous as vol

    schema = options_schema(FakeEntry())
    keys = {key.schema: key for key in schema.schema}
    default = keys["debug_logging"].default
    assert default is not vol.UNDEFINED and default() is False
    assert DEFAULT_DEBUG_LOGGING is False


def test_notifications_have_their_own_section_and_are_off_by_default():
    from custom_components.ems_home.config_flow import notify_schema

    fields = {key.schema: value for key, value in notify_schema(FakeEntry()).schema.items()}
    assert "notify_enabled" in fields
    assert "notify_service" in fields
    assert "notify_on_finish" in fields

    schema_keys = [str(key.schema) for key in options_schema(FakeEntry()).schema]
    assert "notify" in schema_keys


def test_the_vehicle_sensor_is_an_entity_picker_and_the_service_a_dropdown():
    from homeassistant.helpers import selector

    from custom_components.ems_home.config_flow import notify_schema

    schema = notify_schema(FakeEntry())
    validators = {key.schema: value for key, value in schema.schema.items()}

    assert _picker_in(validators["notify_service"]) is not None
    # an empty field must be accepted, not rejected by the selector
    assert validators["notify_service"](None) is None
    # the vehicle sensor sits with the other sensors, not in the notify section
    assert "notify_vehicle_entity" not in validators

    main = {key.schema: value for key, value in options_schema(FakeEntry()).schema.items()}
    assert _picker_in(main["vehicle_entity"]) is not None
    assert "notify_test" in validators


def test_the_service_dropdown_lists_what_the_instance_offers():
    from custom_components.ems_home.config_flow import notify_services

    class Services:
        def async_services(self):
            return {"notify": {"mobile_app_pixel": {}, "notify": {}}}

    class Hass:
        services = Services()

    assert notify_services(Hass()) == ["notify.mobile_app_pixel", "notify.notify"]


def test_a_broken_service_registry_still_opens_the_dialog():
    from custom_components.ems_home.config_flow import notify_services

    class Hass:
        class services:
            @staticmethod
            def async_services():
                raise RuntimeError("boom")

    assert notify_services(Hass()) == ["notify.notify"]


def test_the_vehicle_survives_the_migration_and_can_be_cleared():
    from custom_components.ems_home.config_flow import _vehicle_input

    class Old:
        options = {"notify_vehicle_entity": "sensor.car"}

    class New:
        options = {"vehicle_entity": "sensor.car", "notify_vehicle_entity": "sensor.car"}

    # migration: the old key still counts while the new one was never saved
    assert _vehicle_input({}, Old()) == "sensor.car"
    # clearing the picker really clears it afterwards
    assert _vehicle_input({"vehicle_entity": None}, New()) is None
    # a fresh pick wins
    assert _vehicle_input({"vehicle_entity": "sensor.other"}, New()) == "sensor.other"


def test_the_idle_end_is_configurable():
    from custom_components.ems_home.const import DEFAULT_IDLE_END_SECONDS
    from custom_components.ems_home.coordinator import EMSHomeCoordinator

    schema = options_schema(FakeEntry())
    keys = {str(key.schema): value for key, value in schema.schema.items()}
    section = keys["tuning"].schema.schema
    names = {str(key.schema): key for key in section}
    assert "idle_end_seconds" in names

    assert DEFAULT_IDLE_END_SECONDS == 300
