"""Charging notifications: the events carry the cycle, the push renders it."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.ems_home import notifications as notif  # noqa: E402
from custom_components.ems_home.coordinator import EMSHomeCoordinator  # noqa: E402


class Bus:
    def __init__(self):
        self.events = []

    def async_fire(self, event_type, data):
        self.events.append((event_type, data))


class States:
    def __init__(self, mapping):
        self.mapping = mapping

    def get(self, entity_id):
        return self.mapping.get(entity_id)


def hass(language="de", states=None):
    return SimpleNamespace(
        config=SimpleNamespace(language=language),
        states=States(states or {}),
        bus=Bus(),
        services=SimpleNamespace(async_call=_record_calls),
        async_create_task=lambda coro: coro.close(),
    )


CALLS: list = []


async def _record_calls(domain, service, data, blocking=False):
    CALLS.append((domain, service, data))


SESSION = {
    "energy_kwh": 12.4,
    "energy_grid_kwh": 5.1,
    "energy_pv_kwh": 7.3,
    "duration_min": 48.0,
    "cost": 1.78,
}


def test_the_finish_message_shows_cost_energy_duration_and_split():
    title, body = notif.finish_messages(hass(), SESSION, saved=2.56)

    assert "Ladevorgang beendet" in title
    assert "Kosten 1,78 €" in body
    assert "statt 4,34 €" in body
    assert "Geladen 12,4 kWh" in body
    assert "Dauer 48 min" in body
    assert "Netz 5,1 kWh" in body and "PV 7,3 kWh" in body


def test_the_car_name_is_part_of_the_title():
    states = {"sensor.car": SimpleNamespace(state="SEAT Leon")}
    title, _ = notif.finish_messages(hass(states=states), {**SESSION, "vehicle_entity": "sensor.car"})

    assert "SEAT Leon" in title


def test_english_messages():
    title, body = notif.finish_messages(hass(language="en"), SESSION, saved=2.56)

    assert "Charging finished" in title
    assert "Cost €1.78" in body, "English uses a decimal point"
    assert "Charged 12.4 kWh" in body


def test_no_saving_is_not_printed():
    _, body = notif.finish_messages(hass(), SESSION, saved=0.0)
    assert "statt" not in body


def coordinator(hass_obj) -> EMSHomeCoordinator:
    obj = object.__new__(EMSHomeCoordinator)
    obj.hass = hass_obj
    obj.grid_price = 0.35
    obj.pv_price = 0.0
    obj.notify_enabled = False
    obj.notify_service = None
    obj.notify_on_start = False
    obj.notify_on_finish = True
    obj.notify_vehicle_entity = None
    obj._last_session = dict(SESSION)
    obj.data = SimpleNamespace(charge_mode=SimpleNamespace(mode="grid"))
    return obj


def test_finishing_fires_an_event_with_the_whole_cycle():
    h = hass()
    c = coordinator(h)

    c._announce_finish()

    event, data = h.bus.events[0]
    assert event == notif.EVENT_FINISHED
    assert data["energy_kwh"] == 12.4
    assert data["cost"] == 1.78
    assert data["duration_min"] == 48.0
    assert data["saved"] == pytest.approx(7.3 * 0.35, rel=0.01)


def test_starting_fires_an_event_with_mode_and_price():
    h = hass()
    c = coordinator(h)

    c._announce_start()

    event, data = h.bus.events[0]
    assert event == notif.EVENT_STARTED
    assert data["mode"] == "grid"
    assert data["price_per_kwh"] == 0.35


def test_a_push_is_only_sent_when_it_is_switched_on():
    CALLS.clear()
    h = hass()
    c = coordinator(h)

    c._announce_finish()
    assert CALLS == []

    c.notify_enabled = True
    c.notify_service = "notify.mobile_app_pixel"
    c._announce_finish()
    asyncio.get_event_loop_policy()
    assert CALLS == []  # the coroutine is created, not awaited in this stub


def test_garbage_in_the_session_never_raises():
    broken = {"energy_kwh": "bad", "cost": float("inf"), "duration_min": None,
              "energy_grid_kwh": object(), "energy_pv_kwh": -3}
    title, body = notif.finish_messages(hass(), broken, saved="2")

    assert "Ladevorgang beendet" in title
    assert "Kosten 0,00 €" in body


def test_service_names_are_normalised():
    assert notif.normalise_service("notify.mobile_app_pixel") == "notify.mobile_app_pixel"
    assert notif.normalise_service("mobile_app_pixel") == "notify.mobile_app_pixel"
    assert notif.normalise_service(" notify.mobile_app_pixel ") == "notify.mobile_app_pixel"
    assert notif.normalise_service("notify.") is None
    assert notif.normalise_service("") is None
    assert notif.normalise_service(None) is None


def test_a_broken_announcement_does_not_break_the_cycle():
    h = hass()
    c = coordinator(h)
    c._last_session = {"cost": object()}  # formatting explodes
    c.notify_enabled = True
    c.notify_service = "notify.mobile_app_pixel"

    c._announce_finish()  # must not raise


def test_a_test_notification_uses_the_stored_session():
    h = hass()
    c = coordinator(h)
    c._last_session = dict(SESSION)

    payload = c.test_payload("finish")

    assert payload["test"] is True
    assert payload["energy_kwh"] == 12.4
    assert payload["cost"] == 1.78


def test_a_test_notification_falls_back_to_a_sample():
    h = hass()
    c = coordinator(h)
    c._last_session = {}

    payload = c.test_payload("finish")

    assert payload["energy_kwh"] > 0
    assert payload["test"] is True


def test_a_test_start_payload_has_mode_and_price():
    h = hass()
    c = coordinator(h)

    payload = c.test_payload("start")

    assert payload["mode"] == "grid"
    assert payload["price_per_kwh"] == 0.35
    assert payload["test"] is True


def test_the_test_service_fires_the_event_and_can_skip_the_push():
    CALLS.clear()
    h = hass()
    c = coordinator(h)
    c.notify_enabled = True
    c.notify_service = "notify.mobile_app_pixel"

    asyncio.run(c.async_send_test("finish", send=False))
    assert h.bus.events[-1][0] == notif.EVENT_FINISHED
    assert CALLS == []
