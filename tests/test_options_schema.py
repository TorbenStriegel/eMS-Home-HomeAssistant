"""The options form must build and validate – a broken one shows as HTTP 500."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("homeassistant")

from custom_components.ems_home.config_flow import options_schema  # noqa: E402
from custom_components.ems_home.const import (  # noqa: E402
    CONF_MIN_CYCLE_POWER,
    CONF_MIN_CYCLE_SECONDS,
    CONF_NOISE_FLOOR,
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

    schema = options_schema(FakeEntry())
    keys = {str(key.schema): value for key, value in schema.schema.items()}
    section = keys["tuning"].schema.schema
    names = {str(key.schema): key for key in section}
    assert "idle_end_seconds" in names

    assert DEFAULT_IDLE_END_SECONDS == 300


def test_the_notification_extras_are_pickers():
    from homeassistant.helpers import selector

    from custom_components.ems_home.config_flow import notify_schema

    fields = {str(k.schema): v for k, v in notify_schema(FakeEntry()).schema.items()}
    for name in ("notify_channel", "notify_importance", "notify_icon", "notify_tag"):
        assert name in fields, name

    assert _picker_in(fields["notify_channel"]) is not None
    assert _picker_in(fields["notify_importance"]) is not None
    # importance is a closed list – no free text
    inner = getattr(fields["notify_importance"], "validators", [fields["notify_importance"]])
    select = [v for v in inner if isinstance(v, selector.SelectSelector)][0]
    assert select.config.get("custom_value") in (False, None)


def _history_section(entry=None):
    fields = {
        key.schema: value
        for key, value in options_schema(entry or FakeEntry()).schema.items()
    }
    return fields["history"]


def test_history_section_is_collapsed_and_has_safe_defaults():
    from custom_components.ems_home.const import (
        DEFAULT_HISTORY_ENABLED,
        DEFAULT_HISTORY_RETENTION_MONTHS,
    )

    history = _history_section()
    assert history.options["collapsed"] is True
    assert history.schema({}) == {
        "history_enabled": True,
        "history_retention_months": 60,
    }
    assert DEFAULT_HISTORY_ENABLED is True
    assert DEFAULT_HISTORY_RETENTION_MONTHS == 60
    assert "history" not in options_schema(FakeEntry())({})


def test_history_section_uses_existing_flat_options():
    from types import SimpleNamespace

    entry = SimpleNamespace(
        data={}, options={"history_enabled": False, "history_retention_months": 0}
    )
    assert _history_section(entry).schema({}) == entry.options


@pytest.mark.parametrize("months", [0, 1, 60, 600])
def test_history_retention_accepts_integer_boundaries(months):
    result = options_schema(FakeEntry())(
        {"history": {"history_enabled": False, "history_retention_months": months}}
    )
    assert result["history"] == {
        "history_enabled": False, "history_retention_months": months
    }


@pytest.mark.parametrize("months", [-1, 601, 1.5, "60", None])
def test_history_retention_rejects_out_of_range_and_non_integer_values(months):
    import voluptuous as vol

    with pytest.raises(vol.Invalid):
        options_schema(FakeEntry())({"history": {"history_retention_months": months}})


@pytest.mark.parametrize("enabled", ["false", 0, None])
def test_history_enabled_requires_a_boolean(enabled):
    import voluptuous as vol

    with pytest.raises(vol.Invalid):
        options_schema(FakeEntry())({"history": {"history_enabled": enabled}})


def _save_history_options(options, submitted):
    import asyncio
    from types import SimpleNamespace

    from custom_components.ems_home.config_flow import EMSHomeOptionsFlow

    entry = SimpleNamespace(options=options, data={}, entry_id="history-test")
    flow = EMSHomeOptionsFlow()
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_known_entry=lambda _: entry)
    )
    flow.handler = entry.entry_id
    validated = options_schema(entry)(submitted)
    return asyncio.run(flow.async_step_init(validated))["data"]


def test_history_options_handler_saves_flat_values():
    saved = _save_history_options(
        {}, {"history": {"history_enabled": False, "history_retention_months": 0}}
    )
    assert "history" not in saved
    assert saved["history_enabled"] is False
    assert saved["history_retention_months"] == 0


def test_history_options_handler_preserves_omitted_section():
    options = {"history_enabled": False, "history_retention_months": 24}
    saved = _save_history_options(options, {})
    assert saved["history_enabled"] is False
    assert saved["history_retention_months"] == 24


@pytest.mark.parametrize("submitted", [{}, {"history": {}}])
def test_history_options_handler_initializes_missing_defaults(submitted):
    saved = _save_history_options({}, submitted)
    assert saved["history_enabled"] is True
    assert saved["history_retention_months"] == 60


def test_history_options_handler_preserves_partial_section_values():
    saved = _save_history_options(
        {"history_enabled": False, "history_retention_months": 24},
        {"history": {"history_retention_months": 600}},
    )
    assert saved["history_enabled"] is False
    assert saved["history_retention_months"] == 600


def test_history_option_translations_cover_labels_and_descriptions():
    import json
    from pathlib import Path

    component = Path(__file__).resolve().parents[1] / "custom_components/ems_home"
    blocks = []
    for relative in ("strings.json", "translations/en.json", "translations/de.json"):
        history = json.loads((component / relative).read_text())["options"]["step"]["init"]["sections"]["history"]
        assert history["name"]
        for field in ("history_enabled", "history_retention_months"):
            assert history["data"][field]
            assert history["data_description"][field]
        blocks.append(history)
    assert blocks[0] == blocks[1]


def test_every_auto_field_has_a_label_in_every_language():
    """A field without a label shows its raw key (auto_surplus_hold_s) in the dialog."""
    component = Path(__file__).resolve().parent.parent / "custom_components" / "ems_home"
    # The exact form fields of the three sections (not the internal option keys).
    wanted = {
        "auto": ["auto_charge_enabled", "auto_surplus_entity", "auto_soc_entity", "auto_guard_entity"],
        "auto_full": ["auto_soc_full_pct"],
        "auto_export": ["auto_surplus_start_w", "auto_surplus_hold_s", "auto_soc_min_pct"],
        "auto_behavior": ["auto_solar_only", "auto_release_without_vehicle"],
    }
    for relative in ("strings.json", "translations/en.json", "translations/de.json"):
        sections = json.loads((component / relative).read_text())["options"]["step"]["init"]["sections"]
        for section, keys in wanted.items():
            labels = sections[section].get("data", {})
            missing = [key for key in keys if key not in labels]
            assert not missing, f"{relative}: {section} has no label for {missing}"


def test_optional_sections_say_so_in_every_language():
    """A section that can be left alone should not look mandatory."""
    component = Path(__file__).resolve().parent.parent / "custom_components" / "ems_home"
    optional = ["tuning", "notify", "auto", "auto_full", "auto_export", "auto_behavior"]
    for relative in ("strings.json", "translations/en.json", "translations/de.json"):
        sections = json.loads((component / relative).read_text())["options"]["step"]["init"]["sections"]
        missing = [key for key in optional if "optional" not in sections[key]["name"].lower()]
        assert not missing, f"{relative}: no '(optional)' in {missing}"


def _options_result(submitted, options=None):
    import asyncio
    from types import SimpleNamespace

    from custom_components.ems_home.config_flow import EMSHomeOptionsFlow

    entry = SimpleNamespace(options=options or {}, data={}, entry_id="auto-test")
    flow = EMSHomeOptionsFlow()
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_known_entry=lambda _: entry)
    )
    flow.handler = entry.entry_id
    validated = options_schema(entry, flow.hass)(submitted)
    return asyncio.run(flow.async_step_init(validated))


def test_enabling_the_automatic_needs_only_the_export_sensor():
    """Without a house battery only path 2 exists; the export sensor is the one input."""
    missing = _options_result({"auto": {"auto_charge_enabled": True}})
    assert missing["errors"]["base"] == "auto_needs_source"

    export_only = _options_result(
        {"auto": {"auto_charge_enabled": True, "auto_surplus_entity": "sensor.export"}}
    )
    assert "errors" not in export_only, export_only
    assert export_only["data"]["auto_soc_entity"] is None

    both = _options_result(
        {
            "auto": {
                "auto_charge_enabled": True,
                "auto_surplus_entity": "sensor.export",
                "auto_soc_entity": "sensor.battery",
            }
        }
    )
    assert "errors" not in both, both


def test_the_minimum_must_stay_below_the_full_level():
    result = _options_result(
        {
            "auto": {"auto_charge_enabled": True, "auto_surplus_entity": "sensor.export"},
            "auto_full": {"auto_soc_full_pct": 90},
            "auto_export": {"auto_soc_min_pct": 90},
        }
    )
    assert result["errors"]["base"] == "auto_bad_thresholds"


def test_the_minimum_lives_in_the_export_path():
    """The full level is always above the minimum, so the minimum only limits path 2."""
    keys = {str(key.schema): value for key, value in options_schema(FakeEntry()).schema.items()}
    full = [str(key.schema) for key in keys["auto_full"].schema.schema]
    export = [str(key.schema) for key in keys["auto_export"].schema.schema]
    assert full == ["auto_soc_full_pct"]
    assert export == ["auto_surplus_start_w", "auto_surplus_hold_s", "auto_soc_min_pct"]
    assert "auto_thresholds" not in keys and "auto_start" not in keys


def _export_suggestion(entry, hass):
    keys = {str(key.schema): value for key, value in options_schema(entry, hass).schema.items()}
    fields = {str(key.schema): key for key in keys["auto"].schema.schema}
    return fields["auto_surplus_entity"].description["suggested_value"]


def test_the_export_sensor_of_this_integration_is_suggested(monkeypatch):
    """It is positive while exporting and in kW, which the automatic reads correctly."""
    from types import SimpleNamespace

    from homeassistant.helpers import entity_registry as er

    asked = []

    def lookup(domain, platform, unique_id):
        asked.append((domain, platform, unique_id))
        return "sensor.ems_home_grid_export"

    monkeypatch.setattr(er, "async_get", lambda hass: SimpleNamespace(async_get_entity_id=lookup))
    entry = SimpleNamespace(options={}, data={}, entry_id="abc")
    assert _export_suggestion(entry, object()) == "sensor.ems_home_grid_export"
    assert asked == [("sensor", "ems_home", "abc_grid_power_export")]

    # A cleared field (stored None, the state of every entry saved before) gets it too,
    # but a sensor the user chose always wins.
    entry.options = {"auto_surplus_entity": None}
    assert _export_suggestion(entry, object()) == "sensor.ems_home_grid_export"
    entry.options = {"auto_surplus_entity": "sensor.my_export"}
    assert _export_suggestion(entry, object()) == "sensor.my_export"


def test_no_suggestion_without_a_registry():
    from types import SimpleNamespace

    entry = SimpleNamespace(options={}, data={}, entry_id="abc")
    assert _export_suggestion(entry, None) is None
    assert _export_suggestion(entry, SimpleNamespace()) is None


def test_no_automatic_label_outside_its_sections():
    """Top-level auto_* texts are never shown and once contradicted the behaviour."""
    component = Path(__file__).resolve().parent.parent / "custom_components" / "ems_home"
    for relative in ("strings.json", "translations/en.json", "translations/de.json"):
        init = json.loads((component / relative).read_text())["options"]["step"]["init"]
        for block in ("data", "data_description"):
            stray = [key for key in init.get(block, {}) if key.startswith("auto_")]
            assert not stray, f"{relative}: {block} still has {stray}"
        errors = json.loads((component / relative).read_text())["options"]["error"]
        assert "auto_needs_soc" not in errors
