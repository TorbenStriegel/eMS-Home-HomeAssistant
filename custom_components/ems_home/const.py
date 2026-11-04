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
CONF_PV_POWER_ENTITY = "pv_power_entity"
CONF_BATTERY_POWER_ENTITY = "battery_power_entity"
CONF_MIN_CYCLE_POWER = "min_cycle_power"
CONF_MIN_CYCLE_SECONDS = "min_cycle_seconds"
CONF_NOISE_FLOOR = "noise_floor"
CONF_GRID_PRICE = "grid_price"
CONF_PV_PRICE = "pv_price"

# Defaults
DEFAULT_PORT = 80
CONF_DEBUG_LOGGING = "debug_logging"
DEFAULT_DEBUG_LOGGING = False

DEFAULT_SCAN_INTERVAL = 20   # seconds – the streams carry the live values
DEFAULT_TIMEOUT = 10         # seconds per HTTP request
DEFAULT_MIN_CYCLE_POWER = 1.0    # kW – below this a charge does not count
DEFAULT_MIN_CYCLE_SECONDS = 180  # s  – and it has to last this long
DEFAULT_NOISE_FLOOR = 0.35       # kW – nothing is integrated below this
DEFAULT_GRID_PRICE = 0.35    # €/kWh – default tariff for the cost sensors
DEFAULT_PV_PRICE = 0.0       # €/kWh – value of own solar energy
MIN_SCAN_INTERVAL = 3
MAX_SCAN_INTERVAL = 600

# hass.data layout
DATA_COORDINATOR = "coordinator"

# Frontend
STATIC_URL_PATH = "/ems_home_static"
CARD_FILENAME = "ems-home-card.js"
CARD_URL = f"{STATIC_URL_PATH}/{CARD_FILENAME}"

PLATFORMS = ["sensor", "binary_sensor", "select", "number"]
