"""DataUpdateCoordinator for eMS Home."""
from __future__ import annotations

import logging
import time as _time
from datetime import timedelta
from dataclasses import dataclass
from typing import Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .ems_home_api import EMSHomeHTTP, DeviceStatus, EMobilityState, ChargeModeConfig
from .smart_meter_ws import SmartMeterReading, SmartMeterWebSocket
from .evse_ws import EVSEReading, EVSEWebSocket
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class EMSHomeData:
    """All data available to sensor / select entities."""
    device_status:   DeviceStatus
    emobility_state: EMobilityState
    charge_mode:     ChargeModeConfig
    smart_meter: Optional[SmartMeterReading] = None
    evse: Optional[EVSEReading] = None


class EMSHomeCoordinator(DataUpdateCoordinator[EMSHomeData]):
    """Polls eMS Home HTTP endpoints and incorporates WS data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: EMSHomeHTTP,
        update_interval: int,
    ) -> None:
        self.client = client
        self._ws_client: Optional[SmartMeterWebSocket] = None
        self._evse_ws_client: Optional[EVSEWebSocket] = None
        self._latest_smart_meter: Optional[SmartMeterReading] = None
        self._latest_evse: Optional[EVSEReading] = None
        self._poll_count: int = 0

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

    # ------------------------------------------------------------------
    # Helper: extract host/port from client base URL
    # ------------------------------------------------------------------

    def _get_host_port(self) -> tuple[str, int]:
        base = self.client._base
        host = base.split("//")[1].rsplit(":", 1)[0]
        try:
            port = int(base.rsplit(":", 1)[1])
        except (IndexError, ValueError):
            port = 80
        return host, port

    # ------------------------------------------------------------------
    # WebSocket lifecycle
    # ------------------------------------------------------------------

    async def async_start_websocket(self) -> None:
        token = self.client.token
        if token is None:
            _LOGGER.warning("Cannot start WebSockets – no token available")
            return

        host, port = self._get_host_port()

        # Smart Meter WS
        self._ws_client = SmartMeterWebSocket(
            host=host, token=token,
            on_reading=self._on_smart_meter_reading, port=port,
        )
        await self._ws_client.start()
        _LOGGER.debug("Smart meter WebSocket started for %s:%s", host, port)

        # EVSE WS
        self._evse_ws_client = EVSEWebSocket(
            host=host, token=token,
            on_reading=self._on_evse_reading, port=port,
        )
        await self._evse_ws_client.start()
        _LOGGER.debug("EVSE WebSocket started for %s:%s", host, port)

    async def async_stop_websocket(self) -> None:
        if self._ws_client:
            await self._ws_client.stop()
            self._ws_client = None
        if self._evse_ws_client:
            await self._evse_ws_client.stop()
            self._evse_ws_client = None

    # ------------------------------------------------------------------
    # Smart Meter callbacks
    # ------------------------------------------------------------------

    @callback
    def _on_smart_meter_reading(self, reading: SmartMeterReading) -> None:
        reading._received_at = _time.monotonic()
        self._latest_smart_meter = reading
        # Only push to HA if we already have base data from HTTP poll
        # Use async_write_ha_state pattern to avoid resetting the poll timer
        if self.data is not None:
            self.data.smart_meter = reading
            # Notify listeners without resetting the update_interval timer
            self.async_update_listeners()

    def get_fresh_smart_meter(self, max_age: float = 15.0):
        r = self._latest_smart_meter
        if r is None:
            return None
        return r if (_time.monotonic() - getattr(r, "_received_at", 0.0)) <= max_age else None

    # ------------------------------------------------------------------
    # EVSE callbacks
    # ------------------------------------------------------------------

    @callback
    def _on_evse_reading(self, reading: EVSEReading) -> None:
        reading._received_at = _time.monotonic()
        self._latest_evse = reading
        if self.data is not None:
            self.data.evse = reading
            self.async_update_listeners()

    def get_fresh_evse(self, max_age: float = 15.0):
        r = self._latest_evse
        if r is None:
            return None
        return r if (_time.monotonic() - getattr(r, "_received_at", 0.0)) <= max_age else None

    # ------------------------------------------------------------------
    # HTTP poll
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> EMSHomeData:
        self._poll_count += 1
        _LOGGER.info(
            "HTTP poll #%d starting (interval=%s)",
            self._poll_count,
            self.update_interval,
        )

        try:
            device_status, emobility_state, charge_mode = (
                await self.hass.async_add_executor_job(self._fetch_all)
            )
        except Exception as exc:
            _LOGGER.warning("HTTP poll #%d failed: %s", self._poll_count, exc)
            raise UpdateFailed(f"Error communicating with eMS Home: {exc}") from exc

        _LOGGER.info(
            "HTTP poll #%d OK – charging=%.3f kW (raw=%d), mode=%s, cpu=%d°C",
            self._poll_count,
            emobility_state.ev_charging_power.total / 1_000_000,
            emobility_state.ev_charging_power.total,
            charge_mode.mode,
            device_status.cpu_temp,
        )

        return EMSHomeData(
            device_status=device_status,
            emobility_state=emobility_state,
            charge_mode=charge_mode,
            smart_meter=self._latest_smart_meter,
            evse=self._latest_evse,
        )

    def _fetch_all(self):
        # Keep WS tokens in sync
        token = self.client.token
        if self._ws_client and token:
            self._ws_client.update_token(token)
        if self._evse_ws_client and token:
            self._evse_ws_client.update_token(token)

        # Fetch each endpoint independently – if one fails, try the others
        device_status = None
        emobility_state = None
        charge_mode = None

        try:
            device_status = self.client.get_device_status()
        except Exception as exc:
            _LOGGER.warning("Failed to fetch device status: %s", exc)

        try:
            emobility_state = self.client.get_emobility_state()
        except Exception as exc:
            _LOGGER.warning("Failed to fetch e-mobility state: %s", exc)

        try:
            charge_mode = self.client.get_charge_mode()
        except Exception as exc:
            _LOGGER.warning("Failed to fetch charge mode: %s", exc)

        # If all three failed, raise so the coordinator marks as unavailable
        if device_status is None and emobility_state is None and charge_mode is None:
            raise ConnectionError("All HTTP endpoints failed")

        # Use previous data as fallback for individual failures
        prev = self.data
        if device_status is None and prev:
            device_status = prev.device_status
        if emobility_state is None and prev:
            emobility_state = prev.emobility_state
        if charge_mode is None and prev:
            charge_mode = prev.charge_mode

        # If we still have None (first poll, partial failure), create defaults
        from .ems_home_api import PhaseValues
        if device_status is None:
            device_status = DeviceStatus("unknown", 0, 0, 1, 1, 1, 1, 1, 1)
        if emobility_state is None:
            emobility_state = EMobilityState(
                PhaseValues(0, 0, 0, 0), PhaseValues(0, 0, 0, 0), False
            )
        if charge_mode is None:
            charge_mode = ChargeModeConfig("unknown", 0, 0, 0, 0)

        return device_status, emobility_state, charge_mode

