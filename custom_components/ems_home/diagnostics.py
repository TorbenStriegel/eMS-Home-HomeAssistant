"""Diagnostics support for the eMS Home integration."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD, DATA_COORDINATOR, DOMAIN
from .coordinator import EMSHomeCoordinator

TO_REDACT = {CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Includes the raw decoded values *and* the live stream statistics – that is
    what makes a silent WebSocket debuggable from a user's bug report.
    """
    coordinator: EMSHomeCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    data = coordinator.data

    payload: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "connection": coordinator.diagnostics_snapshot(),
    }

    if data is None:
        payload["data"] = None
        return payload

    payload["data"] = {
        "device_status": asdict(data.device_status),
        "e_mobility": {
            "ev_charging_power": asdict(data.emobility_state.ev_charging_power),
            "curtailment_setpoint": asdict(data.emobility_state.curtailment_setpoint),
            "overload_protection_active": data.emobility_state.overload_protection_active,
        },
        "charge_mode": asdict(data.charge_mode),
        "smart_meter": data.smart_meter.as_dict() if data.smart_meter else None,
        "smart_meter_unknown_registers": (
            {hex(k): v for k, v in data.smart_meter.extra.items()}
            if data.smart_meter
            else None
        ),
        "evse": data.evse.as_dict() if data.evse else None,
        "evse_extra_values": data.evse.extra if data.evse else None,
    }
    return payload
