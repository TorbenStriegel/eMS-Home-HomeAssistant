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

    Three things happen here, because a card that silently fails to load is the
    most annoying failure mode there is:

    1. the JS file is served from the integration directory,
    2. it is added to the frontend as an extra module (works on every page,
       including a hard refresh of an already-open dashboard),
    3. it is registered as a Lovelace resource, so dashboards in storage mode
       load it reliably and the entry survives restarts.

    The success is logged at INFO: if that line is missing from the log, the new
    code never ran (Home Assistant needs a full restart, not an entry reload).
    """
    global _CARD_REGISTERED
    if _CARD_REGISTERED:
        return

    card_file = Path(__file__).parent / "frontend" / CARD_FILENAME
    if not card_file.is_file():
        _LOGGER.warning(
            "Bundled card %s is missing – custom:ems-home-card will not be available",
            card_file,
        )
        return

    url = f"{CARD_URL}?v={VERSION}"
    registered = []

    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL_PATH, str(card_file.parent), False)]
        )
        registered.append("static path")
    except Exception as exc:  # noqa: BLE001 - already registered on reload
        _LOGGER.debug("Static path already present (%s)", exc)

    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, url)
        registered.append("extra_js_url")
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("Could not add the eMS Home card to the frontend: %s", exc)

    try:
        if await _async_add_lovelace_resource(hass, url):
            registered.append("lovelace resource")
    except Exception as exc:  # noqa: BLE001 - YAML mode / older versions
        _LOGGER.debug("Lovelace resource not created: %s", exc)

    # A missing lovelace resource is fine as long as one path worked; only a
    # complete failure is worth a warning.
    if not registered:
        _LOGGER.warning(
            "custom:ems-home-card could not be registered – add %s manually as a "
            "dashboard resource (type: module)",
            url,
        )
        return

    _CARD_REGISTERED = True
    _LOGGER.info("Registered eMS Home card at %s (%s)", url, ", ".join(registered))


async def _async_add_lovelace_resource(hass: HomeAssistant, url: str) -> bool:
    """Add the card to the Lovelace resources (storage mode only).

    ``hass.data["lovelace"]`` is a dict in Home Assistant 2024.x and a dataclass
    with a ``resources`` attribute in newer versions, so both shapes are read.
    """
    try:
        from homeassistant.components.lovelace.const import DOMAIN as LOVELACE_DOMAIN
    except ImportError:  # pragma: no cover - very old versions
        LOVELACE_DOMAIN = "lovelace"

    lovelace = hass.data.get(LOVELACE_DOMAIN)
    if isinstance(lovelace, dict):
        resources = lovelace.get("resources")
    else:
        resources = getattr(lovelace, "resources", None)

    if resources is None or not hasattr(resources, "async_create_item"):
        return False  # YAML mode: resources live in configuration.yaml

    if hasattr(resources, "async_get_info"):
        await resources.async_get_info()

    base = url.split("?")[0]
    if any(str(item.get("url", "")).startswith(base) for item in resources.async_items()):
        return True

    await resources.async_create_item({"res_type": "module", "url": url})
    return True
