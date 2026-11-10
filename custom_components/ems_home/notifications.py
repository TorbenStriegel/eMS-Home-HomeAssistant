"""Charging notifications – bus events and an optional push.

Two separate things, deliberately:

* **Events** (`ems_home_charging_started` / `ems_home_charging_finished`) are always
  fired. They carry the whole cycle in their data, so an automation does not depend
  on sensors that may already have been reset.
* **Notifications** are opt-in. When enabled, the same data is rendered into a
  message and sent through the configured `notify` service.

Users pick one or the other – sending both means two messages per charge.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

#: The firmware speaks raw enums – people read their own language.
MODE_LABELS = {
    "de": {
        "grid": "Netz",
        "pv": "PV",
        "hybrid": "Hybrid",
        "lock": "Gesperrt",
        "locked": "Gesperrt",
        "unknown": "unbekannt",
    },
    "en": {
        "grid": "Grid",
        "pv": "PV",
        "hybrid": "Hybrid",
        "lock": "Locked",
        "locked": "Locked",
        "unknown": "unknown",
    },
}

EVENT_STARTED = "ems_home_charging_started"
EVENT_FINISHED = "ems_home_charging_finished"

TRANSLATIONS = {
    "de": {
        "started_title": "Ladevorgang gestartet",
        "started_body": "⚡ Modus {mode} · {price} €/kWh",
        "finished_title": "Ladevorgang beendet",
        "finished_body": (
            "💶 Kosten {cost} €{saved}\n"
            "⚡ Geladen {energy} kWh\n"
            "⏱️ Dauer {duration}\n"
            "🔌 Netz {grid} kWh · ☀️ PV {pv} kWh"
        ),
        "saved": " (statt {total} €)",
        "duration": "{h} Std. {m} Min.",
        "duration_short": "{m} Min.",
        "unknown": "unbekannt",
    },
    "en": {
        "started_title": "Charging started",
        "started_body": "⚡ Mode {mode} · €{price}/kWh",
        "finished_title": "Charging finished",
        "finished_body": (
            "💶 Cost €{cost}{saved}\n"
            "⚡ Charged {energy} kWh\n"
            "⏱️ Duration {duration}\n"
            "🔌 Grid {grid} kWh · ☀️ PV {pv} kWh"
        ),
        "saved": " (instead of €{total})",
        "duration": "{h} h {m} min",
        "duration_short": "{m} min",
        "unknown": "unknown",
    },
}


def _is_german(hass: HomeAssistant) -> bool:
    return (getattr(hass.config, "language", "en") or "en").lower().startswith("de")


def _strings(hass: HomeAssistant) -> dict[str, str]:
    return TRANSLATIONS["de"] if _is_german(hass) else TRANSLATIONS["en"]


def _number(value: Any) -> float | None:
    """Anything that is not a finite number becomes None, never an exception."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _num(value: Any, digits: int = 1, comma: bool = True) -> str:
    number = _number(value)
    if number is None:
        number = 0.0
    text = f"{number:.{digits}f}"
    return text.replace(".", ",") if comma else text


def _duration(minutes: Any, text: dict[str, str]) -> str:
    """3 Std. 15 Min. instead of 195 min – that is how people say it."""
    value = _number(minutes)
    if value is None:
        value = 0.0
    total = int(round(value))
    hours, mins = divmod(total, 60)
    if hours:
        return text["duration"].format(h=hours, m=mins)
    return text["duration_short"].format(m=mins)


def mode_label(hass: HomeAssistant, mode: Any) -> str:
    """`grid` becomes `Netz` / `Grid`; anything unknown is passed through."""
    raw = str(mode or "").strip().lower()
    if not raw:
        return "–"
    table = MODE_LABELS["de"] if _is_german(hass) else MODE_LABELS["en"]
    return table.get(raw, str(mode))


def vehicle_name(hass: HomeAssistant, entity_id: str | None) -> str:
    """The car as the user labelled it, without the emoji noise."""
    if not entity_id:
        return ""
    state = hass.states.get(entity_id)
    if state is None:
        return ""
    return state.state if state.state not in ("unknown", "unavailable") else ""


def finish_messages(
    hass: HomeAssistant, session: dict, saved: float | None = None
) -> tuple[str, str]:
    """Title and body of the finish notification."""
    text = _strings(hass)
    comma = _is_german(hass)
    cost_value = _number(session.get("cost"))
    saved_value = _number(saved) or 0.0

    body = text["finished_body"].format(
        cost=_num(cost_value, 2, comma),
        energy=_num(session.get("energy_kwh"), 1, comma),
        duration=_duration(session.get("duration_min"), text),
        grid=_num(session.get("energy_grid_kwh"), 1, comma),
        pv=_num(session.get("energy_pv_kwh"), 1, comma),
        saved=(
            text["saved"].format(total=_num((cost_value or 0.0) + saved_value, 2, comma))
            if saved_value >= 0.01
            else ""
        ),
    )
    # The session stores the name itself; the entity id is only a fallback for
    # callers that know nothing else.
    stored = str(session.get("vehicle") or "").strip()
    car = stored or vehicle_name(hass, session.get("vehicle_entity"))
    title = f"🔋 {car} – {text['finished_title']}" if car else f"🔋 {text['finished_title']}"
    return title, body


def start_messages(
    hass: HomeAssistant,
    mode: str | None,
    price: Any,
    vehicle: str | None = None,
) -> tuple[str, str]:
    """Title and body of the start notification."""
    text = _strings(hass)
    body = text["started_body"].format(
        mode=mode_label(hass, mode), price=_num(price, 2, _is_german(hass))
    )
    title = f"⚡ {vehicle} – {text['started_title']}" if vehicle else f"⚡ {text['started_title']}"
    return title, body


def normalise_service(service: str | None) -> str | None:
    """`mobile_app_x`, `notify.mobile_app_x` and `notify. notify` all work."""
    if not service:
        return None
    cleaned = str(service).strip().strip(".")
    if not cleaned:
        return None
    if "." not in cleaned:
        return f"notify.{cleaned}" if cleaned != "notify" else None
    domain, _, name = cleaned.partition(".")
    return f"{domain}.{name}" if name and domain else None


def notification_data(
    channel: str | None = None,
    importance: str | None = None,
    tag: str | None = None,
    icon: str | None = None,
) -> dict[str, Any]:
    """The Android extras – only for the fields that are actually set."""
    extra: dict[str, Any] = {}
    if channel:
        extra["channel"] = channel
    if importance:
        extra["importance"] = importance
    if tag:
        extra["tag"] = tag
    if icon:
        extra["notification_icon"] = icon
    return extra


async def async_send(
    hass: HomeAssistant,
    service: str,
    title: str,
    body: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Call a notify service; failures are logged, never raised into the cycle."""
    target = normalise_service(service)
    if not target:
        return
    domain, _, name = target.partition(".")
    data: dict[str, Any] = {"title": title, "message": body}
    if extra:
        # Home Assistant expects the Android extras nested under `data`.
        data["data"] = dict(extra)
    try:
        await hass.services.async_call(domain, name, data, blocking=True)
    except Exception as exc:  # noqa: BLE001 - a notification must not break charging
        _LOGGER.warning("Could not send the notification via %s: %s", target, exc)
