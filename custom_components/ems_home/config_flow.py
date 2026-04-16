"""Config flow for eMS Home integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)


def _try_login(host: str, password: str, port: int) -> str | None:
    """Attempt to authenticate. Returns None on success, or an error key."""
    try:
        from .ems_home_api import EMSHomeHTTP
        ems = EMSHomeHTTP(host, password, port=port, use_https=(port == 443), verify_ssl=False)
        ems.login()
        ems.logout()
        return None
    except Exception as exc:
        msg = str(exc).lower()
        if "401" in msg or "403" in msg or "invalid" in msg or "unauthorized" in msg:
            return "invalid_auth"
        return "cannot_connect"


class EMSHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration UI flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host     = user_input[CONF_HOST].strip()
            password = user_input[CONF_PASSWORD]
            port     = user_input.get(CONF_PORT, DEFAULT_PORT)

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            error = await self.hass.async_add_executor_job(
                _try_login, host, password, port
            )
            if error is None:
                return self.async_create_entry(
                    title=f"eMS Home ({host})",
                    data={
                        CONF_HOST:          host,
                        CONF_PASSWORD:      password,
                        CONF_PORT:          port,
                        CONF_SCAN_INTERVAL: user_input.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    },
                )
            errors["base"] = error

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(int, vol.Range(min=3, max=300)),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EMSHomeOptionsFlow(config_entry)


class EMSHomeOptionsFlow(config_entries.OptionsFlow):
    """Allow the user to change the poll interval after setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=current_interval): vol.All(
                    int, vol.Range(min=3, max=300)
                )
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

