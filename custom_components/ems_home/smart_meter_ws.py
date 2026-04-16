"""
eMS Home – Smart Meter WebSocket client.

Connects to ws://<host>/api/data-transfer/ws/protobuf/gdr/local/values/smart-meter
and decodes the binary protobuf frames into a SmartMeterReading dataclass.
Uses only stdlib asyncio — no external websockets library required.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import struct
from dataclasses import dataclass
from typing import Callable, Optional

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Channel ID constants
# ---------------------------------------------------------------------------

CH_POWER_TOTAL      = 0x100010400FF
CH_POWER_APPARENT   = 0x100090400FF
CH_POWER_L1         = 0x100150400FF
CH_POWER_L2         = 0x100290400FF
CH_POWER_L3         = 0x1003D0400FF
CH_APPARENT_L1      = 0x1001D0400FF
CH_APPARENT_L2      = 0x100310400FF
CH_APPARENT_L3      = 0x100450400FF
CH_VOLTAGE_L1       = 0x100200400FF
CH_VOLTAGE_L2       = 0x100340400FF
CH_VOLTAGE_L3       = 0x100480400FF
CH_CURRENT_L1       = 0x1001F0400FF
CH_CURRENT_L2       = 0x100330400FF
CH_CURRENT_L3       = 0x100470400FF
CH_FREQUENCY        = 0x1000E0400FF
CH_ENERGY_TOTAL     = 0x100010800FF

# Additional channels identified from real device data
CH_POWER_EXPORT     = 0x100020400FF   # Active power export total (W)
CH_REACTIVE_POWER   = 0x100030400FF   # Reactive power total (var)
CH_ENERGY_EXPORT    = 0x100020800FF   # Energy export total (kWh)
CH_REACTIVE_IMPORT  = 0x100030800FF   # Reactive energy import (kvarh)
CH_POWER_FACTOR     = 0x1000D0400FF   # Power factor (cos φ)
CH_POWER_FACTOR_L1  = 0x100210400FF   # Power factor L1
CH_POWER_FACTOR_L2  = 0x100350400FF   # Power factor L2
CH_POWER_FACTOR_L3  = 0x100490400FF   # Power factor L3
CH_REACTIVE_L1      = 0x100180400FF   # Reactive power L1 (var)
CH_REACTIVE_L2      = 0x1002C0400FF   # Reactive power L2 (var)
CH_REACTIVE_L3      = 0x100400400FF   # Reactive power L3 (var)


@dataclass
class SmartMeterReading:
    """Decoded smart meter snapshot from one WebSocket frame."""
    power_total:    float = 0.0
    power_l1:       float = 0.0
    power_l2:       float = 0.0
    power_l3:       float = 0.0
    power_apparent: float = 0.0
    apparent_l1:    float = 0.0
    apparent_l2:    float = 0.0
    apparent_l3:    float = 0.0
    voltage_l1:     float = 0.0
    voltage_l2:     float = 0.0
    voltage_l3:     float = 0.0
    current_l1:     float = 0.0
    current_l2:     float = 0.0
    current_l3:     float = 0.0
    frequency:      float = 0.0
    energy_total:   float = 0.0
    # Additional fields
    power_export:   float = 0.0     # W (active power export)
    energy_export:  float = 0.0     # kWh (energy export total)
    reactive_power: float = 0.0     # var (reactive power total)
    reactive_l1:    float = 0.0     # var
    reactive_l2:    float = 0.0     # var
    reactive_l3:    float = 0.0     # var
    power_factor:   float = 0.0     # cos φ (total)
    power_factor_l1: float = 0.0
    power_factor_l2: float = 0.0
    power_factor_l3: float = 0.0
    timestamp:      float = 0.0

    @property
    def power_total_kw(self) -> float:
        return round(self.power_total / 1000, 3)


# ---------------------------------------------------------------------------
# Minimal protobuf decoder
# ---------------------------------------------------------------------------

def _decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    result, shift = 0, 0
    while True:
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def _decode_fields(data: bytes) -> list:
    pos, fields = 0, []
    while pos < len(data):
        try:
            tag, pos = _decode_varint(data, pos)
        except IndexError:
            break
        fn, wt = tag >> 3, tag & 7
        if wt == 0:
            v, pos = _decode_varint(data, pos)
            fields.append((fn, wt, v))
        elif wt == 2:
            l, pos = _decode_varint(data, pos)
            fields.append((fn, wt, data[pos: pos + l]))
            pos += l
        elif wt == 5:
            v = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            fields.append((fn, wt, v))
        else:
            break
    return fields


def decode_smart_meter_frame(raw: bytes) -> Optional[SmartMeterReading]:
    try:
        outer = _decode_fields(raw)
        wrapper_bytes = next((v for fn, wt, v in outer if fn == 1 and wt == 2), None)
        if wrapper_bytes is None:
            return None
        wrapper = _decode_fields(wrapper_bytes)
        payload_bytes = next((v for fn, wt, v in wrapper if fn == 2 and wt == 2), None)
        if payload_bytes is None:
            return None

        reading = SmartMeterReading()
        for fn, wt, v in _decode_fields(payload_bytes):
            if fn == 3 and wt == 2:
                tsf = _decode_fields(v)
                sec = next((val for f, _, val in tsf if f == 1), 0)
                ns  = next((val for f, _, val in tsf if f == 2), 0)
                reading.timestamp = sec + ns / 1e9
            elif fn == 4 and wt == 2:
                dp    = _decode_fields(v)
                ch_id = next((val for f, _, val in dp if f == 1), None)
                raw_v = next((val for f, _, val in dp if f == 2), None)
                if ch_id is not None and raw_v is not None:
                    _apply_channel(reading, ch_id, raw_v)
        return reading
    except Exception as exc:
        _LOGGER.debug("Failed to decode smart meter frame: %s", exc)
        return None


def _apply_channel(reading: SmartMeterReading, ch_id: int, raw: int) -> None:
    if   ch_id == CH_POWER_TOTAL:    reading.power_total    = raw / 1000
    elif ch_id == CH_POWER_APPARENT: reading.power_apparent = raw / 1000
    elif ch_id == CH_POWER_L1:       reading.power_l1       = raw / 1000
    elif ch_id == CH_POWER_L2:       reading.power_l2       = raw / 1000
    elif ch_id == CH_POWER_L3:       reading.power_l3       = raw / 1000
    elif ch_id == CH_APPARENT_L1:    reading.apparent_l1    = raw / 1000
    elif ch_id == CH_APPARENT_L2:    reading.apparent_l2    = raw / 1000
    elif ch_id == CH_APPARENT_L3:    reading.apparent_l3    = raw / 1000
    elif ch_id == CH_VOLTAGE_L1:     reading.voltage_l1     = raw / 1000
    elif ch_id == CH_VOLTAGE_L2:     reading.voltage_l2     = raw / 1000
    elif ch_id == CH_VOLTAGE_L3:     reading.voltage_l3     = raw / 1000
    elif ch_id == CH_CURRENT_L1:     reading.current_l1     = raw / 1000
    elif ch_id == CH_CURRENT_L2:     reading.current_l2     = raw / 1000
    elif ch_id == CH_CURRENT_L3:     reading.current_l3     = raw / 1000
    elif ch_id == CH_FREQUENCY:      reading.frequency      = raw / 1000
    elif ch_id == CH_ENERGY_TOTAL:   reading.energy_total   = raw / 1e6
    # Additional channels
    elif ch_id == CH_POWER_EXPORT:   reading.power_export   = raw / 1000
    elif ch_id == CH_ENERGY_EXPORT:  reading.energy_export  = raw / 1e6
    elif ch_id == CH_REACTIVE_POWER: reading.reactive_power = raw / 1000
    elif ch_id == CH_REACTIVE_L1:    reading.reactive_l1    = raw / 1000
    elif ch_id == CH_REACTIVE_L2:    reading.reactive_l2    = raw / 1000
    elif ch_id == CH_REACTIVE_L3:    reading.reactive_l3    = raw / 1000
    elif ch_id == CH_POWER_FACTOR:   reading.power_factor   = raw / 1000
    elif ch_id == CH_POWER_FACTOR_L1: reading.power_factor_l1 = raw / 1000
    elif ch_id == CH_POWER_FACTOR_L2: reading.power_factor_l2 = raw / 1000
    elif ch_id == CH_POWER_FACTOR_L3: reading.power_factor_l3 = raw / 1000


# ---------------------------------------------------------------------------
# Raw asyncio WebSocket helpers
# ---------------------------------------------------------------------------

async def _ws_open(host: str, port: int, path: str, auth_token: str):
    import ssl as _ssl
    if port == 443:
        sc = _ssl.create_default_context()
        sc.check_hostname = False
        sc.verify_mode = _ssl.CERT_NONE
        reader, writer = await asyncio.open_connection(host, port, ssl=sc)
    else:
        reader, writer = await asyncio.open_connection(host, port)
    key = base64.b64encode(os.urandom(16)).decode()
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"Authorization: Bearer {auth_token}\r\n"
        f"\r\n"
    )
    writer.write(request.encode())
    await writer.drain()

    response = b""
    while b"\r\n\r\n" not in response:
        chunk = await reader.read(4096)
        if not chunk:
            raise ConnectionError("Connection closed during WebSocket handshake")
        response += chunk

    status_line = response.split(b"\r\n")[0].decode()
    if "101" not in status_line:
        raise ConnectionError(f"WebSocket upgrade failed: {status_line}")

    return reader, writer


def _send_ws_text(writer, text: str) -> None:
    payload = text.encode()
    mask_key = os.urandom(4)
    masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    length = len(payload)
    if length < 126:
        header = bytes([0x81, 0x80 | length])
    else:
        header = bytes([0x81, 0xFE]) + struct.pack(">H", length)
    writer.write(header + mask_key + masked)


async def _ws_recv_frame(reader) -> bytes:
    header = await reader.readexactly(2)
    opcode  = header[0] & 0x0F
    masked  = (header[1] & 0x80) != 0
    length  = header[1] & 0x7F

    if length == 126:
        length = struct.unpack(">H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", await reader.readexactly(8))[0]

    mask_key = await reader.readexactly(4) if masked else b""
    payload  = await reader.readexactly(length)

    if masked:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

    if opcode == 0x8:
        raise ConnectionError("Server sent WebSocket close frame")
    if opcode in (0x9, 0xA):
        return await _ws_recv_frame(reader)

    return payload


async def _ws_close(writer) -> None:
    try:
        writer.write(b"\x88\x80" + os.urandom(4))
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Async WebSocket client
# ---------------------------------------------------------------------------

WS_PATH = "/api/data-transfer/ws/protobuf/gdr/local/values/smart-meter"


class SmartMeterWebSocket:
    """Persistent WebSocket connection with auto-reconnect."""

    def __init__(
        self,
        host: str,
        token: str,
        on_reading: Callable[[SmartMeterReading], None],
        port: int = 80,
    ) -> None:
        self._host     = host
        self._port     = port
        self._token    = token
        self._callback = on_reading
        self._task: Optional[asyncio.Task] = None
        self._running  = False

    def update_token(self, token: str) -> None:
        self._token = token

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        delay = 1.0
        while self._running:
            try:
                await self._connect_and_listen()
                delay = 1.0
            except asyncio.CancelledError:
                break
            except Exception as exc:
                _LOGGER.warning(
                    "Smart meter WebSocket error (%s), reconnecting in %.0fs", exc, delay
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60.0)

    async def _connect_and_listen(self) -> None:
        reader, writer = await _ws_open(
            self._host, self._port, WS_PATH, self._token
        )
        _LOGGER.info("Smart meter WebSocket connected")
        _send_ws_text(writer, f"Bearer {self._token}")
        await writer.drain()
        try:
            while self._running:
                payload = await _ws_recv_frame(reader)
                reading = decode_smart_meter_frame(payload)
                if reading is not None:
                    self._callback(reading)
        finally:
            await _ws_close(writer)

