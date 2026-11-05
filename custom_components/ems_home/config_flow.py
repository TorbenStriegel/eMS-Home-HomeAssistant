"""Config flow for eMS Home."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .const import (
    CONF_BATTERY_POWER_ENTITY,
    CONF_ENABLE_EVSE,
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
    CONF_ENABLE_SMART_METER,
    CONF_GRID_PRICE,
    CONF_PV_POWER_ENTITY,
    CONF_PV_PRICE,
    DEFAULT_GRID_PRICE,
    DEFAULT_DEBUG_LOGGING,
    DEFAULT_MIN_CYCLE_POWER,
    DEFAULT_MIN_CYCLE_SECONDS,
    DEFAULT_NOISE_FLOOR,
    DEFAULT_PV_PRICE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .ems_home_api import EMSHomeHTTP

_LOGGER = logging.getLogger(__name__)


def _try_login(host: str, password: str, port: int, timeout: float) -> str | None:
    """Attempt to authenticate. Returns ``None`` on success, else an error key."""
    client = EMSHomeHTTP(
        host,
        password,
        port=port,
        use_https=(port == 443),
        verify_ssl=False,
        timeout=timeout,
    )
    try:
        client.login()
    except Exception as exc:  # noqa: BLE001
        message = str(exc).lower()
        if "401" in message or "403" in message or "unauthorized" in message:
            return "invalid_auth"
        if "timed out" in message or "timeout" in message:
            return "timeout"
        return "cannot_connect"
    else:
        return None
    finally:
        client.logout()


def _connection_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
            vol.Optional(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(
                int, vol.Range(min=1, max=65535)
            ),
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
            vol.Optional(
                CONF_TIMEOUT, default=defaults.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
            ): vol.All(int, vol.Range(min=3, max=60)),
        }
    )


class EMSHomeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the configuration, reconfiguration and re-authentication."""

    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry: ConfigEntry | None = None
        self._reconfigure_entry: ConfigEntry | None = None

    # -- initial setup -----------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            timeout = user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            error = await self.hass.async_add_executor_job(
                _try_login, host, user_input[CONF_PASSWORD], port, timeout
            )
            if error is None:
                return self.async_create_entry(
                    title=f"eMS Home ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_PORT: port,
                        CONF_SCAN_INTERVAL: user_input.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                        CONF_TIMEOUT: timeout,
                    },
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=_connection_schema(user_input or {}),
            errors=errors,
        )

    # -- re-authentication (password changed on the device) ----------------

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._reauth_entry
        if entry is None:
            return self.async_abort(reason="reauth_failed")

        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self.hass.async_add_executor_job(
                _try_login,
                entry.data[CONF_HOST],
                user_input[CONF_PASSWORD],
                entry.data.get(CONF_PORT, DEFAULT_PORT),
                entry.options.get(CONF_TIMEOUT, entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)),
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )

    # -- reconfigure (host / port changed) --------------------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="reconfigure_failed")
        self._reconfigure_entry = entry

        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            timeout = user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)

            error = await self.hass.async_add_executor_job(
                _try_login, host, user_input[CONF_PASSWORD], port, timeout
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=f"{host}:{port}",
                    data={
                        **entry.data,
                        CONF_HOST: host,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_PORT: port,
                        CONF_TIMEOUT: timeout,
                    },
                )
            errors["base"] = error

        defaults = {
            CONF_HOST: entry.data[CONF_HOST],
            CONF_PASSWORD: entry.data[CONF_PASSWORD],
            CONF_PORT: entry.data.get(CONF_PORT, DEFAULT_PORT),
            CONF_SCAN_INTERVAL: entry.options.get(
                CONF_SCAN_INTERVAL,
                entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ),
            CONF_TIMEOUT: entry.options.get(
                CONF_TIMEOUT, entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
            ),
        }
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_connection_schema(defaults),
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EMSHomeOptionsFlow()


