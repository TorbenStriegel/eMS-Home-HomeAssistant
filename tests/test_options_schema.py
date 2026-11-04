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
