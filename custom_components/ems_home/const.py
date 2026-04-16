"""Constants for the eMS Home integration."""

DOMAIN = "ems_home"

# Config entry keys
CONF_HOST           = "host"
CONF_PASSWORD       = "password"
CONF_PORT           = "port"
CONF_SCAN_INTERVAL  = "scan_interval"

# Defaults
DEFAULT_PORT          = 80
DEFAULT_SCAN_INTERVAL = 5    # seconds

# Coordinator update key stored in hass.data
DATA_COORDINATOR = "coordinator"