class EMSHomeOptionsFlow(OptionsFlow):
    """Poll interval, timeouts and the live stream switches."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        errors: dict[str, str] = {}

        if user_input is not None:
            tuning = user_input.get("tuning") or {}
            return self.async_create_entry(
                data={
                    CONF_MIN_CYCLE_POWER: tuning.get(
                        CONF_MIN_CYCLE_POWER, DEFAULT_MIN_CYCLE_POWER
                    ),
                    CONF_MIN_CYCLE_SECONDS: tuning.get(
                        CONF_MIN_CYCLE_SECONDS, DEFAULT_MIN_CYCLE_SECONDS
                    ),
                    CONF_NOISE_FLOOR: tuning.get(CONF_NOISE_FLOOR, DEFAULT_NOISE_FLOOR),
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    CONF_TIMEOUT: user_input[CONF_TIMEOUT],
                    CONF_ENABLE_SMART_METER: user_input.get(CONF_ENABLE_SMART_METER, True),
                    CONF_ENABLE_EVSE: user_input.get(CONF_ENABLE_EVSE, True),
                    CONF_DEBUG_LOGGING: user_input.get(
                        CONF_DEBUG_LOGGING, DEFAULT_DEBUG_LOGGING
                    ),
                    **_notify_input(user_input, entry),
                    CONF_PV_POWER_ENTITY: user_input.get(CONF_PV_POWER_ENTITY) or None,
                    CONF_BATTERY_POWER_ENTITY: user_input.get(CONF_BATTERY_POWER_ENTITY) or None,
                    # The form always shows a value, so a missing key means the
                    # field was cleared: costs are switched off.
                    CONF_GRID_PRICE: _as_price(user_input.get(CONF_GRID_PRICE), 0.0),
                    CONF_PV_PRICE: _as_price(
                        user_input.get(CONF_PV_PRICE), DEFAULT_PV_PRICE
                    ),
                }
            )

        schema = options_schema(entry)
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

def _notify_input(user_input: dict, entry: ConfigEntry | None = None) -> dict:
    """Read the notification section; the whole block is optional."""
    if "notify" not in user_input and entry is not None:
        # The section was not submitted (older flow, automation) – keep what is
        # stored instead of silently switching the notifications off.
        opts = entry.options
        return {
            key: opts.get(key)
            for key in (
                CONF_NOTIFY_ENABLED,
                CONF_NOTIFY_SERVICE,
                CONF_NOTIFY_ON_START,
                CONF_NOTIFY_ON_FINISH,
                CONF_NOTIFY_VEHICLE,
            )
            if key in opts
        }
    section = user_input.get("notify") or {}
    return {
        CONF_NOTIFY_ENABLED: bool(section.get(CONF_NOTIFY_ENABLED, False)),
        CONF_NOTIFY_SERVICE: section.get(CONF_NOTIFY_SERVICE) or None,
        CONF_NOTIFY_ON_START: bool(
            section.get(CONF_NOTIFY_ON_START, DEFAULT_NOTIFY_ON_START)
        ),
        CONF_NOTIFY_ON_FINISH: bool(
            section.get(CONF_NOTIFY_ON_FINISH, DEFAULT_NOTIFY_ON_FINISH)
        ),
        CONF_NOTIFY_VEHICLE: section.get(CONF_NOTIFY_VEHICLE) or None,
    }


def _as_price(value, fallback: float) -> float:
    """Empty field -> fallback (0 switches the cost calculation off)."""
    if value is None or value == "":
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def notify_schema(entry: ConfigEntry) -> vol.Schema:
    """Notifications – collapsed by default, so the dialog stays short."""
    opts = entry.options
    return vol.Schema(
        {
            vol.Optional(
                CONF_NOTIFY_ENABLED,
                default=bool(opts.get(CONF_NOTIFY_ENABLED, False)),
            ): bool,
            vol.Optional(
                CONF_NOTIFY_SERVICE,
                description={
                    "suggested_value": opts.get(CONF_NOTIFY_SERVICE) or "notify."
                },
            ): vol.Any(None, str),
            vol.Optional(
                CONF_NOTIFY_ON_START,
                default=bool(opts.get(CONF_NOTIFY_ON_START, DEFAULT_NOTIFY_ON_START)),
            ): bool,
            vol.Optional(
                CONF_NOTIFY_ON_FINISH,
                default=bool(
                    opts.get(CONF_NOTIFY_ON_FINISH, DEFAULT_NOTIFY_ON_FINISH)
                ),
            ): bool,
            vol.Optional(
                CONF_NOTIFY_VEHICLE,
                description={"suggested_value": opts.get(CONF_NOTIFY_VEHICLE)},
            ): vol.Any(None, str),
        }
    )


def options_schema(entry: ConfigEntry) -> vol.Schema:
    """The options form – kept out of the flow so it can be unit-tested."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=entry.options.get(
                    CONF_SCAN_INTERVAL,
                    entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ),
            ): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
            vol.Optional(
                CONF_TIMEOUT,
                default=entry.options.get(
                    CONF_TIMEOUT, entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
                ),
            ): vol.All(int, vol.Range(min=3, max=60)),
            vol.Optional(
                CONF_ENABLE_SMART_METER,
                default=entry.options.get(CONF_ENABLE_SMART_METER, True),
            ): bool,
            vol.Optional(
                CONF_ENABLE_EVSE,
                default=entry.options.get(CONF_ENABLE_EVSE, True),
            ): bool,
            vol.Optional(
                CONF_DEBUG_LOGGING,
                default=entry.options.get(
                    CONF_DEBUG_LOGGING,
                    entry.data.get(CONF_DEBUG_LOGGING, DEFAULT_DEBUG_LOGGING),
                ),
            ): bool,
            vol.Optional(
                CONF_PV_POWER_ENTITY,
                description={
                    "suggested_value": entry.options.get(CONF_PV_POWER_ENTITY) or None
                },
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(
                CONF_BATTERY_POWER_ENTITY,
                description={
                    "suggested_value": entry.options.get(CONF_BATTERY_POWER_ENTITY) or None
                },
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional("tuning"): section(
                vol.Schema(
                    {
                        vol.Optional(
                            CONF_MIN_CYCLE_POWER,
                            default=entry.options.get(
                                CONF_MIN_CYCLE_POWER, DEFAULT_MIN_CYCLE_POWER
                            ),
                        ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=22)),
                        vol.Optional(
                            CONF_MIN_CYCLE_SECONDS,
                            default=entry.options.get(
                                CONF_MIN_CYCLE_SECONDS, DEFAULT_MIN_CYCLE_SECONDS
                            ),
                        ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
                        vol.Optional(
                            CONF_NOISE_FLOOR,
                            default=entry.options.get(
                                CONF_NOISE_FLOOR, DEFAULT_NOISE_FLOOR
                            ),
                        ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=5.0)),
                    }
                ),
                {"collapsed": True},
            ),
            vol.Optional("notify"): section(notify_schema(entry), {"collapsed": True}),
            vol.Optional(
                CONF_GRID_PRICE,
                # A suggestion, not a default: an empty field must reach us as
                # "no price" and switch the cost calculation off.
                description={
                    "suggested_value": entry.options.get(
                        CONF_GRID_PRICE, DEFAULT_GRID_PRICE
                    )
                },
            ): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0, max=10))),
            vol.Optional(
                CONF_PV_PRICE,
                description={
                    "suggested_value": entry.options.get(
                        CONF_PV_PRICE, DEFAULT_PV_PRICE
                    )
                },
            ): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0, max=10))),
        }
    )
