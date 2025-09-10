"""Config flow for eMS Home integration."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from aiohttp import ClientConnectorError
import aiohttp

from .const import DOMAIN, CONF_HOST, CONF_PASSWORD
from .sensor import get_bearer_token

class EMSHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for eMS Home."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_user(self, user_input=None):
        """Handle the initial step of the config flow."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            password = user_input[CONF_PASSWORD]

            # Validate connection by fetching Bearer token
            try:
                await get_bearer_token(host, password)
            except ClientConnectorError:
                errors["base"] = "cannot_connect"
            except (PermissionError, KeyError):
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"

            if not errors:
                # Successful connection
                user_input["username"] = "root"  # username is always root
                return self.async_create_entry(
                    title=f"eMS Home @ {host}",
                    data=user_input
                )

        # Show form to ask for host and password
        data_schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PASSWORD): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors
        )
