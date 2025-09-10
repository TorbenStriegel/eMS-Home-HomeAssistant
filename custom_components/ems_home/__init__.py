"""The eMS Home integration."""

from homeassistant.core import HomeAssistant
from .const import DOMAIN

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the eMS Home integration."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry):
    """Set up eMS Home from a config entry."""
    # Forward the entry to the sensor platform
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    )
    return True

async def async_unload_entry(hass: HomeAssistant, entry):
    """Unload a config entry."""
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    return True
