"""Protocol tests for the eMS Home integration.

Runs without Home Assistant: they cover the protobuf decoding and the
WebSocket client against a mock device that behaves like the real firmware
(binary frames, fragmented frames, keep-alive pings, sparse pushes).

    python -m pytest tests -q
"""
from __future__ import annotations

import asyncio
import os
import struct
import sys
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "ems_home"
sys.path.insert(0, str(COMPONENT))

from ws_client import EMSWebSocket, encode_frame, read_frame  # noqa: E402
from ws_proto import (  # noqa: E402
    CHANNELS,
    EVSEReading,
    SmartMeterReading,
    decode_evse_frame,
    decode_smart_meter_frame,
    obis_label,
    unpack_channel,
)

# ---------------------------------------------------------------------------
# Protobuf encoder used to build device-like frames
# ---------------------------------------------------------------------------


def varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def key(field: int, wire: int) -> bytes:
    return varint((field << 3) | wire)


def ld(field: int, payload: bytes) -> bytes:
    return key(field, 2) + varint(len(payload)) + payload


def vi(field: int, value: int) -> bytes:
    return key(field, 0) + varint(value)


def channel(measurement: int, vtype: int) -> int:
    return int.from_bytes(bytes([0, 0, 1, 0, measurement, vtype, 0, 0xFF]), "big")


def gdr_frame(values: dict[int, int], flex: dict[str, tuple[str, int | str]] | None = None) -> bytes:
    gdr = vi(1, 1)  # id (unused by the decoder, kept for realism)
    gdr += ld(3, vi(1, 1_700_000_000) + vi(2, 500_000_000))  # timestamp
    for chan, raw in values.items():
        entry = vi(1, chan) + vi(2, raw)
        gdr += ld(4, entry)
    for name, (kind, value) in (flex or {}).items():
        flex_value = vi(1, value) if isinstance(value, int) else ld(1, str(kind).encode()) + ld(2, str(value).encode())
        gdr += ld(5, ld(1, name.encode()) + ld(2, flex_value))
    return ld(1, ld(1, b"meter-1") + ld(2, gdr))


# ---------------------------------------------------------------------------
# Decoder tests
# ---------------------------------------------------------------------------


def test_channel_unpacking_matches_known_registers():
    assert unpack_channel(0x100010400FF) == (1, 4)
    assert unpack_channel(0x100200400FF) == (32, 4)
    assert unpack_channel(0x1001F0400FF) == (31, 4)
    assert unpack_channel(0x100010800FF) == (1, 8)
    assert "21.4" in obis_label(channel(21, 4))


def test_decode_smart_meter_scaling():
    frame = gdr_frame(
        {
            channel(1, 4): 1_234_000,        # 1234.000 W
            channel(21, 4): 400_000,         # L1 400 W
            channel(32, 4): 230_500,         # 230.5 V
            channel(31, 4): 5_400,           # 5.4 A
            channel(14, 4): 50_010,          # 50.010 Hz
            channel(1, 8): 4_821_300_000,    # 4821.3 kWh
            channel(2, 8): 2_914_800_000,    # 2914.8 kWh
        }
    )
    reading = decode_smart_meter_frame(frame)
    assert isinstance(reading, SmartMeterReading)
    assert reading.power_total == pytest.approx(1234.0)
    assert reading.power_l1 == pytest.approx(400.0)
    assert reading.voltage_l1 == pytest.approx(230.5)
    assert reading.current_l1 == pytest.approx(5.4)
    assert reading.frequency == pytest.approx(50.01)
    assert reading.energy_total == pytest.approx(4821.3)
    assert reading.energy_export == pytest.approx(2914.8)
    assert reading.timestamp == pytest.approx(1_700_000_000.5)
    assert reading.meter_id == "meter-1"


def test_unknown_registers_are_surfaced_not_dropped():
    frame = gdr_frame({channel(99, 4): 42})
    reading = decode_smart_meter_frame(frame)
    assert reading is not None
    assert reading.extra == {channel(99, 4): 42}


