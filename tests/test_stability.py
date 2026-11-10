"""Stability regressions found on the live installation.

Three things made the integration look broken while it was working:

* the grid sensors went ``unavailable`` for minutes when the meter stream stalled,
  because a dead socket was only detected after five minutes,
* every short reconnect blanked eight sensors for a moment (HA records that, and
  automations trip over it),
* the session state was never written to disk while a charge was running, because
  the store's own delay was restarted on every frame.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.ems_home import ws_client  # noqa: E402
from custom_components.ems_home.sensor import stream_alive  # noqa: E402


def stats(*, frames=100, undecodable=0, age=1.0, connected=True, decoded_age=None):
    return SimpleNamespace(
        frames=frames, undecodable_frames=undecodable,
        seconds_since_frame=age, seconds_since_decoded=decoded_age,
        connected=connected,
    )


def test_the_meter_timeout_is_short_enough_to_heal():
    """The meter sends several frames per second, so silence means a dead link."""
    assert ws_client.METER_READ_TIMEOUT <= 60.0
    assert ws_client.METER_READ_TIMEOUT > 20.0, "must tolerate a hiccup"
    assert ws_client.EVSE_READ_TIMEOUT > ws_client.METER_READ_TIMEOUT


def test_a_short_reconnect_keeps_the_sensors_available():
    """A reconnect that takes a second must not blank eight sensors."""
    assert stream_alive(stats(connected=False, age=1.0), 60.0) is True


def test_a_long_silence_is_unavailable():
    assert stream_alive(stats(age=90.0), 60.0) is False


def test_a_stream_that_never_delivered_is_unavailable():
    assert stream_alive(stats(frames=0, age=0.0), 60.0) is False


def test_only_garbage_is_unavailable():
    assert stream_alive(stats(frames=10, undecodable=10), 60.0) is False


def test_garbage_frames_do_not_keep_old_values_fresh():
    """20 broken frames must not make a 20-minute-old reading look current."""
    assert stream_alive(stats(frames=120, undecodable=20, age=1.0, decoded_age=1200.0), 60.0) is False


def test_the_meter_stream_uses_its_own_timeout():
    """Wiring check: the smart meter must not fall back to the meter default."""
    import inspect

    from custom_components.ems_home import smart_meter_ws

    source = inspect.getsource(smart_meter_ws)
    assert "read_timeout=METER_READ_TIMEOUT" in source


def test_the_session_is_not_written_on_every_frame():
    """Otherwise the store's own delay never fires and nothing is saved."""
    import inspect

    from custom_components.ems_home.coordinator import EMSHomeCoordinator

    source = inspect.getsource(EMSHomeCoordinator._persist_session)
    assert "PERSIST_INTERVAL" in source
    assert EMSHomeCoordinator.PERSIST_INTERVAL >= 10.0


def test_the_store_restore_survives_a_damaged_file():
    """A hand-edited or half-written file must not abort the setup."""
    import asyncio

    from custom_components.ems_home.coordinator import EMSHomeCoordinator

    class BrokenStore:
        async def async_load(self):
            return {"energy_wh": "kaputt", "grid_wh": 1.0, "seconds": 2.0}

    c = object.__new__(EMSHomeCoordinator)
    c._store = BrokenStore()
    c._session_energy_wh = 0.0
    c._session_grid_wh = 0.0
    c._session_seconds = 0.0
    c._session_prev = None
    c._last_session = {}
    c._session_ended = True

    asyncio.run(c.async_load_session())
    assert c._session_energy_wh == 0.0


def test_the_meter_stream_is_wired_to_its_short_timeout():
    from custom_components.ems_home import ws_client

    assert ws_client.METER_READ_TIMEOUT < ws_client.READ_TIMEOUT


def test_charging_sensors_go_unavailable_with_the_stream():
    """Cached plug/charging values must not look like fresh news."""
    import inspect

    from custom_components.ems_home.binary_sensor import EMSBinarySensor

    source = inspect.getsource(EMSBinarySensor.available.fget)
    assert "stream_alive" in source
    assert "ev_plugged" in source
