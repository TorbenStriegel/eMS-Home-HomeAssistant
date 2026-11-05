"""The ABL eMS Home integration."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.components.http import StaticPathConfig
from homeassistant.helpers.storage import Store
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_BATTERY_POWER_ENTITY,
    CONF_MIN_CYCLE_POWER,
    CONF_MIN_CYCLE_SECONDS,
    CONF_DEBUG_LOGGING,
    CONF_NOISE_FLOOR,
    CONF_NOTIFY_ENABLED,
    CONF_NOTIFY_ON_FINISH,
    CONF_NOTIFY_ON_START,
    CONF_NOTIFY_SERVICE,
    CONF_NOTIFY_VEHICLE,
    DEFAULT_NOTIFY_ON_FINISH,
    DEFAULT_NOTIFY_ON_START,
    DEFAULT_DEBUG_LOGGING,
    DEFAULT_MIN_CYCLE_POWER,
    DEFAULT_MIN_CYCLE_SECONDS,
    DEFAULT_NOISE_FLOOR,
    CONF_PV_POWER_ENTITY,
    CARD_FILENAME,
    DEFAULT_GRID_PRICE,
    DEFAULT_PV_PRICE,
    CARD_URL,
    CONF_ENABLE_EVSE,
    CONF_ENABLE_SMART_METER,
    CONF_GRID_PRICE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_PV_PRICE,
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


def _option_float(options: dict, key: str, default: float) -> float:
    """A numeric option, falling back to the default when it was never saved."""
    value = options.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _debug_option(options: dict) -> bool:
    """Verbose logging is opt-in – it costs CPU and fills the log."""
    value = options.get(CONF_DEBUG_LOGGING, DEFAULT_DEBUG_LOGGING)
    return bool(value)


def _price_option(options: dict, key: str, default: float) -> float:
    """Read a tariff from the options.

    An option that was never saved must fall back to the default (0,35 €/kWh),
    otherwise the cost sensors report ``None`` and show up as "unknown". A value
    the user saved – including 0 – is taken as it is.
    """
    value = options.get(key)
    if value is None:
        return default
    try:
        return max(float(value), 0.0)
    except (TypeError, ValueError):
        return default


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

    store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.session")
    coordinator = EMSHomeCoordinator(
        hass,
        client,
        int(interval),
        store=store,
        min_cycle_power=_option_float(options, CONF_MIN_CYCLE_POWER, DEFAULT_MIN_CYCLE_POWER),
        min_cycle_seconds=_option_float(options, CONF_MIN_CYCLE_SECONDS, DEFAULT_MIN_CYCLE_SECONDS),
        noise_floor=_option_float(options, CONF_NOISE_FLOOR, DEFAULT_NOISE_FLOOR),
        debug_logging=_debug_option(options),
        notify_enabled=bool(options.get(CONF_NOTIFY_ENABLED, False)),
        notify_service=options.get(CONF_NOTIFY_SERVICE) or None,
        notify_on_start=bool(options.get(CONF_NOTIFY_ON_START, DEFAULT_NOTIFY_ON_START)),
        notify_on_finish=bool(
            options.get(CONF_NOTIFY_ON_FINISH, DEFAULT_NOTIFY_ON_FINISH)
        ),
        notify_vehicle_entity=options.get(CONF_NOTIFY_VEHICLE) or None,
        pv_power_entity=options.get(CONF_PV_POWER_ENTITY) or None,
        battery_power_entity=options.get(CONF_BATTERY_POWER_ENTITY) or None,
        grid_price=_price_option(options, CONF_GRID_PRICE, DEFAULT_GRID_PRICE),
        pv_price=_price_option(options, CONF_PV_PRICE, DEFAULT_PV_PRICE),
    )
    await coordinator.async_load_session()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {DATA_COORDINATOR: coordinator}
    _async_register_services(hass)

    if _debug_option(options):
        logging.getLogger(__package__).setLevel(logging.DEBUG)
        _LOGGER.info("Verbose logging is enabled for eMS Home")
    else:
        logging.getLogger(__package__).setLevel(logging.NOTSET)

    await coordinator.async_start_websockets(
        smart_meter=options.get(CONF_ENABLE_SMART_METER, True),
        evse=options.get(CONF_ENABLE_EVSE, True),
    )

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




SERVICE_SET_LAST_SESSION = "set_last_session"
SERVICE_TEST_NOTIFICATION = "test_notification"

SERVICE_SET_LAST_SESSION_SCHEMA = vol.Schema(
    {
        vol.Optional("energy_kwh"): vol.All(vol.Coerce(float), vol.Range(min=0, max=1000)),
        vol.Optional("energy_grid_kwh"): vol.All(vol.Coerce(float), vol.Range(min=0, max=1000)),
        vol.Optional("energy_pv_kwh"): vol.All(vol.Coerce(float), vol.Range(min=0, max=1000)),
        vol.Optional("duration_min"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100000)),
        vol.Optional("cost"): vol.All(vol.Coerce(float), vol.Range(min=0, max=10000)),
    }
)


SERVICE_TEST_NOTIFICATION_SCHEMA = vol.Schema(
    {
        vol.Optional("kind", default="finish"): vol.In(["start", "finish"]),
        vol.Optional("send", default=True): bool,
    }
)


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    """Register the helper service used to test automations."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_LAST_SESSION):
        return

    async def _handle(call: ServiceCall) -> None:
        coordinators = [
            entry[DATA_COORDINATOR]
            for entry in hass.data.get(DOMAIN, {}).values()
            if DATA_COORDINATOR in entry
        ]
        if not coordinators:
            _LOGGER.warning("No eMS Home entry is loaded")
            return
        data = dict(call.data)
        for coordinator in coordinators:
            coordinator.async_set_last_session(**data)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_LAST_SESSION,
        _handle,
        schema=SERVICE_SET_LAST_SESSION_SCHEMA,
    )

    async def _handle_test(call: ServiceCall) -> None:
        coordinators = [
            entry[DATA_COORDINATOR]
            for entry in hass.data.get(DOMAIN, {}).values()
            if DATA_COORDINATOR in entry
        ]
        if not coordinators:
            _LOGGER.warning("No eMS Home entry is loaded")
            return
        for coordinator in coordinators:
            await coordinator.async_send_test(
                kind=call.data.get("kind", "finish"),
                send=bool(call.data.get("send", True)),
            )

    hass.services.async_register(
        DOMAIN,
        SERVICE_TEST_NOTIFICATION,
        _handle_test,
        schema=SERVICE_TEST_NOTIFICATION_SCHEMA,
    )

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
    for item in resources.async_items():
        if not str(item.get("url", "")).startswith(base):
            continue
        # The resource is stored once and would otherwise keep its old ?v=…,
        # so browsers go on serving the cached module after an update.
        if item.get("url") != url and hasattr(resources, "async_update_item"):
            await resources.async_update_item(item["id"], {"url": url})
            _LOGGER.debug("Updated the card resource to %s", url)
        return True

    await resources.async_create_item({"res_type": "module", "url": url})
    return True
