"""DataUpdateCoordinator for eMS Home."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .ems_home_api import ChargeMode, ChargeModeConfig, DeviceStatus, EMobilityState, PhaseValues
from .ems_home_api import EMSHomeHTTP
from .evse_ws import EVSEWebSocket
from .smart_meter_ws import SmartMeterWebSocket
from .ws_proto import EVSEReading, SmartMeterReading

_LOGGER = logging.getLogger(__name__)


@dataclass
class EMSHomeData:
    """Snapshot handed to every entity."""

    device_status: DeviceStatus
    emobility_state: EMobilityState
    charge_mode: ChargeModeConfig
    smart_meter: Optional[SmartMeterReading] = None
    evse: Optional[EVSEReading] = None
    #: Energy of the current charging cycle, integrated by the coordinator when
    #: the firmware does not report it (some versions always send 0).
    tracked_session_energy_wh: float = 0.0
    #: Share of that energy that came from the grid (rest: from the roof).
    tracked_session_grid_wh: float = 0.0
    #: Tariffs from the options, used for the cost sensor.
    grid_price: float = 0.0
    pv_price: float = 0.0
    #: Snapshot of the last completed cycle, so a notification still has the
    #: numbers after the next session started.
    last_session: dict = field(default_factory=dict)

    @property
    def session_energy_kwh(self) -> float:
        """Energy charged in the current cycle, in kWh.

        The device value wins when it is present – otherwise the integrated one.
        """
        if self.evse is not None and self.evse.session_energy > 0:
            return self.evse.session_energy_kwh
        return round(self.tracked_session_energy_wh / 1000, 3)

    @property
    def session_grid_kwh(self) -> float:
        """Energy of the cycle that was drawn from the grid.

        While charging, whatever the meter reports as import is attributed to the
        car first (capped at the charging power); the remainder comes from the
        roof. That is an estimate – the house draws from the same meter – but far
        closer to the truth than pricing PV energy at the grid tariff.
        """
        return round(self.tracked_session_grid_wh / 1000, 3)

    @property
    def session_pv_kwh(self) -> float:
        total = self.session_energy_kwh
        return max(round(total - self.session_grid_kwh, 3), 0.0)

    @property
    def session_cost(self) -> float | None:
        """Cost of the current cycle – None while no tariff is configured."""
        if self.grid_price <= 0 and self.pv_price <= 0:
            return None
        cost = self.session_grid_kwh * self.grid_price + self.session_pv_kwh * self.pv_price
        return round(cost, 3)

    @property
    def session_saved(self) -> float | None:
        """What the roof saved compared to buying everything."""
        if self.grid_price <= 0:
            return None
        return round(self.session_pv_kwh * max(self.grid_price - self.pv_price, 0), 3)

    @property
    def charging_power_kw(self) -> float:
        return round(self.emobility_state.ev_charging_power.total / 1_000_000, 3)

    @property
    def grid_power_kw(self) -> float:
        """Grid power in kW (positive = import)."""
        if self.smart_meter is None:
            return 0.0
        return round(self.smart_meter.power_total / 1000, 3)

    @property
    def is_locked(self) -> bool:
        return self.charge_mode.mode == ChargeMode.LOCK

    @property
    def effective_pv_quota(self) -> int:
        return int(
            self.charge_mode.min_pv_power_quota
            or self.charge_mode.last_min_pv_power_quota
            or 0
        )

    @property
    def charge_state(self) -> str:
        if self.is_locked:
            return "locked"
        if self.evse is not None and self.evse.is_charging:
            return "charging"
        if self.charging_power_kw > 0:
            return "charging"
        return "idle"


class EMSHomeCoordinator(DataUpdateCoordinator[EMSHomeData]):
    """Polls the HTTP API and merges the pushed WebSocket streams."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: EMSHomeHTTP,
        update_interval: int = DEFAULT_SCAN_INTERVAL,
        grid_price: float = 0.0,
        pv_price: float = 0.0,
    ) -> None:
        self.client = client
        self.grid_price = grid_price
        self.pv_price = pv_price
        self._last_session: dict = {}
        self._latest_smart_meter: Optional[SmartMeterReading] = None
        self._latest_evse: Optional[EVSEReading] = None
        self._poll_count = 0
        # per charging cycle
        self._session_energy_wh = 0.0
        self._session_grid_wh = 0.0
        self._session_prev: Optional[dict[str, float | bool]] = None
        self._energy_last_ts: Optional[float] = None

        self.smart_meter_ws: Optional[SmartMeterWebSocket] = None
        self.evse_ws: Optional[EVSEWebSocket] = None
        self._known_wallboxes: set[str] = set()

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=max(update_interval, 3)),
        )

    # ------------------------------------------------------------------
    # WebSocket lifecycle
    # ------------------------------------------------------------------

    async def async_start_websockets(self) -> None:
        token = self.client.token
        if not token:
            _LOGGER.warning("Cannot start the live streams – no access token yet")
            return

        self.smart_meter_ws = SmartMeterWebSocket(
            self.client.host,
            token,
            self._on_smart_meter_reading,
            self.client.port,
            on_state_change=self._on_stream_state_change,
        )
        self.evse_ws = EVSEWebSocket(
            self.client.host,
            token,
            self._on_evse_reading,
            self.client.port,
            on_state_change=self._on_stream_state_change,
        )
        await self.smart_meter_ws.start()
        await self.evse_ws.start()

    async def async_stop_websockets(self) -> None:
        for client in (self.smart_meter_ws, self.evse_ws):
            if client is not None:
                await client.stop()
        self.smart_meter_ws = None
        self.evse_ws = None

    @callback
    def _on_stream_state_change(self, _connected: bool) -> None:
        """Refresh entities so stream availability is reflected immediately."""
        self.async_update_listeners()

    # ------------------------------------------------------------------
    # Stream callbacks
    # ------------------------------------------------------------------

    @callback
    def _on_smart_meter_reading(self, reading: SmartMeterReading) -> None:
        self._latest_smart_meter = reading
        if self.data is not None:
            self.data.smart_meter = reading
        self.async_update_listeners()

    @callback
    def _on_evse_reading(self, reading: EVSEReading) -> None:
        if reading.uuid and reading.uuid not in self._known_wallboxes:
            self._known_wallboxes.add(reading.uuid)
            if len(self._known_wallboxes) > 1:
                # The subscription uses a wildcard, so a second wallbox pushes on
                # the same stream and the entities would silently alternate.
                _LOGGER.warning(
                    "Multiple wallboxes are publishing on the live stream (%s). "
                    "Only the most recent frame is exposed – the wallbox entities "
                    "will alternate between devices.",
                    ", ".join(sorted(self._known_wallboxes)),
                )
        self._track_session_cycle(reading)
        self._latest_evse = reading
        if self.data is not None:
            self.data.evse = reading
            self.data.tracked_session_energy_wh = self._session_energy_wh
        self.async_update_listeners()

    @property
    def stream_stats(self) -> dict[str, dict]:
        """Connection statistics for diagnostics."""
        stats: dict[str, dict] = {}
        if self.smart_meter_ws is not None:
            stats["smart_meter"] = self.smart_meter_ws.stats.as_dict()
        if self.evse_ws is not None:
            stats["evse"] = self.evse_ws.stats.as_dict()
        return stats

    # ------------------------------------------------------------------
    # HTTP poll
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> EMSHomeData:
        self._poll_count += 1

        try:
            device_status, emobility_state, charge_mode = await self.hass.async_add_executor_job(
                self._fetch_all
            )
        except Exception as exc:  # noqa: BLE001
            raise UpdateFailed(f"Error communicating with eMS Home: {exc}") from exc

        _LOGGER.debug(
            "Poll #%d – charging %.3f kW, mode %s",
            self._poll_count,
            emobility_state.ev_charging_power.total / 1_000_000,
            charge_mode.mode,
        )

        self._accumulate_session_energy(emobility_state)

        return EMSHomeData(
            device_status=device_status,
            emobility_state=emobility_state,
            charge_mode=charge_mode,
            smart_meter=self._latest_smart_meter,
            evse=self._latest_evse,
            tracked_session_energy_wh=self._session_energy_wh,
            tracked_session_grid_wh=self._session_grid_wh,
            grid_price=self.grid_price,
            pv_price=self.pv_price,
            last_session=dict(self._last_session),
        )

    # ------------------------------------------------------------------
    # Per-cycle session energy
    # ------------------------------------------------------------------

    @callback
    def _track_session_cycle(self, reading: EVSEReading) -> None:
        """Start a new cycle when the car is plugged in or the counter restarts."""
        previous = self._session_prev
        duration = reading.session_duration
        plugged = reading.is_plugged

        new_cycle = False
        if previous is not None:
            if duration + 30 < previous["duration"]:
                new_cycle = True  # the device restarted its session counter
            elif plugged and not previous["plugged"]:
                new_cycle = True  # car was plugged in again

        if new_cycle:
            if self._session_energy_wh > 0:
                self._last_session = {
                    "energy_kwh": round(self._session_energy_wh / 1000, 3),
                    "energy_grid_kwh": round(self._session_grid_wh / 1000, 3),
                    "energy_pv_kwh": round(
                        max(self._session_energy_wh - self._session_grid_wh, 0) / 1000, 3
                    ),
                    "duration_min": round(previous["duration"] / 60, 1) if previous else 0,
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                }
                if self.grid_price > 0 or self.pv_price > 0:
                    self._last_session["cost"] = round(
                        self._last_session["energy_grid_kwh"] * self.grid_price
                        + self._last_session["energy_pv_kwh"] * self.pv_price,
                        3,
                    )
            _LOGGER.debug(
                "New charging cycle detected (was %.2f kWh, %s s)",
                self._session_energy_wh / 1000,
                duration,
            )
            self._session_energy_wh = 0.0
            self._session_grid_wh = 0.0
            self._energy_last_ts = None

        self._session_prev = {"duration": duration, "plugged": plugged}

    @callback
    def _accumulate_session_energy(self, state: EMobilityState) -> None:
        """Integrate the reported charging power over time."""
        now = time.monotonic()
        power_kw = state.ev_charging_power.total / 1_000_000
        previous = self._energy_last_ts
        self._energy_last_ts = now

        if previous is None or power_kw <= 0.05:
            return
        elapsed = now - previous
        if not 0 < elapsed < 300:  # a poll gap this long is a restart, not a sample
            return

        hours = elapsed / 3600
        energy_wh = power_kw * hours * 1000
        self._session_energy_wh += energy_wh

        # Attribute grid import to the car first, capped at its own draw.
        grid_kw = 0.0
        if self._latest_smart_meter is not None:
            grid_kw = max(self._latest_smart_meter.power_total / 1000, 0.0)
        self._session_grid_wh += min(grid_kw, power_kw) * hours * 1000

    def _fetch_all(self) -> tuple[DeviceStatus, EMobilityState, ChargeModeConfig]:
        # Keep the stream tokens in sync with the (renewed) HTTP session token.
        token = self.client.token
        if token:
            if self.smart_meter_ws is not None:
                self.smart_meter_ws.update_token(token)
            if self.evse_ws is not None:
                self.evse_ws.update_token(token)

        previous = self.data
        device_status: Optional[DeviceStatus] = None
        emobility_state: Optional[EMobilityState] = None
        charge_mode: Optional[ChargeModeConfig] = None
        errors: list[str] = []

        try:
            device_status = self.client.get_device_status()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"device status: {exc}")

        try:
            emobility_state = self.client.get_emobility_state()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"e-mobility state: {exc}")

        try:
            charge_mode = self.client.get_charge_mode()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"charge mode: {exc}")

        if device_status is None and emobility_state is None and charge_mode is None:
            raise ConnectionError("; ".join(errors) or "all endpoints failed")

        # Partial failures fall back to the previous values – the device is a
        # small embedded web server and regularly drops a single request.
        if errors:
            _LOGGER.debug("Partial poll failure: %s", "; ".join(errors))

        if device_status is None:
            device_status = previous.device_status if previous else DeviceStatus("unknown", 0, 0, 1, 1, 1, 1, 1, 1)
        if emobility_state is None:
            emobility_state = previous.emobility_state if previous else EMobilityState(PhaseValues(0, 0, 0, 0), PhaseValues(0, 0, 0, 0), False)
        if charge_mode is None:
            charge_mode = previous.charge_mode if previous else ChargeModeConfig("unknown", 0, 0, 0, 0)

        return device_status, emobility_state, charge_mode

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def async_set_charge_mode(self, mode: str) -> None:
        """Select the charge mode, keeping the configured PV quota."""
        data = self.data
        pv_quota = data.effective_pv_quota if data else 0
        await self.hass.async_add_executor_job(self._set_mode, mode, pv_quota)
        await self.async_request_refresh()

    async def async_set_pv_quota(self, quota: int) -> None:
        """Write the minimum PV surplus quota while keeping the current mode."""
        data = self.data
        mode = data.charge_mode.mode if data else ChargeMode.HYBRID
        await self.hass.async_add_executor_job(self._set_quota, mode, quota)
        await self.async_request_refresh()

    async def async_set_min_charging_quota(self, quota: int) -> None:
        """Write the minimum charging power quota (used by grid/hybrid)."""
        data = self.data
        mode = data.charge_mode.mode if data else ChargeMode.HYBRID
        pv_quota = data.effective_pv_quota if data else 0
        await self.hass.async_add_executor_job(
            self.client.set_charge_mode, mode, quota, pv_quota
        )
        await self.async_request_refresh()

    def _set_mode(self, mode: str, pv_quota: int) -> None:
        # Always send the known PV quota: omitting it made the firmware fall
        # back to 0, so switching PV -> Grid silently wiped the configured quota.
        self.client.set_charge_mode(mode, min_pv_power_quota=pv_quota)

    def _set_quota(self, mode: str, quota: int) -> None:
        self.client.set_charge_mode(mode, min_pv_power_quota=quota)

    # ------------------------------------------------------------------
    # Helper for entities
    # ------------------------------------------------------------------

    @property
    def smart_meter_connected(self) -> bool:
        return bool(self.smart_meter_ws and self.smart_meter_ws.stats.connected)

    @property
    def evse_connected(self) -> bool:
        return bool(self.evse_ws and self.evse_ws.stats.connected)

    @property
    def last_frame_age(self) -> Optional[float]:
        return self.smart_meter_ws.stats.seconds_since_frame if self.smart_meter_ws else None

    def diagnostics_snapshot(self) -> dict:
        """Everything that helps to debug a device in the field."""
        return {
            "host": self.client.host,
            "port": self.client.port,
            "https": self.client.uses_https,
            "poll_interval": self.update_interval.total_seconds() if self.update_interval else None,
            "polls": self._poll_count,
            "streams": self.stream_stats,
            "last_update": time.time(),
        }
