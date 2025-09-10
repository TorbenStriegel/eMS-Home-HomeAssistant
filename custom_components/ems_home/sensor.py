"""Sensor platform for eMS Home integration."""

import asyncio
import base64
import time
import aiohttp
import websockets
from homeassistant.helpers.entity import Entity
from .const import CONF_HOST, CONF_PASSWORD
from .obis_mapping import OBIS_MAPPING
from . import smart_meter_pb2

# Token caching
TOKEN = None
TOKEN_EXPIRY = 0

async def get_bearer_token(host: str, password: str):
    """Fetch Bearer token (cached 1 hour)."""
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
    """Decode integer OBIS key to readable string."""
    t = [0] * 8
    e = key
    for r in range(8):
        n = e & 0xFF
        t[7 - r] = n
        e = (e - n) // 256
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

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sensor entities from config entry."""
    host = entry.data[CONF_HOST]
    password = entry.data[CONF_PASSWORD]

    token = await get_bearer_token(host, password)
    uri = f"ws://{host}/api/data-transfer/ws/protobuf/gdr/local/values/smart-meter"

    async with websockets.connect(uri, extra_headers=[("Authorization", f"Bearer {token}")]) as ws:
        # Receive first message to get keys
        message = await ws.recv()
        if isinstance(message, str):
            message = base64.b64decode(message.strip())
        data = process_message(message)

    # Create a sensor for each OBIS value
    entities = [EMSHomeSingleSensor(host, password, name) for name in data.keys()]
    async_add_entities(entities)

    # Start background task to update all sensors
    asyncio.create_task(update_sensors(host, password, entities))

async def update_sensors(host, password, entities):
    uri = f"ws://{host}/api/data-transfer/ws/protobuf/gdr/local/values/smart-meter"
    while True:
        try:
            token = await get_bearer_token(host, password)
            async with websockets.connect(uri, extra_headers=[("Authorization", f"Bearer {token}")]) as ws:
                async for message in ws:
                    if isinstance(message, str):
                        message = base64.b64decode(message.strip())
                    data = process_message(message)
                    for entity in entities:
                        if entity.name in data:
                            entity._state = data[entity.name]
                            entity.async_write_ha_state()
        except Exception as e:
            print(f"WebSocket error: {e}, reconnecting in 10s")
            await asyncio.sleep(10)

class EMSHomeSingleSensor(Entity):
    """Single OBIS sensor."""

    def __init__(self, host, password, name):
        self.host = host
        self.password = password
        self.name = name
        self._state = None

    @property
    def state(self):
        return self._state

    @property
    def unique_id(self):
        return f"ems_home_{self.name.replace(' ', '_').lower()}"
