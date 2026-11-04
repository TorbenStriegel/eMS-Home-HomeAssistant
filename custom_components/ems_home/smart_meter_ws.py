"""eMS Home – smart meter WebSocket stream."""
from __future__ import annotations

import logging
from typing import Callable, Optional

from .ws_client import EMSWebSocket, StreamStats
from .ws_proto import SmartMeterReading, decode_smart_meter_frame

_LOGGER = logging.getLogger(__name__)

WS_PATH = "/api/data-transfer/ws/protobuf/gdr/local/values/smart-meter"


class SmartMeterWebSocket:
    """Persistent, self-healing stream of smart meter readings."""

    def __init__(
        self,
        host: str,
        token: str,
        on_reading: Callable[[SmartMeterReading], None],
        port: int = 80,
        *,
        on_state_change: Optional[Callable[[bool], None]] = None,
    ) -> None:
        self._callback = on_reading
        self.on_state_change = on_state_change
        self._client = EMSWebSocket(
            host,
            port,
            WS_PATH,
            token,
            self._handle_frame,
            name="Smart meter",
            on_state_change=on_state_change,
        )

    @property
    def stats(self) -> StreamStats:
        return self._client.stats

    async def start(self) -> None:
        await self._client.start()

    async def stop(self) -> None:
        await self._client.stop()

    def update_token(self, token: str) -> None:
        self._client.update_token(token)

    def _handle_frame(self, payload: bytes) -> None:
        reading = decode_smart_meter_frame(payload)
        if reading is None:
            self.stats.undecodable_frames += 1
            if self.stats.undecodable_frames <= 3:
                _LOGGER.warning(
                    "Smart meter frame could not be decoded (%d bytes, starts with %s)",
                    len(payload),
                    payload[:16].hex(),
                )
            return
        self._callback(reading)
