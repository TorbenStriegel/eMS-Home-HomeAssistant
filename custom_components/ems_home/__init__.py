"""eMS Home integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .ems_home_api import EMSHomeHTTP
from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DATA_COORDINATOR,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import EMSHomeCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "select", "number"]



async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up eMS Home from a config entry."""
    host     = entry.data[CONF_HOST]
    password = entry.data[CONF_PASSWORD]
    port     = entry.data.get(CONF_PORT, DEFAULT_PORT)
    interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    _LOGGER.info(
        "Setting up eMS Home: host=%s port=%d interval=%ds",
        host, port, interval,
    )

    client = EMSHomeHTTP(
        host, password, port=port,
        use_https=(port == 443),
        verify_ssl=False,
    )

    try:
        await hass.async_add_executor_job(client.login)
        _LOGGER.info("eMS Home login successful for %s:%d", host, port)
    except Exception as exc:
        _LOGGER.error("eMS Home login failed for %s:%d – %s", host, port, exc)
        raise ConfigEntryNotReady(
            f"Cannot connect to eMS Home at {host}:{port} – {exc}"
        ) from exc

    coordinator = EMSHomeCoordinator(hass, client, interval)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as exc:
        _LOGGER.error("eMS Home first refresh failed: %s", exc)
        raise

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_start_websocket()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _LOGGER.info("eMS Home setup complete for %s:%d", host, port)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: EMSHomeCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    await coordinator.async_stop_websocket()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
