"""Constants for the eMS Home integration."""

DOMAIN = "ems_home"

# Config entry / options keys
CONF_HOST = "host"
CONF_PASSWORD = "password"
CONF_PORT = "port"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_TIMEOUT = "timeout"
CONF_ENABLE_SMART_METER = "enable_smart_meter_stream"
CONF_ENABLE_EVSE = "enable_evse_stream"

# Defaults
DEFAULT_PORT = 80
DEFAULT_SCAN_INTERVAL = 10   # seconds
DEFAULT_TIMEOUT = 10         # seconds per HTTP request
MIN_SCAN_INTERVAL = 3
MAX_SCAN_INTERVAL = 600

# hass.data layout
DATA_COORDINATOR = "coordinator"

# Frontend
STATIC_URL_PATH = "/ems_home_static"
CARD_FILENAME = "ems-home-card.js"
CARD_URL = f"{STATIC_URL_PATH}/{CARD_FILENAME}"

PLATFORMS = ["sensor", "binary_sensor", "select", "number"]