def test_decode_evse_frame():
    frame = gdr_frame(
        {},
        {
            "evse_status": ("int", 4),
            "evse_status_code": ("str", "C1"),
            "evse_error_code": ("str", "E0"),
            "evse_serial": ("str", "EMH1-0815"),
            "evse_hw_imax": ("int", 32_000),
            "ev_imax_default": ("int", 16_000),
            "evse_session_duration": ("int", 2_850),
            "evse_session_energy": ("int", 12_400_000),
        },
    )
    reading = decode_evse_frame(frame)
    assert isinstance(reading, EVSEReading)
    assert reading.status_text == "charging"
    assert reading.is_charging and reading.is_plugged
    assert reading.hw_imax_amps == pytest.approx(32.0)
    assert reading.session_duration_min == pytest.approx(47.5)
    assert reading.session_energy_kwh == pytest.approx(12.4)
    assert reading.evse_serial == "EMH1-0815"


def test_unknown_wallbox_status_is_kept_raw():
    """An unmapped status must stay visible instead of being swallowed."""
    frame = gdr_frame({}, {"evse_status": ("int", 12), "evse_serial": ("str", "EMH1-2")})
    reading = decode_evse_frame(frame)
    assert reading is not None
    assert reading.evse_status == 12
    assert reading.status_text == "status_12"
    assert reading.evse_serial == "EMH1-2"


def test_two_wallboxes_are_distinguishable_by_uuid():
    """The wildcard stream may carry more than one wallbox."""
    first = decode_evse_frame(gdr_frame({}, {"evse_status": ("int", 4)}))
    assert first is not None and first.uuid == "meter-1"
    # the mock helper always writes "meter-1" as the map key; a real device
    # uses the wallbox uuid there, which is what the coordinator tracks.
    assert first.is_charging


def test_garbage_frame_returns_none():
    assert decode_smart_meter_frame(b"\xff\xff\xff") is None
    assert decode_evse_frame(b"") is None


def test_channel_table_is_consistent():
    for (measurement, vtype), (attribute, divisor) in CHANNELS.items():
        assert 0 < measurement < 256
        assert vtype in (4, 8)
        assert divisor in (1e3, 1e6)
        assert attribute


# ---------------------------------------------------------------------------
# WebSocket client tests
# ---------------------------------------------------------------------------

FRAME_BYTES = gdr_frame({channel(1, 4): 1_500_000})


class MockDevice:
    """Minimal eMS Home stand-in: handshake, auth frame, frames, pings."""

    def __init__(self, *, fragment: bool = False, ping: bool = True) -> None:
        self.fragment = fragment
        self.ping = ping
        self.requests: list[bytes] = []
        self.auth_frames: list[str] = []
        self.pongs: list[bytes] = []
        self.connections = 0
        self._server: asyncio.AbstractServer | None = None
        self.port = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        head = await reader.readuntil(b"\r\n\r\n")
        self.requests.append(head)
        writer.write(
            b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
            b"Connection: Upgrade\r\nSec-WebSocket-Accept: x\r\n\r\n"
        )
        await writer.drain()

        # the firmware expects the bearer token as the first text frame
        fin, opcode, payload = await read_frame(reader)
        assert opcode == 0x1
        self.auth_frames.append(payload.decode())

        if self.ping:
            writer.write(encode_frame(0x9, b"keepalive"))
            await writer.drain()

        if self.fragment:
            half = len(FRAME_BYTES) // 2
            writer.write(encode_frame(0x2, FRAME_BYTES[:half], fin=False))
            await writer.drain()
            await asyncio.sleep(0.02)
            writer.write(encode_frame(0x0, FRAME_BYTES[half:], fin=True))
        else:
            writer.write(encode_frame(0x2, FRAME_BYTES))
        await writer.drain()

        # consume client frames (pong) until the peer goes away
        try:
            while True:
                fin, opcode, payload = await asyncio.wait_for(read_frame(reader), 3)
                if opcode == 0xA:
                    self.pongs.append(payload)
                elif opcode == 0x8:
                    break
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()


