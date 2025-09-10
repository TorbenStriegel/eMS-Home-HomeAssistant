import asyncio
import base64
import aiohttp
import websockets
from homeassistant.helpers.entity import Entity
from .const import CONF_HOST, CONF_PASSWORD
from .obis_mapping import OBIS_MAPPING, decode_obis_key
from . import smart_meter_pb2

# ------------------------------
# Global token cache per host
# ------------------------------
TOKEN_CACHE = {}  # host -> {"token": str, "expiry": float}

# ------------------------------
# Global WebSocket management
# ------------------------------
WS_TASKS = {}  # host -> {"task": asyncio.Task, "sensors": [Entity]}
WS_DATA = {}   # host -> latest values

# ------------------------------
# Fetch Bearer token
# ------------------------------
async def get_bearer_token(host: str, password: str):
    """Fetch Bearer token per host and cache it for 1 hour."""
    loop = asyncio.get_running_loop()
    now = loop.time()

    if host in TOKEN_CACHE:
        token_info = TOKEN_CACHE[host]
        if token_info["expiry"] - 10 > now:
            return token_info["token"]

    url = f"http://{host}/api/web-login/token"
    data = {
        "grant_type": "password",
        "client_id": "emos",
        "client_secret": "56951025",
        "username": "admin",
        "password": password,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": f"http://{host}",
        "Referer": f"http://{host}/login",
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data, headers=headers, ssl=False) as resp:
            resp_json = await resp.json()
            if resp.status != 200:
                raise PermissionError(f"Authentication failed for host {host}")
            if "access_token" not in resp_json:
                raise KeyError(f"No access_token returned. Response: {resp_json}")
            token = resp_json["access_token"]
            TOKEN_CACHE[host] = {"token": token, "expiry": now + 3600}
            return token

# ------------------------------
# Process WebSocket message
# ------------------------------
def process_message(byte_data: bytes):
    """Parse WebSocket message and return dictionary of readable OBIS values."""
    gdrs_message = smart_meter_pb2.GDRs()
    gdrs_message.ParseFromString(byte_data)
    all_values = {}

    for key, gdr in gdrs_message.GDRs.items():
        for k, v in gdr.values.items():
            obis = decode_obis_key(k)
            readable_name = OBIS_MAPPING.get(obis, obis)
            all_values[readable_name] = v

    return all_values

# ------------------------------
# WebSocket listener per host
# ------------------------------
async def ws_listener(hass, host: str, password: str):
    """Single WebSocket listener per host, updates shared WS_DATA."""
    uri = f"ws://{host}/api/data-transfer/ws/protobuf/gdr/local/values/smart-meter"

    while True:
        try:
            token = await get_bearer_token(host, password)
            headers = [("Origin", f"http://{host}"), ("User-Agent", "Mozilla/5.0")]

            async with websockets.connect(uri, extra_headers=headers) as ws:
                await ws.send(f"Bearer {token}")

                async for message in ws:
                    if isinstance(message, str):
                        message = base64.b64decode(message.strip())
                    WS_DATA[host] = process_message(message)

                    # Update all sensors for this host
                    if host in WS_TASKS:
                        for sensor in WS_TASKS[host]["sensors"]:
                            if sensor._name in WS_DATA[host]:
                                sensor._state = WS_DATA[host][sensor._name]
                                sensor._available = True
                                sensor.async_write_ha_state()
        except Exception:
            # Mark sensors unavailable if WebSocket fails
            if host in WS_TASKS:
                for sensor in WS_TASKS[host]["sensors"]:
                    sensor._available = False
                    sensor.async_write_ha_state()
            await asyncio.sleep(10)

# ------------------------------
# Setup sensors from config entry
# ------------------------------
async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sensor platform from config entry."""
    host = entry.data[CONF_HOST]
    password = entry.data[CONF_PASSWORD]

    # Validate connection by fetching token
    try:
        await get_bearer_token(host, password)
    except (ConnectionError, PermissionError, KeyError) as e:
        raise Exception(f"Connection failed: {e}")

    # Create sensors (one per OBIS value)
    sensors = [EMSHomeSensor(host, name) for name in OBIS_MAPPING.values()]

    # Start WS listener if not already running
    if host not in WS_TASKS:
        task = hass.loop.create_task(ws_listener(hass, host, password))
        WS_TASKS[host] = {"task": task, "sensors": sensors}
    else:
        WS_TASKS[host]["sensors"].extend(sensors)

    hass.data.setdefault("ems_home_sensors", []).extend(sensors)
    async_add_entities(sensors)

    return True

# ------------------------------
# Unload entry
# ------------------------------
async def async_unload_entry(hass, entry):
    """Unload a config entry and stop WS listener."""
    host = entry.data[CONF_HOST]

    if host in WS_TASKS:
        WS_TASKS[host]["task"].cancel()
        for sensor in WS_TASKS[host]["sensors"]:
            sensor._available = False
            sensor.async_write_ha_state()
        WS_TASKS.pop(host)
        WS_DATA.pop(host, None)
        TOKEN_CACHE.pop(host, None)

    return True

# ------------------------------
# EMS Home sensor entity
# ------------------------------
class EMSHomeSensor(Entity):
    """Single eMS Home sensor representing one OBIS value."""

    def __init__(self, host, name):
        self._host = host
        self._name = name
        self._state = None
        self._available = False

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def available(self):
        return self._available
