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
CONF_HISTORY_ENABLED = "history_enabled"
CONF_HISTORY_RETENTION_MONTHS = "history_retention_months"
DEFAULT_HISTORY_ENABLED = True
DEFAULT_HISTORY_RETENTION_MONTHS = 60

# Defaults
DEFAULT_PORT = 80
CONF_VEHICLE_ENTITY = "vehicle_entity"
CONF_NOTIFY_ENABLED = "notify_enabled"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_NOTIFY_ON_START = "notify_on_start"
CONF_NOTIFY_ON_FINISH = "notify_on_finish"
CONF_NOTIFY_VEHICLE = "notify_vehicle_entity"
CONF_NOTIFY_TEST = "notify_test"
#: Switch the wallbox to "lock" when a charge ends (optional, off by default).
CONF_LOCK_AFTER_CHARGE = "lock_after_charge"
DEFAULT_NOTIFY_ON_START = False
DEFAULT_NOTIFY_ON_FINISH = True
DEFAULT_LOCK_AFTER_CHARGE = False

CONF_NOTIFY_CHANNEL = "notify_channel"
CONF_NOTIFY_IMPORTANCE = "notify_importance"
CONF_NOTIFY_TAG = "notify_tag"
CONF_NOTIFY_ICON = "notify_icon"
DEFAULT_NOTIFY_CHANNEL = "eMS Home"
DEFAULT_NOTIFY_IMPORTANCE = "default"
DEFAULT_NOTIFY_TAG = "ems_home_charge"
DEFAULT_NOTIFY_ICON = "mdi:ev-station"
#: Android importance levels the companion app understands.
NOTIFY_IMPORTANCE_OPTIONS = ["min", "low", "default", "high", "max"]
#: Suggested channels – the field stays a dropdown, new names can still be typed.
NOTIFY_CHANNEL_OPTIONS = ["eMS Home", "Auto", "Wallbox", "Solar", "Strom"]

CONF_IDLE_END_SECONDS = "idle_end_seconds"
DEFAULT_IDLE_END_SECONDS = 300  # s without any flow -> the charge is over

#: Optional automatic charge release (one-shot: arm, release once, observe).
CONF_AUTO_CHARGE_ENABLED = "auto_charge_enabled"
CONF_AUTO_SURPLUS_ENTITY = "auto_surplus_entity"
CONF_AUTO_SOC_ENTITY = "auto_soc_entity"
CONF_AUTO_GUARD_ENTITY = "auto_guard_entity"
DEFAULT_AUTO_CHARGE_ENABLED = False

#: The six thresholds live in the entry options (Configure), not as entities.
CONF_AUTO_SURPLUS_START = "auto_surplus_start_w"
CONF_AUTO_SURPLUS_HOLD = "auto_surplus_hold_s"
CONF_AUTO_SOC_FULL = "auto_soc_full_pct"
CONF_AUTO_SOC_MIN = "auto_soc_min_pct"
CONF_AUTO_TARGET = "auto_target_mode"
CONF_AUTO_NO_VEHICLE = "auto_no_vehicle_policy"
AUTO_SETTING_KEYS = (
    CONF_AUTO_SURPLUS_START,
    CONF_AUTO_SURPLUS_HOLD,
    CONF_AUTO_SOC_FULL,
    CONF_AUTO_SOC_MIN,
    CONF_AUTO_TARGET,
    CONF_AUTO_NO_VEHICLE,
)

#: Where a release may point to. "grid" would defeat the purpose, "lock" is no release.
AUTO_TARGET_MODES = ("pv", "hybrid")
AUTO_NO_VEHICLE_POLICIES = ("wait", "allow_release")
AUTO_CHARGE_STATES = (
    "off",
    "arming",
    "armed",
    "waiting_soc",
    "waiting_surplus",
    "blocked_no_vehicle",
    "starting",
    "released",
    "charging",
    "finished",
    "degraded_unavailable",
    "conflict_external",
)
DEFAULT_AUTO_SURPLUS_START_W = 4000.0
DEFAULT_AUTO_SURPLUS_HOLD_S = 120
DEFAULT_AUTO_SOC_FULL_PCT = 99
DEFAULT_AUTO_SOC_MIN_PCT = 90
DEFAULT_AUTO_TARGET_MODE = "hybrid"
DEFAULT_AUTO_NO_VEHICLE = "wait"

CONF_DEBUG_LOGGING = "debug_logging"
DEFAULT_DEBUG_LOGGING = False

DEFAULT_SCAN_INTERVAL = 20   # seconds – the streams carry the live values
DEFAULT_TIMEOUT = 10         # seconds per HTTP request
DEFAULT_MIN_CYCLE_POWER = 1.0    # kW – below this a charge does not count
DEFAULT_MIN_CYCLE_SECONDS = 60  # s  – and it has to last this long
DEFAULT_NOISE_FLOOR = 0.35       # kW – nothing is integrated below this
DEFAULT_GRID_PRICE = 0.35    # €/kWh – default tariff for the cost sensors
DEFAULT_PV_PRICE = 0.0       # €/kWh – value of own solar energy
MIN_SCAN_INTERVAL = 3
MAX_SCAN_INTERVAL = 600

# hass.data layout
DATA_COORDINATOR = "coordinator"
DATA_AUTO_CHARGE = "auto_charge"

# Frontend
STATIC_URL_PATH = "/ems_home_static"
CARD_FILENAME = "ems-home-card.js"
CARD_URL = f"{STATIC_URL_PATH}/{CARD_FILENAME}"

PLATFORMS = ["sensor", "binary_sensor", "select", "number", "button", "switch"]
