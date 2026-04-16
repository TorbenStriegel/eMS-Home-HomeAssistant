"""
eMS Home – EVSE (Wallbox) WebSocket client.

Connects to ws://<host>/api/data-transfer/ws/protobuf/gdr/local/values/+/evse
and decodes the binary protobuf frames into an EVSEReading dataclass.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from .smart_meter_ws import (
    _ws_open,
    _ws_recv_frame,
    _ws_close,
    _send_ws_text,
    _decode_fields,
)

_LOGGER = logging.getLogger(__name__)

WS_EVSE_PATH = "/api/data-transfer/ws/protobuf/gdr/local/values/+/evse"


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class EVSEReading:
    """Decoded EVSE snapshot from one WebSocket frame."""
    uuid: str = ""
    evse_status: int = 0
    evse_status_code: str = ""
    evse_error_code: str = ""
    evse_serial: str = ""
    evse_hw_imax: int = 0           # mA (hardware max current)
    ev_imax_default: int = 0        # mA
    session_duration: int = 0       # seconds
    session_energy: float = 0.0     # Wh
    energy_total: float = 0.0       # Wh
    timestamp: float = 0.0

    @property
    def hw_imax_amps(self) -> float:
        """Hardware max current in A."""
        return self.evse_hw_imax / 1000 if self.evse_hw_imax else 0

    @property
    def session_duration_min(self) -> float:
        """Session duration in minutes."""
        return round(self.session_duration / 60, 1)

    @property
    def session_energy_kwh(self) -> float:
        """Session energy in kWh."""
        return round(self.session_energy / 1000, 3)

    @property
    def energy_total_kwh(self) -> float:
        """Total energy in kWh."""
        return round(self.energy_total / 1000, 3)

    @property
    def status_text(self) -> str:
        """Human-readable EVSE status."""
        status_map = {
            0: "unknown",
            1: "available",
            2: "occupied",
            3: "preparing",
            4: "charging",
            5: "finishing",
            6: "reserved",
            7: "unavailable",
            8: "faulted",
            9: "suspended_ev",
            10: "suspended_evse",
        }
        return status_map.get(self.evse_status, f"status_{self.evse_status}")


# ---------------------------------------------------------------------------
# Protobuf decoder for EVSE frames
# ---------------------------------------------------------------------------

def decode_evse_frame(raw: bytes) -> Optional[EVSEReading]:
    """Decode an EVSE protobuf frame."""
    try:
        outer = _decode_fields(raw)
        # field 1 = outer wrapper
        wrapper_bytes = next((v for fn, wt, v in outer if fn == 1 and wt == 2), None)
        if wrapper_bytes is None:
            return None

        wrapper = _decode_fields(wrapper_bytes)
        # field 1 = UUID, field 2 = inner payload
        uuid = ""
        inner_bytes = None
        for fn, wt, v in wrapper:
            if fn == 1 and wt == 2:
                try:
                    uuid = v.decode("utf-8")
                except Exception:
                    pass
            elif fn == 2 and wt == 2:
                inner_bytes = v

        if inner_bytes is None:
            return None

        reading = EVSEReading(uuid=uuid)
        inner = _decode_fields(inner_bytes)

        for fn, wt, v in inner:
            # field 3 = timestamp
            if fn == 3 and wt == 2:
                tsf = _decode_fields(v)
                sec = next((val for f, _, val in tsf if f == 1), 0)
                ns = next((val for f, _, val in tsf if f == 2), 0)
                reading.timestamp = sec + ns / 1e9

            # field 4 = channel data (numeric measurements)
            elif fn == 4 and wt == 2:
                dp = _decode_fields(v)
                ch_id = next((val for f, _, val in dp if f == 1), None)
                raw_v = next((val for f, _, val in dp if f == 2), None)
                if ch_id is not None and raw_v is not None:
                    _apply_evse_channel(reading, ch_id, raw_v)

            # field 5 = named key-value pairs
            elif fn == 5 and wt == 2:
                _apply_evse_property(reading, v)

        return reading
    except Exception as exc:
        _LOGGER.debug("Failed to decode EVSE frame: %s", exc)
        return None


def _apply_evse_channel(reading: EVSEReading, ch_id: int, raw: int) -> None:
    """Apply numeric channel data. Channel semantics are inferred from observed values."""
    # We store any large counter values as energy candidates.
    # The two largest values from observed data appear to be energy counters.
    # Since we can't yet map channel IDs with 100% certainty, we use heuristics:
    # values > 100000 are likely energy (mWh), smaller values are current/power (mA/mW).
    pass  # Channel mapping will be refined with more data samples


def _apply_evse_property(reading: EVSEReading, prop_bytes: bytes) -> None:
    """Parse a named property (field 5) and apply it to the reading."""
    try:
        fields = _decode_fields(prop_bytes)
        name_bytes = next((v for fn, wt, v in fields if fn == 1 and wt == 2), None)
        value_bytes = next((v for fn, wt, v in fields if fn == 2 and wt == 2), None)

        if name_bytes is None:
            return

        name = name_bytes.decode("utf-8")

        if value_bytes is None or len(value_bytes) == 0:
            return

        # Decode the value sub-message
        value_fields = _decode_fields(value_bytes)

        if name == "evse_session_duration":
            reading.session_duration = next(
                (val for f, _, val in value_fields if f == 1), 0
            )
        elif name == "evse_status":
            reading.evse_status = next(
                (val for f, _, val in value_fields if f == 1), 0
            )
        elif name == "evse_status_code":
            s = next((v for f, wt, v in value_fields if f == 2 and wt == 2), None)
            if s:
                reading.evse_status_code = s.decode("utf-8", errors="replace")
        elif name == "evse_error_code":
            s = next((v for f, wt, v in value_fields if f == 2 and wt == 2), None)
            if s:
                reading.evse_error_code = s.decode("utf-8", errors="replace")
        elif name == "evse_serial":
            s = next((v for f, wt, v in value_fields if f == 2 and wt == 2), None)
            if s:
                reading.evse_serial = s.decode("utf-8", errors="replace").strip()
        elif name == "evse_hw_imax":
            reading.evse_hw_imax = next(
                (val for f, _, val in value_fields if f == 1), 0
            )
        elif name == "ev_imax_default":
            reading.ev_imax_default = next(
                (val for f, _, val in value_fields if f == 1), 0
            )
    except Exception as exc:
        _LOGGER.debug("Failed to parse EVSE property: %s", exc)


# ---------------------------------------------------------------------------
# Async WebSocket client
# ---------------------------------------------------------------------------

class EVSEWebSocket:
    """Persistent WebSocket connection for EVSE data with auto-reconnect."""

    def __init__(
        self,
        host: str,
        token: str,
        on_reading: Callable[[EVSEReading], None],
        port: int = 80,
    ) -> None:
        self._host = host
        self._port = port
        self._token = token
        self._callback = on_reading
        self._task: Optional[asyncio.Task] = None
        self._running = False

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
                    "EVSE WebSocket error (%s), reconnecting in %.0fs", exc, delay
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60.0)

    async def _connect_and_listen(self) -> None:
        reader, writer = await _ws_open(
            self._host, self._port, WS_EVSE_PATH, self._token
        )
        _LOGGER.info("EVSE WebSocket connected")
        _send_ws_text(writer, f"Bearer {self._token}")
        await writer.drain()
        try:
            while self._running:
                payload = await _ws_recv_frame(reader)
                reading = decode_evse_frame(payload)
                if reading is not None:
                    self._callback(reading)
        finally:
            await _ws_close(writer)

