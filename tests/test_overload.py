"""Issue #4: the device toggles OverloadProtectionActive on single frames.

The entity must not blink, and a *reused* value from a failed partial poll must not
count as a second measurement.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.ems_home.coordinator import EMSHomeCoordinator  # noqa: E402


class Fake:
    """Runs the coordinator's own counter method – not a copy of it."""

    OVERLOAD_CONFIRM_SAMPLES = EMSHomeCoordinator.OVERLOAD_CONFIRM_SAMPLES
    _update_overload_counter = EMSHomeCoordinator._update_overload_counter

    def __init__(self):
        self._overload_samples = 0

    @property
    def samples(self):
        return self._overload_samples

    def feed(self, active, fresh=True):
        self._update_overload_counter(active, fresh)
        return self._overload_samples >= self.OVERLOAD_CONFIRM_SAMPLES


def test_a_single_frame_does_not_raise_a_problem():
    c = Fake()
    assert c.feed(True) is False
    assert c.feed(False) is False


def test_two_fresh_polls_are_needed():
    c = Fake()
    assert c.feed(True) is False
    assert c.feed(True) is True


def test_a_stale_value_does_not_confirm():
    """The regression the smoke test found: a reused state counted as a new one."""
    c = Fake()
    assert c.feed(True) is False
    assert c.feed(True, fresh=False) is False, "reused value must not confirm"
    assert c.feed(True, fresh=False) is False
    assert c.samples == 1


def test_an_unknown_value_neither_confirms_nor_clears():
    c = Fake()
    c.feed(True)
    assert c.feed(None) is False
    assert c.samples == 1, "a null field keeps the counter where it was"


def test_flicker_never_reaches_the_entity():
    c = Fake()
    shown = [c.feed(active) for active in (True, False, True, False, True, False)]
    assert not any(shown)


def test_the_counter_resets_when_the_device_reports_false():
    c = Fake()
    c.feed(True)
    c.feed(False)
    assert c.samples == 0


def test_the_entity_is_not_a_problem_class_entity():
    """Protective limiting is normal operation, not a fault."""
    from custom_components.ems_home.binary_sensor import BINARY_SENSOR_DESCRIPTIONS

    desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "overload_protection")
    assert desc.device_class is None


def test_the_raw_value_can_be_unknown():
    from custom_components.ems_home.coordinator import EMSHomeData

    data = EMSHomeData(
        device_status=None, emobility_state=None, charge_mode=None,
        overload_raw=None, overload_sustained=False,
    )
    assert data.overload_raw is None
