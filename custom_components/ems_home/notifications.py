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
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

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
            "⏱️ Dauer {duration} min\n"
            "🔌 Netz {grid} kWh · ☀️ PV {pv} kWh"
        ),
        "saved": " (statt {total} €)",
    },
    "en": {
        "started_title": "Charging started",
        "started_body": "⚡ Mode {mode} · €{price}/kWh",
        "finished_title": "Charging finished",
        "finished_body": (
            "💶 Cost €{cost}{saved}\n"
            "⚡ Charged {energy} kWh\n"
            "⏱️ Duration {duration} min\n"
            "🔌 Grid {grid} kWh · ☀️ PV {pv} kWh"
        ),
        "saved": " (instead of €{total})",
    },
}


def _strings(hass: HomeAssistant) -> dict[str, str]:
    language = (getattr(hass.config, "language", "en") or "en").lower()
    return TRANSLATIONS["de"] if language.startswith("de") else TRANSLATIONS["en"]


def _num(value: Any, digits: int = 1) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    return f"{number:.{digits}f}".replace(".", ",")


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
    energy = _num(session.get("energy_kwh"))
    grid = _num(session.get("energy_grid_kwh"))
    pv = _num(session.get("energy_pv_kwh"))
    duration = _num(session.get("duration_min"), 0)
    cost = _num(session.get("cost"), 2)
    total = _num(float(session.get("cost") or 0) + float(saved or 0), 2)

    body = text["finished_body"].format(
        cost=cost,
        energy=energy,
        duration=duration,
        grid=grid,
        pv=pv,
        saved=text["saved"].format(total=total) if saved and saved >= 0.01 else "",
    )
    car = vehicle_name(hass, session.get("vehicle_entity"))
    title = f"🔋 {car} – {text['finished_title']}" if car else f"🔋 {text['finished_title']}"
    return title, body


def start_messages(
    hass: HomeAssistant, mode: str | None, price: float, vehicle: str | None = None
) -> tuple[str, str]:
    """Title and body of the start notification."""
    text = _strings(hass)
    body = text["started_body"].format(mode=mode or "–", price=_num(price, 2))
    title = f"⚡ {vehicle} – {text['started_title']}" if vehicle else f"⚡ {text['started_title']}"
    return title, body


async def async_send(
    hass: HomeAssistant, service: str, title: str, body: str, target: str | None = None
) -> None:
    """Call a notify service; failures are logged, never raised into the cycle."""
    if not service:
        return
    domain, _, name = service.partition(".")
    if not name:
        domain, name = "notify", service
    data: dict[str, Any] = {"title": title, "message": body}
    if target:
        data["data"] = {"target": target, "url": target}
    try:
        await hass.services.async_call(domain, name, data, blocking=False)
    except Exception as exc:  # noqa: BLE001 - a notification must not break charging
        _LOGGER.warning("Could not send the notification via %s: %s", service, exc)
