"""Switch platform for eMS Home – the automatic charge release."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .auto_charge_entities import async_setup_switches


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the armed switch when the feature is configured."""
    await async_setup_switches(hass, entry, async_add_entities)
