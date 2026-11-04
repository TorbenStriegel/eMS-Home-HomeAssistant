"""Guards against the class of bug where an entity reads a property that the
data snapshot does not have – the entity then stays 'unknown' forever."""
from __future__ import annotations

import dataclasses
import pathlib
import re

from custom_components.ems_home.coordinator import EMSHomeData

ROOT = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ems_home"


def _attributes_used() -> set[str]:
    used: set[str] = set()
    for name in ("sensor.py", "binary_sensor.py", "number.py", "select.py"):
        source = (ROOT / name).read_text()
        used.update(re.findall(r"\bd\.([a-z][a-z0-9_]*)", source))
    return used


def test_every_attribute_the_entities_read_exists():
    fields = {f.name for f in dataclasses.fields(EMSHomeData)}
    missing = sorted(
        attr
        for attr in _attributes_used()
        if attr not in fields and not hasattr(EMSHomeData, attr)
    )
    assert missing == [], f"entities read attributes that do not exist: {missing}"


def test_the_charge_state_still_works():
    """It was accidentally deleted once and every charging sensor went unknown."""
    assert hasattr(EMSHomeData, "charge_state")
    for name in ("charging_power_kw", "effective_pv_quota", "grid_power_kw", "is_locked"):
        assert hasattr(EMSHomeData, name), name