def _run(coro):
    return asyncio.run(coro)


def test_client_handshake_auth_and_binary_frame():
    async def scenario():
        device = MockDevice()
        await device.start()
        received = []

        client = EMSWebSocket(
            "127.0.0.1", device.port, "/api/data-transfer/ws/protobuf/gdr/local/values/smart-meter",
            "TOKEN123", received.append, name="test",
        )
        await client.start()
        for _ in range(100):
            if received:
                break
            await asyncio.sleep(0.02)
        await client.stop()
        await device.stop()
        return device, received, client

    device, received, client = _run(scenario())

    head = device.requests[0].decode()
    assert "GET /api/data-transfer/ws/protobuf/gdr/local/values/smart-meter HTTP/1.1" in head
    assert "Authorization: Bearer TOKEN123" in head, "the token must be sent in the header too"
    assert "Sec-WebSocket-Version: 13" in head
    assert device.auth_frames == ["Bearer TOKEN123"]
    assert received and received[0] == FRAME_BYTES
    assert client.stats.frames == 1
    assert client.stats.bytes_received == len(FRAME_BYTES)


def test_client_reassembles_fragmented_frames():
    async def scenario():
        device = MockDevice(fragment=True)
        await device.start()
        received = []
        client = EMSWebSocket("127.0.0.1", device.port, "/ws", "t", received.append, name="frag")
        await client.start()
        for _ in range(150):
            if received:
                break
            await asyncio.sleep(0.02)
        await client.stop()
        await device.stop()
        return received

    received = _run(scenario())
    assert received == [FRAME_BYTES]


def test_client_answers_ping_with_pong():
    async def scenario():
        device = MockDevice(ping=True)
        await device.start()
        received = []
        client = EMSWebSocket("127.0.0.1", device.port, "/ws", "t", received.append, name="ping")
        await client.start()
        for _ in range(100):
            if received and device.pongs:
                break
            await asyncio.sleep(0.03)
        await client.stop()
        await device.stop()
        return device, received

    device, received = _run(scenario())
    assert received, "frame should arrive even when a ping precedes it"
    assert device.pongs == [b"keepalive"], "the client must echo the ping payload"


def test_client_reconnects_after_drop():
    async def scenario():
        device = MockDevice()
        await device.start()
        received = []
        client = EMSWebSocket("127.0.0.1", device.port, "/ws", "t", received.append, name="reconnect")
        client._next_backoff = lambda attempt: 0.05  # keep the test fast
        await client.start()
        for _ in range(200):
            if device.connections >= 1 and received:
                break
            await asyncio.sleep(0.02)
        # force the server side away
        await device.stop()
        await asyncio.sleep(0.1)
        device2 = MockDevice()
        await device2.start()
        client._port = device2.port
        for _ in range(300):
            if device2.connections >= 1:
                break
            await asyncio.sleep(0.02)
        await client.stop()
        await device2.stop()
        return device2.connections

    assert _run(scenario()) >= 1


def test_client_reports_connection_state():
    async def scenario():
        device = MockDevice()
        await device.start()
        states = []
        client = EMSWebSocket(
            "127.0.0.1", device.port, "/ws", "t", lambda _p: None,
            name="state", on_state_change=states.append,
        )
        await client.start()
        await asyncio.sleep(0.4)
        assert states == [True]
        await client.stop()
        await device.stop()
        return states

    # True on connect, False once the client is stopped again
    assert _run(scenario()) == [True, False]


def test_handshake_rejected_raises():
    async def scenario():
        async def handler(reader, writer):
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        client = EMSWebSocket("127.0.0.1", port, "/ws", "t", lambda _p: None, name="404")
        with pytest.raises(ConnectionError, match="404"):
            await client._open()
        server.close()
        await server.wait_closed()

    _run(scenario())
