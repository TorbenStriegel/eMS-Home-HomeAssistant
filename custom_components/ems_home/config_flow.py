"""Config flow for eMS Home integration."""

import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_HOST, CONF_PASSWORD

class EMSHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for eMS Home."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_user(self, user_input=None):
        """Handle the initial step of the config flow."""
        errors = {}

        if user_input is not None:
            # Username is always 'root'
            user_input["username"] = "root"

            # Here you could validate connection with the provided host/password
            # e.g., await self._test_connection(user_input)

            return self.async_create_entry(
                title=f"eMS Home @ {user_input['host']}",
                data=user_input
            )

        # Only ask for host and password
        data_schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PASSWORD): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors
        )
