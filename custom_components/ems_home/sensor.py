import asyncio
import base64
import json
import aiohttp
import websockets
from homeassistant.helpers.entity import Entity
from .const import DOMAIN, CONF_HOST, CONF_USERNAME, CONF_PASSWORD
import smart_meter_pb2
from google.protobuf.json_format import MessageToDict

OBIS_MAPPING = {
    "1-0:1.8.0*255": "Total active energy import",
    "1-0:2.8.0*255": "Total active energy export"
    # weitere Mapping-Werte hier einfügen...
}

def decode_obis_key(key: int):
    t = [0] * 8
    e = key
    for r in range(8):
        n = e & 0xFF
        t[7 - r] = n
        e = (e - n) // 256
    t = t[2:]
    Media, Channel, Indicator, Mode, Quantities, Storage = t
    return f"{Media}-{Channel}:{Indicator}.{Mode}.{Quantities}*{Storage}"

class EMSHomeSensor(Entity):
    def __init__(self, hass, name):
        self._hass = hass
        self._name = name
        self._state = None

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    async def async_update(self):
        pass

async def async_setup_entry(hass, entry, async_add_entities):
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    async_add_entities([EMSHomeSensor(hass, "eMS Home Smart Meter")])