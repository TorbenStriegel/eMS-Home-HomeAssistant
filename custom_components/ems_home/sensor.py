import asyncio
import base64
import aiohttp
import websockets
from homeassistant.helpers.entity import Entity
from .const import CONF_HOST, CONF_PASSWORD
from .obis_mapping import OBIS_MAPPING, decode_obis_key
from . import smart_meter_pb2

# Token-Cache
TOKEN = None
TOKEN_EXPIRY = 0

async def get_bearer_token(host: str, password: str):
    """Fetch Bearer token and cache it for 1 hour."""
    global TOKEN, TOKEN_EXPIRY

    loop = asyncio.get_running_loop()
    now = loop.time()

    if TOKEN and TOKEN_EXPIRY - 10 > now:
        return TOKEN

    url = f"http://{host}/api/web-login/token"
    data = {
        "grant_type": "password",
        "client_id": "emos",
        "client_secret": "56951025",
        "username": "root",
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
            try:
                resp_json = await resp.json()
            except Exception:
                raise ConnectionError(f"Invalid response from {host}")

            if resp.status != 200:
                raise PermissionError(f"Authentication failed for host {host}")

            if "access_token" not in resp_json:
                raise KeyError(f"No access_token returned. Response: {resp_json}")

            TOKEN = resp_json["access_token"]
            TOKEN_EXPIRY = now + 3600
            return TOKEN


def process_message(byte_data: bytes):
    """Parse WebSocket message and return dict of readable OBIS values."""
    gdrs_message = smart_meter_pb2.GDRs()
    gdrs_message.ParseFromString(byte_data)
    all_values = {}

    for key, gdr in gdrs_message.GDRs.items():
        for k, v in gdr.values.items():
            obis = decode_obis_key(k)
            readable_name = OBIS_MAPPING.get(obis, obis)
            all_values[readable_name] = v

    return all_values


async def async_setup_entry(hass, entry):
    """Set up sensor platform from config entry and create one entity per OBIS value."""
    host = entry.data[CONF_HOST]
    password = entry.data[CONF_PASSWORD]

    # Validate connection
    try:
        await get_bearer_token(host, password)
    except (ConnectionError, PermissionError, KeyError) as e:
        raise Exception(f"Connection failed: {e}")

    sensors = []
    for name in OBIS_MAPPING.values():
        sensors.append(EMSHomeSensor(hass, host, password, name))

    # Store sensors in hass.data to keep references
    hass.data.setdefault("ems_home_sensors", []).extend(sensors)

    # Add all sensors to HA
    for sensor in sensors:
        hass.async_create_task(hass.helpers.entity_platform.async_add_entities([sensor]))

    return True


class EMSHomeSensor(Entity):
    """Single eMS Home sensor representing one OBIS value."""

    def __init__(self, hass, host, password, name):
        self.hass = hass
        self.host = host
        self.password = password
        self._name = name
        self._state = None
        self._available = False

        # Start WebSocket update loop
        self.hass.loop.create_task(self._update_loop())

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def available(self):
        return self._available

    async def _update_loop(self):
        """Listen to WebSocket and update sensor state continuously."""
        uri = f"ws://{self.host}/api/data-transfer/ws/protobuf/gdr/local/values/smart-meter"

        while True:
            try:
                token = await get_bearer_token(self.host, self.password)
                headers = [("Origin", f"http://{self.host}"), ("User-Agent", "Mozilla/5.0")]

                async with websockets.connect(uri, extra_headers=headers) as ws:
                    await ws.send(f"Bearer {token}")

                    async for message in ws:
                        if isinstance(message, str):
                            message = base64.b64decode(message.strip())

                        values = process_message(message)
                        if self._name in values:
                            self._state = values[self._name]
                            self._available = True
                            self.async_write_ha_state()
            except Exception:
                self._available = False
                self.async_write_ha_state()
                await asyncio.sleep(10)
