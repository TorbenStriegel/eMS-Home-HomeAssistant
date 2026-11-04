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
    #: Seconds actually spent charging in this cycle.
    tracked_session_seconds: float = 0.0
    #: Power the house produced itself (PV + battery discharge), in kW.
    self_supply_kw: float | None = None
    #: Tariffs from the options, used for the cost sensor.
    grid_price: float = 0.0
    pv_price: float = 0.0
    #: Snapshot of the last completed cycle, so a notification still has the
    #: numbers after the next session started.
    last_session: dict = field(default_factory=dict)

    @property
    def _live_cycle(self) -> bool:
        """Is there something in the running cycle? Otherwise the last one counts."""
        return self.tracked_session_energy_wh > 0 or self.tracked_session_seconds > 0

    def _last(self, key: str) -> float:
        try:
            return float((self.last_session or {}).get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    @property
    def session_energy_kwh(self) -> float:
        """Energy of the running cycle – or of the last one until a new charge starts."""
        if self.evse is not None and self.evse.session_energy > 0:
            return self.evse.session_energy_kwh
        if self._live_cycle:
            return round(self.tracked_session_energy_wh / 1000, 3)
        return round(self._last("energy_kwh"), 3)

    @property
    def session_grid_kwh(self) -> float:
        if self._live_cycle:
            return round(self.tracked_session_grid_wh / 1000, 3)
        return round(self._last("energy_grid_kwh"), 3)

    @property
    def session_pv_kwh(self) -> float:
        if self._live_cycle:
            return max(round(self.session_energy_kwh - self.session_grid_kwh, 3), 0.0)
        return round(self._last("energy_pv_kwh"), 3)

    @property
    def session_charge_minutes(self) -> float:
        """Time the car actually charged – not the time it stayed plugged in."""
        if self._live_cycle:
            return round(self.tracked_session_seconds / 60, 1)
        return round(self._last("duration_min"), 1)

    @property
    def session_cost(self) -> float | None:
        """Cost of the cycle – None while no tariff is configured."""
        if self.grid_price <= 0 and self.pv_price <= 0:
            return None
        if not self._live_cycle and self.last_session.get("cost") is not None:
            return round(self._last("cost"), 3)
        return round(
            self.session_grid_kwh * self.grid_price + self.session_pv_kwh * self.pv_price, 3
        )

    @property
    def session_saved(self) -> float | None:
        """What the roof saved compared to buying everything."""
        if self.grid_price <= 0:
            return None
        return round(self.session_pv_kwh * max(self.grid_price - self.pv_price, 0), 3)

class EMSHomeCoordinator(DataUpdateCoordinator[EMSHomeData]):
    """Polls the HTTP API and merges the pushed WebSocket streams."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: EMSHomeHTTP,
        update_interval: int = DEFAULT_SCAN_INTERVAL,
        grid_price: float = 0.0,
        pv_price: float = 0.0,
        store=None,
        pv_power_entity: str | None = None,
        battery_power_entity: str | None = None,
        min_cycle_power: float | None = None,
        min_cycle_seconds: float | None = None,
        noise_floor: float | None = None,
    ) -> None:
        if min_cycle_power is not None:
            self.MIN_CYCLE_POWER_KW = max(float(min_cycle_power), 0.1)
        if min_cycle_seconds is not None:
            self.MIN_CYCLE_SECONDS = max(float(min_cycle_seconds), 10.0)
        if noise_floor is not None:
            self.NOISE_FLOOR_KW = max(float(noise_floor), 0.0)
        self.client = client
        self._store = store
        self.pv_power_entity = pv_power_entity
        self.battery_power_entity = battery_power_entity
        self.grid_price = grid_price
        self.pv_price = pv_price
        self._last_session: dict = {}
        self._latest_smart_meter: Optional[SmartMeterReading] = None
        self._latest_evse: Optional[EVSEReading] = None
        self._poll_count = 0
        self._failed_polls = 0
        # per charging cycle
        self._session_energy_wh = 0.0
        self._session_grid_wh = 0.0
        self._session_seconds = 0.0
        self._session_prev: Optional[dict[str, float | bool]] = None
        #: True while nothing is running – the next charge starts a fresh cycle.
        self._session_ended = True
        #: When the power first rose above the gate, to time the confirmation.
        self._charge_since: Optional[float] = None
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
    # Persistence of the running cycle
    # ------------------------------------------------------------------

    async def async_load_session(self) -> None:
        """Restore the cycle after a restart – the figures must not reset."""
        if self._store is None:
            return
        try:
            stored = await self._store.async_load()
        except Exception as exc:  # noqa: BLE001 - a broken store must not block setup
            _LOGGER.debug("Could not restore the charging cycle: %s", exc)
            return
        if not stored:
            return
        self._session_energy_wh = float(stored.get("energy_wh") or 0)
        self._session_grid_wh = float(stored.get("grid_wh") or 0)
        self._session_seconds = float(stored.get("seconds") or 0)
        self._session_prev = stored.get("prev")
        self._last_session = stored.get("last_session") or {}
        _LOGGER.debug(
            "Restored charging cycle: %.2f kWh (%.2f kWh from the grid)",
            self._session_energy_wh / 1000,
            self._session_grid_wh / 1000,
        )

    @callback
    def _persist_session(self) -> None:
        store = getattr(self, "_store", None)
        if store is None:
            return
        store.async_delay_save(
            lambda: {
                "energy_wh": self._session_energy_wh,
                "grid_wh": self._session_grid_wh,
                "seconds": self._session_seconds,
                "prev": self._session_prev,
                "last_session": self._last_session,
            },
            30,
        )

    # ------------------------------------------------------------------
    # WebSocket lifecycle
    # ------------------------------------------------------------------

    async def async_start_websockets(
        self, smart_meter: bool = True, evse: bool = True
    ) -> None:
        """Start the live streams – each switch is independent."""
        token = self.client.token
        if not token:
            _LOGGER.warning("Cannot start the live streams – no access token yet")
            return

        if smart_meter:
            self.smart_meter_ws = SmartMeterWebSocket(
                self.client.host,
                token,
                self._on_smart_meter_reading,
                self.client.port,
                on_state_change=self._on_stream_state_change,
            )
        if evse:
            self.evse_ws = EVSEWebSocket(
                self.client.host,
                token,
                self._on_evse_reading,
                self.client.port,
                on_state_change=self._on_stream_state_change,
            )

        for stream in (self.smart_meter_ws, self.evse_ws):
            if stream is not None:
                await stream.start()

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

    #: The meter pushes about five frames per second. Writing ~40 entity states
    #: that often is pointless – the UI cannot show it and Home Assistant only
    #: burns CPU on it.
    UI_MIN_INTERVAL = 1.0

    @callback
    def _on_smart_meter_reading(self, reading: SmartMeterReading) -> None:
        self._latest_smart_meter = reading
        if self.data is not None:
            self.data.smart_meter = reading

        now = time.monotonic()
        last = getattr(self, "_last_ui_update", 0.0)
        if now - last >= self.UI_MIN_INTERVAL:
            self._last_ui_update = now
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
            self.data.tracked_session_grid_wh = self._session_grid_wh
            self.data.tracked_session_seconds = self._session_seconds
            self.data.last_session = dict(self._last_session)
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
            self._failed_polls += 1
            # The eMS Home occasionally stalls for a few seconds. Marking every
            # entity unavailable for a single missed poll is worse than briefly
            # showing the previous values – the live streams keep them fresh.
            if self.data is not None and self._failed_polls < 2:
                _LOGGER.warning(
                    "Poll failed (%s) – keeping the last values, retrying in %ss",
                    exc,
                    self.update_interval.total_seconds() if self.update_interval else "?",
                )
                return self.data
            raise UpdateFailed(f"Error communicating with eMS Home: {exc}") from exc

        self._failed_polls = 0

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
            tracked_session_seconds=self._session_seconds,
            grid_price=self.grid_price,
            pv_price=self.pv_price,
            self_supply_kw=self._self_supply_kw(),
            last_session=dict(self._last_session),
        )

    #: A meter frame older than this is not used for the source split.
    METER_MAX_AGE = 60.0
    #: The wallbox only pushes on change, so its frames are legitimately sparse –
    #: a 60 s window made its sensors flap to unavailable between frames.
    EVSE_MAX_AGE = 900.0
    #: A charge only counts as a session above this power …
    MIN_CYCLE_POWER_KW = 1.0
    #: … and only when it lasts at least this long. The wallbox reports single
    #: samples of 0,11–0,27 kW every few minutes while plugged in; those are not
    #: charging and must not start a new cycle.
    MIN_CYCLE_SECONDS = 180.0
    #: Below this the integration does not integrate at all (standby noise).
    NOISE_FLOOR_KW = 0.35

    def _entity_power_kw(self, entity_id: str | None) -> float | None:
        """Read a power sensor and normalise it to kW."""
        if not entity_id:
            return None
        hass = getattr(self, "hass", None)
        if hass is None:
            return None
        state = hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None
        unit = str(state.attributes.get("unit_of_measurement", "W")).lower()
        if unit in ("kw", "kilowatt"):
            return value
        if unit in ("mw", "megawatt"):
            return value * 1000
        return value / 1000  # W is the default for power sensors

    def _self_supply_kw(self) -> float | None:
        """Own generation: PV plus battery discharge (positive = discharging).

        Returns None when neither sensor is configured, so the caller can fall
        back to the meter-only attribution.
        """
        pv = self._entity_power_kw(getattr(self, "pv_power_entity", None))
        battery = self._entity_power_kw(getattr(self, "battery_power_entity", None))
        if pv is None and battery is None:
            return None
        return max(pv or 0.0, 0.0) + max(battery or 0.0, 0.0)

    def _grid_share_kw(self, power_kw: float) -> float | None:
        """How much of the car's draw came from the grid, or None if unknown."""
        self_kw = self._self_supply_kw()
        meter_kw = self._current_grid_kw()

        if self_kw is not None:
            # Own generation covers the car first; the meter caps what could
            # actually have been imported.
            share = max(power_kw - self_kw, 0.0)
            if meter_kw is not None:
                share = min(share, meter_kw)
            return min(share, power_kw)

        if meter_kw is not None:
            return min(meter_kw, power_kw)
        return None

    def _current_grid_kw(self) -> float | None:
        """Grid power in kW, or None when there is no usable meter reading."""
        if self._latest_smart_meter is None:
            return None
        stream = getattr(self, "smart_meter_ws", None)
        if stream is not None and stream.stats.seconds_since_frame > self.METER_MAX_AGE:
            return None
        return max(self._latest_smart_meter.power_total / 1000, 0.0)

    # ------------------------------------------------------------------
    # Per-cycle session energy
    # ------------------------------------------------------------------

    @callback
    def _track_session_cycle(self, reading: EVSEReading) -> None:
        """Start a new cycle when the car is plugged in or the counter restarts."""
        previous = self._session_prev
        duration = reading.session_duration
        plugged = reading.is_plugged

        # A reconnect can deliver a frame with a reset session counter; that is
        # not a new charge. Only the power gate starts a cycle now – otherwise a
        # short drop of the stream wiped the figures of the last charge.

        self._plugged = plugged
        self._session_prev = {"duration": duration, "plugged": plugged}
        self._persist_session()

    def _finish_cycle(self, previous: Optional[dict]) -> None:
        if self._session_energy_wh <= 0:
            return
        self._last_session = {
            "energy_kwh": round(self._session_energy_wh / 1000, 3),
            "energy_grid_kwh": round(self._session_grid_wh / 1000, 3),
            "energy_pv_kwh": round(
                max(self._session_energy_wh - self._session_grid_wh, 0) / 1000, 3
            ),
            "duration_min": round(self._session_seconds / 60, 1),
            "ended_at": datetime.now(timezone.utc).isoformat(),
        }
        if self.grid_price > 0 or self.pv_price > 0:
            self._last_session["cost"] = round(
                self._last_session["energy_grid_kwh"] * self.grid_price
                + self._last_session["energy_pv_kwh"] * self.pv_price,
                3,
            )

    def _reset_cycle(self) -> None:
        self._session_energy_wh = 0.0
        self._session_grid_wh = 0.0
        self._session_seconds = 0.0
        self._energy_last_ts = None
        self._session_ended = False

    @callback
    def _accumulate_session_energy(self, state: EMobilityState) -> None:
        """Integrate the reported charging power over time."""
        now = time.monotonic()
        power_kw = state.ev_charging_power.total / 1_000_000
        running = not getattr(self, "_session_ended", True)

        # End the cycle only when the car is gone *and* nothing flows. A status
        # flap in the middle of a charge must not close the session.
        if (
            running
            and not getattr(self, "_plugged", True)
            and power_kw < self.NOISE_FLOOR_KW
            and self._session_energy_wh > 0
        ):
            self._finish_cycle(self._session_prev)
            self._session_ended = True
            running = False

        # Track when the power crossed the gate, so a heartbeat of 0,11 kW cannot
        # pass for a charge.
        started = getattr(self, "_charge_since", None)
        if power_kw >= self.MIN_CYCLE_POWER_KW:
            if started is None:
                self._charge_since = started = now
        elif not running:
            self._charge_since = started = None

        if not running:
            if started is None or now - started < self.MIN_CYCLE_SECONDS:
                # Too short or too weak: keep the figures of the last session.
                self._energy_last_ts = now
                return
            self._reset_cycle()  # a real charge begins – start counting

        previous = self._energy_last_ts
        self._energy_last_ts = now

        if previous is None or power_kw < self.NOISE_FLOOR_KW:
            return
        elapsed = now - previous
        if not 0 < elapsed < 300:  # a poll gap this long is a restart, not a sample
            return

        hours = elapsed / 3600
        self._session_seconds += elapsed
        energy_wh = power_kw * hours * 1000
        self._session_energy_wh += energy_wh

        # How much of the draw came from the grid. Unknown sources count as grid –
        # calling them solar would invent savings.
        share_kw = self._grid_share_kw(power_kw)
        if share_kw is None:
            self._session_grid_wh += energy_wh
        else:
            self._session_grid_wh += share_kw * hours * 1000
        self._persist_session()

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
