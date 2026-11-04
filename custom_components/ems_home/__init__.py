"""The ABL eMS Home integration."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CARD_FILENAME,
    CARD_URL,
    CONF_ENABLE_EVSE,
    CONF_ENABLE_SMART_METER,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    DATA_COORDINATOR,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    PLATFORMS,
    STATIC_URL_PATH,
)
from .coordinator import EMSHomeCoordinator
from .ems_home_api import EMSHomeHTTP

_LOGGER = logging.getLogger(__name__)

_MANIFEST = json.loads((Path(__file__).parent / "manifest.json").read_text("utf-8"))
VERSION = _MANIFEST.get("version", "0")

#: Registered once per Home Assistant run – the HTTP router keeps the route
#: across config entry reloads, so a second registration would raise.
_CARD_REGISTERED = False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up eMS Home from a config entry."""
    host = entry.data[CONF_HOST]
    password = entry.data[CONF_PASSWORD]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    options = entry.options
    interval = options.get(
        CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    timeout = options.get(CONF_TIMEOUT, entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))

    _LOGGER.debug("Setting up eMS Home %s:%s (poll %ss)", host, port, interval)

    client = EMSHomeHTTP(
        host,
        password,
        port=port,
        use_https=(port == 443),
        verify_ssl=False,
        timeout=timeout,
    )

    try:
        await hass.async_add_executor_job(client.login)
    except Exception as exc:  # noqa: BLE001
        raise ConfigEntryNotReady(
            f"Cannot connect to eMS Home at {host}:{port} – {exc}"
        ) from exc

    coordinator = EMSHomeCoordinator(hass, client, int(interval))
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {DATA_COORDINATOR: coordinator}

    if options.get(CONF_ENABLE_SMART_METER, True) and options.get(CONF_ENABLE_EVSE, True):
        await coordinator.async_start_websockets()
    else:
        _LOGGER.debug("Live streams disabled by options")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_register_card(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_on_unload(
        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, lambda *_: hass.async_create_task(
                coordinator.async_stop_websockets()
            )
        )
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if entry_data is not None:
        coordinator: EMSHomeCoordinator = entry_data[DATA_COORDINATOR]
        await coordinator.async_stop_websockets()
    else:
        _LOGGER.debug("Unloading %s without coordinator state", entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve and auto-load the bundled Lovelace card.

    Shipping the card inside the integration removes the usual "download the JS
    and add a dashboard resource" step: after installing/updating the
    integration the card is available as ``custom:ems-home-card``.
    """
    global _CARD_REGISTERED
    if _CARD_REGISTERED:
        return

    try:
        from homeassistant.components.frontend import add_extra_js_url
    except ImportError:  # pragma: no cover - frontend not loaded
        _LOGGER.debug("Frontend not available – skipping card registration")
        _CARD_REGISTERED = True
        return

    card_file = Path(__file__).parent / "frontend" / CARD_FILENAME
    if not card_file.is_file():
        _LOGGER.warning("Bundled card %s is missing", card_file)
        return

    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL_PATH, str(card_file.parent), False)]
        )
    except Exception as exc:  # noqa: BLE001 - already registered / router busy
        _LOGGER.debug("Static path already registered: %s", exc)

    add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
    _CARD_REGISTERED = True
    _LOGGER.debug("Registered eMS Home card at %s", CARD_URL)
