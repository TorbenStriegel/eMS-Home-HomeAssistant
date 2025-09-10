import asyncio
import base64
import time
import aiohttp
import websockets
from homeassistant.helpers.entity import Entity
from .const import DOMAIN, CONF_HOST, CONF_PASSWORD
from .obis_mapping import OBIS_MAPPING
from google.protobuf.json_format import MessageToDict
import smart_meter_pb2

# Global token cache
TOKEN = None
TOKEN_EXPIRY = 0

async def get_bearer_token(host: str, password: str):
    """Fetch a Bearer token and cache it for 1 hour."""
    global TOKEN, TOKEN_EXPIRY

    if TOKEN and time.time() < TOKEN_EXPIRY - 10:
        return TOKEN

    url = f"http://{host}/api/web-login/token"
    data = {
        "grant_type": "password",
        "client_id": "emos",
        "client_secret": "56951025",
        "username": "root",
        "password": password
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": f"http://{host}",
        "Referer": f"http://{host}/login",
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data, headers=headers, ssl=False) as resp:
            resp_json = await resp.json()
            TOKEN = resp_json["access_token"]
            TOKEN_EXPIRY = time.time() + 3600
            return TOKEN

def decode_obis_key(key: int):
    """Decode integer OBIS key to human-readable format."""
    t = [0]*8
    e = key
    for r in range(8):
        n = e & 0xFF
        t[7-r] = n
        e = (e-n)//256
    t = t[2:]
    Media, Channel, Indicator, Mode, Quantities, Storage = t
    return f"{Media}-{Channel}:{Indicator}.{Mode}.{Quantities}*{Storage}"

def process_message(byte_data: bytes):
    """Parse WebSocket message and extract OBIS values."""
    gdrs_message = smart_meter_pb2.GDRs()
    gdrs_message.ParseFromString(byte_data)

    result = {}
    for key, gdr in gdrs_message.GDRs.items():
        for k, v in gdr.values.items():
            obis = decode_obis_key(k)
            readable_name = OBIS_MAPPING.get(obis, obis)
            result[readable_name] = v
    return result

class EMSHomeSensor(Entity):
    """Representation of a eMS Home sensor in Home Assistant."""

    def __init__(self, hass, config_entry):
        self.hass = hass
        self.host = config_entry.data[CONF_HOST]
        self.password = config_entry.data[CONF_PASSWORD]
        self._state = None
        self._data = {}

    @property
    def name(self):
        return "eMS Home Sensor"

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._data

    async def async_added_to_hass(self):
        """Start WebSocket listener when added to HA."""
        self.hass.loop.create_task(self.listen_ws())

    async def listen_ws(self):
        """Connect to WebSocket and continuously update data."""
        uri = f"ws://{self.host}/api/data-transfer/ws/protobuf/gdr/local/values/smart-meter"

        while True:
            try:
                token = await get_bearer_token(self.host, self.password)
                headers = [
                    ("Origin", f"http://{self.host}"),
                    ("User-Agent", "Mozilla/5.0"),
                ]

                async with websockets.connect(uri, extra_headers=headers) as ws:
                    await ws.send(f"Bearer {token}")

                    async for message in ws:
                        if isinstance(message, str):
                            message = base64.b64decode(message.strip())
                        self._data = process_message(message)
                        if "Total active energy import" in self._data:
                            self._state = self._data["Total active energy import"]
                        self.async_write_ha_state()

            except Exception as e:
                print(f"WebSocket error: {e}. Reconnecting in 10 seconds...")
                await asyncio.sleep(10)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up eMS Home sensors."""
    sensor = EMSHomeSensor(hass, entry)
    async_add_entities([sensor])
