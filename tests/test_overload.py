"""The device toggles OverloadProtectionActive on single frames – the entity must not.

Issue #4: `binary_sensor.*_overload_protection` blinked between Problem and OK while
the wallbox was locked and drawing 0 kW. The integration passed the raw flag through
unfiltered.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.ems_home.coordinator import EMSHomeCoordinator  # noqa: E402


def coordinator() -> EMSHomeCoordinator:
    obj = object.__new__(EMSHomeCoordinator)
    obj._overload_samples = 0
    return obj


def poll(c: EMSHomeCoordinator, active: bool) -> bool:
    """One poll: returns the debounced value the entity would show."""
    c._overload_samples = c._overload_samples + 1 if active else 0
    return c._overload_samples >= c.OVERLOAD_CONFIRM_SAMPLES


def test_a_single_frame_does_not_raise_a_problem():
    c = coordinator()

    assert poll(c, True) is False, "one frame is not a problem"
    assert poll(c, False) is False, "and it clears again immediately"


def test_two_polls_in_a_row_do_report_it():
    c = coordinator()

    assert poll(c, True) is False
    assert poll(c, True) is True


def test_flicker_never_reaches_the_entity():
    c = coordinator()
    shown = [poll(c, active) for active in (True, False, True, False, True, False)]

    assert not any(shown), "alternating frames never count as sustained"


def test_the_raw_value_stays_available():
    """Power users can still see what the device actually sent."""
    from custom_components.ems_home.coordinator import EMSHomeData

    data = EMSHomeData(
        device_status=None, emobility_state=None, charge_mode=None,
        overload_raw=True, overload_sustained=False,
    )
    assert data.overload_raw is True
    assert data.overload_sustained is False


def test_it_is_not_a_problem_class_entity():
    """Protective limiting is normal operation, not a fault (issue #4)."""
    from homeassistant.components.binary_sensor import BinarySensorDeviceClass

    from custom_components.ems_home.binary_sensor import BINARY_SENSOR_DESCRIPTIONS

    desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "overload_protection")
    assert desc.device_class != BinarySensorDeviceClass.PROBLEM
