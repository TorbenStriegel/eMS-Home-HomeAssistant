"""DataUpdateCoordinator for eMS Home."""
from __future__ import annotations

import asyncio

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_INSTANT_POWER, DEFAULT_SCAN_INTERVAL, DOMAIN
from .ems_home_api import ChargeMode, ChargeModeConfig, DeviceStatus, EMobilityState, PhaseValues
from .ems_home_api import EMSHomeHTTP
from . import notifications
from .evse_ws import EVSEWebSocket
from .smart_meter_ws import SmartMeterWebSocket
from .ws_proto import EVSEReading, SmartMeterReading

_LOGGER = logging.getLogger(__name__)

#: Entity keys of the two number entities – the pending values are stored under
#: the same names they are read with.
PV_QUOTA_KEY = "pv_quota_number"
MIN_CHARGING_QUOTA_KEY = "min_charging_quota_number"


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
    #: The car's name from the optional vehicle sensor (card, notifications).
    vehicle_name: str | None = None

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

    @property
    def charging_power_kw(self) -> float:
        return round(self.emobility_state.ev_charging_power.total / 1_000_000, 3)

    @property
    def effective_pv_quota(self) -> int:
        return int(
            self.charge_mode.min_pv_power_quota
            or self.charge_mode.last_min_pv_power_quota
            or 0
        )

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
    def charge_state(self) -> str:
        """idle / charging / locked – what the sensors and the card show."""
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
        store=None,
        pv_power_entity: str | None = None,
        battery_power_entity: str | None = None,
        min_cycle_power: float | None = None,
        min_cycle_seconds: float | None = None,
        noise_floor: float | None = None,
        debug_logging: bool = False,
        notify_enabled: bool = False,
        notify_service: str | None = None,
        notify_on_start: bool = False,
        notify_on_finish: bool = True,
        notify_vehicle_entity: str | None = None,
        instant_power: float | None = None,
    ) -> None:
        self.debug_logging = debug_logging
        self.notify_enabled = notify_enabled
        self.notify_service = notify_service
        self.notify_on_start = notify_on_start
        self.notify_on_finish = notify_on_finish
        self.notify_vehicle_entity = notify_vehicle_entity
        if instant_power is not None:
            self.INSTANT_CYCLE_POWER_KW = min(max(float(instant_power), 0.5), 22.0)
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
        self._pending_mode: str | None = None
        #: key -> (value, deadline) for the numbers the device has not confirmed
        self._pending_quota: dict[str, tuple[int, float]] = {}
        # per charging cycle
        self._session_energy_wh = 0.0
        self._gate_energy_wh = 0.0
        self._gate_grid_wh = 0.0
        self._gate_seconds = 0.0
        self._integrated_state_id = None
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

        # A restart in the middle of a charge must continue the cycle, not start a
        # new one: the restored counters would be wiped by the confirmation gate.
        ended = stored.get("ended")
        if ended is None:
            ended = self._session_energy_wh <= 0
        self._session_ended = bool(ended)
        self._charge_since = None
        self._energy_last_ts = None
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
                "ended": self._session_ended,
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
            vehicle_name=self._vehicle() or None,
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
    #: High power confirms a charge immediately, without the slow-start window.
    INSTANT_CYCLE_POWER_KW = DEFAULT_INSTANT_POWER
    #: A gentle start only counts as a session above this power …
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

    @callback
    def async_set_last_session(
        self,
        energy_kwh: float | None = None,
        energy_grid_kwh: float | None = None,
        energy_pv_kwh: float | None = None,
        duration_min: float | None = None,
        cost: float | None = None,
    ) -> None:
        """Overwrite the stored last session – for testing automations.

        The live counters are cleared, so the entities report these values until
        a real charge starts.
        """
        energy = max(float(energy_kwh or 0.0), 0.0)
        grid = max(float(energy_grid_kwh or 0.0), 0.0)
        pv = energy - grid if energy_pv_kwh is None else max(float(energy_pv_kwh), 0.0)

        session = {
            "energy_kwh": round(energy, 3),
            "energy_grid_kwh": round(grid, 3),
            "energy_pv_kwh": round(pv, 3),
            "duration_min": round(float(duration_min or 0.0), 1),
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "manual": True,
        }
        if cost is not None:
            session["cost"] = round(float(cost), 3)
        elif self.grid_price > 0 or self.pv_price > 0:
            session["cost"] = round(grid * self.grid_price + pv * self.pv_price, 3)

        self._last_session = session
        self._session_energy_wh = 0.0
        self._session_grid_wh = 0.0
        self._session_seconds = 0.0
        self._session_ended = True
        self._gate_energy_wh = 0.0
        self._gate_grid_wh = 0.0
        self._gate_seconds = 0.0
        self._charge_since = None
        self._unplugged_samples = 0
        self._energy_last_ts = None
        self._persist_session()

        if self.data is not None:
            self.data.last_session = dict(session)
            self.data.tracked_session_energy_wh = 0.0
            self.data.tracked_session_grid_wh = 0.0
            self.data.tracked_session_seconds = 0.0
        self.async_update_listeners()

    # -- notification / event side ---------------------------------------

    #: Used when a test notification is sent before any real charge happened.
    SAMPLE_SESSION = {
        "energy_kwh": 12.4,
        "energy_grid_kwh": 5.1,
        "energy_pv_kwh": 7.3,
        "duration_min": 48.0,
        "cost": 1.78,
    }

    def test_payload(self, kind: str = "finish") -> dict:
        """Data for a test event – the stored session if there is one."""
        if kind == "start":
            return {
                "mode": self._mode() or "hybrid",
                "price_per_kwh": self.grid_price,
                "vehicle": self._vehicle(),
                "test": True,
            }

        session = dict(self._last_session or {})
        if not session.get("energy_kwh"):
            session = dict(self.SAMPLE_SESSION)

        pv = float(session.get("energy_pv_kwh") or 0)
        return {
            "energy_kwh": session.get("energy_kwh", 0),
            "energy_grid_kwh": session.get("energy_grid_kwh", 0),
            "energy_pv_kwh": pv,
            "duration_min": session.get("duration_min", 0),
            "cost": session.get("cost"),
            "saved": round(pv * max(self.grid_price - self.pv_price, 0), 3),
            "mode": self._mode(),
            "vehicle": self._vehicle(),
            "ended_at": session.get("ended_at"),
            "test": True,
        }

    async def async_send_test(self, kind: str = "finish", send: bool = True) -> None:
        """Fire a test event, and optionally push the built-in message as well."""
        payload = self.test_payload(kind)
        event = (
            notifications.EVENT_STARTED if kind == "start" else notifications.EVENT_FINISHED
        )
        self._fire(event, payload)

        if not (send and self.notify_service and getattr(self, "hass", None)):
            return
        if kind == "start":
            title, body = notifications.start_messages(
                self.hass, payload["mode"], payload["price_per_kwh"], payload["vehicle"]
            )
        else:
            session = {**payload, "vehicle_entity": self.notify_vehicle_entity}
            title, body = notifications.finish_messages(self.hass, session, payload["saved"])
        await notifications.async_send(self.hass, self.notify_service, title, body)

    def _fire(self, event_type: str, data: dict) -> None:
        hass = getattr(self, "hass", None)
        if hass is None:
            return
        hass.bus.async_fire(event_type, data)

    def _mode(self) -> str | None:
        data = getattr(self, "data", None)
        if data is None:
            return None
        return getattr(getattr(data, "charge_mode", None), "mode", None)

    def _vehicle(self) -> str:
        hass = getattr(self, "hass", None)
        if hass is None:
            return ""
        return notifications.vehicle_name(
            hass, getattr(self, "notify_vehicle_entity", None)
        )

    @callback
    def _announce_start(self) -> None:
        """A confirmed charge begins – event, and a push if it is switched on."""
        try:
            self._announce_start_inner()
        except Exception:  # noqa: BLE001 - must not break the cycle bookkeeping
            _LOGGER.exception("Could not announce the start of the charge")

    def _announce_start_inner(self) -> None:
        mode = self._mode()
        data = {
            "mode": mode,
            "mode_label": notifications.mode_label(self.hass, mode),
            "price_per_kwh": self.grid_price,
            "vehicle": self._vehicle(),
        }
        self._fire(notifications.EVENT_STARTED, data)

        if (
            getattr(self, "notify_enabled", False)
            and getattr(self, "notify_on_start", False)
            and self.notify_service
            and getattr(self, "hass", None) is not None
        ):
            title, body = notifications.start_messages(
                self.hass, mode, self.grid_price, data["vehicle"]
            )
            hass = self.hass
            hass.async_create_task(
                notifications.async_send(hass, self.notify_service, title, body)
            )

    @callback
    def _announce_finish(self) -> None:
        """The cycle ended – event with the whole cycle, plus an optional push."""
        try:
            self._announce_finish_inner()
        except Exception:  # noqa: BLE001 - must not break the cycle bookkeeping
            _LOGGER.exception("Could not announce the end of the charge")

    def _announce_finish_inner(self) -> None:
        session = dict(self._last_session or {})
        if not session:
            return

        pv = float(session.get("energy_pv_kwh") or 0)
        saved = round(pv * max(self.grid_price - self.pv_price, 0), 3)
        data = {
            "energy_kwh": session.get("energy_kwh", 0),
            "energy_grid_kwh": session.get("energy_grid_kwh", 0),
            "energy_pv_kwh": pv,
            "duration_min": session.get("duration_min", 0),
            "cost": session.get("cost"),
            "saved": saved,
            "mode": self._mode(),
            "mode_label": notifications.mode_label(self.hass, self._mode()),
            # the car of *this* session, not whatever the sensor says now
            "vehicle": session.get("vehicle") or "",
            "ended_at": session.get("ended_at"),
        }
        self._fire(notifications.EVENT_FINISHED, data)

        if (
            getattr(self, "notify_enabled", False)
            and getattr(self, "notify_on_finish", True)
            and self.notify_service
            and getattr(self, "hass", None) is not None
        ):
            payload = dict(session)
            payload.pop("vehicle_entity", None)
            title, body = notifications.finish_messages(self.hass, payload, saved)
            hass = self.hass
            hass.async_create_task(
                notifications.async_send(hass, self.notify_service, title, body)
            )

    def _finish_cycle(self, previous: Optional[dict]) -> None:
        if self._session_energy_wh <= 0:
            return
        vehicle = None
        hass = getattr(self, "hass", None)
        if hass is not None:
            vehicle = notifications.vehicle_name(
                hass, getattr(self, "notify_vehicle_entity", None)
            )

        self._last_session = {
            # Which car it was – the card and a delayed message both read this.
            "vehicle": vehicle or None,
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
        self._gate_energy_wh = 0.0
        self._gate_grid_wh = 0.0
        self._gate_seconds = 0.0

    @callback
    def _accumulate_session_energy(self, state: EMobilityState) -> None:
        """Integrate the reported charging power over time."""
        now = time.monotonic()
        power_kw = state.ev_charging_power.total / 1_000_000
        running = not getattr(self, "_session_ended", True)

        # End the cycle only when the car is gone *and* nothing flows – for a few
        # samples in a row. A single misreported status frame must not close a
        # session, and one status flap during a pause must not either.
        if running and not getattr(self, "_plugged", True) and power_kw <= self.NOISE_FLOOR_KW:
            self._unplugged_samples = getattr(self, "_unplugged_samples", 0) + 1
            if self._unplugged_samples >= self.UNPLUG_CONFIRM_SAMPLES and self._session_energy_wh > 0:
                self._finish_cycle(self._session_prev)
                self._announce_finish()
                self._session_ended = True
                self._unplugged_samples = 0
                running = False
        else:
            self._unplugged_samples = 0

        # Track when the power crossed the gate, so a heartbeat of 0,11 kW cannot
        # pass for a charge.
        started = getattr(self, "_charge_since", None)
        instant_start = power_kw >= self.INSTANT_CYCLE_POWER_KW
        if power_kw >= self.MIN_CYCLE_POWER_KW or instant_start:
            if started is None:
                self._charge_since = started = now
        elif not running:
            self._charge_since = started = None
            # The candidate ended (power fell away): its buffer is worthless.
            self._gate_energy_wh = 0.0
            self._gate_grid_wh = 0.0
            self._gate_seconds = 0.0

        if not running:
            # Buffer candidates until either the instant power threshold or the
            # confirmation window is reached, preserving all candidate energy.
            previous = self._energy_last_ts
            self._energy_last_ts = now
            if power_kw > self.NOISE_FLOOR_KW and previous is not None:
                elapsed = now - previous
                if 0 < elapsed < 300:
                    hours = elapsed / 3600
                    energy_wh = power_kw * hours * 1000
                    self._gate_energy_wh += energy_wh
                    self._gate_seconds += elapsed
                    share_kw = self._grid_share_kw(power_kw)
                    self._gate_grid_wh += energy_wh if share_kw is None else share_kw * hours * 1000

            if not instant_start and (started is None or now - started < self.MIN_CYCLE_SECONDS):
                # Too short or too weak: keep the figures of the last session.
                return

            buffered = self._gate_energy_wh
            buffered_grid = self._gate_grid_wh
            buffered_seconds = self._gate_seconds

            self._reset_cycle()  # a real charge begins – start counting
            self._announce_start()
            self._session_energy_wh = buffered
            self._session_seconds = buffered_seconds
            self._session_grid_wh = min(buffered, buffered_grid)

        previous = self._energy_last_ts
        self._energy_last_ts = now

        if previous is None or power_kw <= self.NOISE_FLOOR_KW:
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

    #: The device accepts one connection at a time and sometimes not at all for a
    #: few seconds. Writes are retried and the UI shows the target value right
    #: away instead of waiting for the next poll.
    WRITE_ATTEMPTS = 3
    WRITE_RETRY_DELAY = 2.0
    #: How many samples in a row must say "car gone and nothing flows" before the
    #: cycle ends. At the default poll interval that is about a minute.
    UNPLUG_CONFIRM_SAMPLES = 3
    #: How long the optimistic value survives when the device never confirms it.
    PENDING_TIMEOUT = 20.0

    @property
    def pending_charge_mode(self) -> str | None:
        return self._pending_mode

    @property
    def pending_quota(self) -> int | None:
        """Compatibility view: the newest pending quota."""
        if not self._pending_quota:
            return None
        return max(self._pending_quota.values(), key=lambda v: v[1])[0]

    def pending_quota_for(self, key: str) -> int | None:
        entry = self._pending_quota.get(key)
        return entry[0] if entry else None

    async def _write_with_retry(self, func, *args) -> bool:
        """Run a blocking write in the executor, retrying a stalled device."""
        for attempt in range(self.WRITE_ATTEMPTS):
            try:
                await self.hass.async_add_executor_job(func, *args)
                return True
            except Exception as exc:  # noqa: BLE001
                last = exc
                if attempt + 1 < self.WRITE_ATTEMPTS:
                    _LOGGER.debug(
                        "Write to the eMS Home failed (%s), attempt %d/%d",
                        exc, attempt + 1, self.WRITE_ATTEMPTS,
                    )
                    await asyncio.sleep(self.WRITE_RETRY_DELAY)
        _LOGGER.warning(
            "The eMS Home did not accept the change after %d attempts: %s",
            self.WRITE_ATTEMPTS, last,
        )
        return False

    async def _clear_pending_later(self, delay: float) -> None:
        """Forget the optimistic values even if the device never confirms them."""
        await asyncio.sleep(delay)
        now = time.monotonic()
        stale = [k for k, (_, deadline) in self._pending_quota.items() if deadline <= now]
        if stale:
            for key in stale:
                self._pending_quota.pop(key, None)
        if self._pending_mode is not None and now >= self._pending_mode_deadline:
            self._pending_mode = None
        if stale or self._pending_mode is None:
            self.async_update_listeners()

    async def async_set_charge_mode(self, mode: str) -> None:
        """Select the charge mode, keeping the configured PV quota."""
        data = self.data
        pv_quota = data.effective_pv_quota if data else 0

        # Show the choice immediately – the device can take seconds to answer.
        self._pending_mode = mode
        self._pending_mode_deadline = time.monotonic() + self.PENDING_TIMEOUT
        self.async_update_listeners()

        if await self._write_with_retry(self._set_mode, mode, pv_quota):
            # Keep showing it until a poll reports it (or the timeout ends it).
            self.hass.async_create_task(self._clear_pending_later(self.PENDING_TIMEOUT))
        else:
            self._pending_mode = None
            self.async_update_listeners()
        await self.async_request_refresh()

    async def async_set_pv_quota(self, quota: int) -> None:
        """Write the minimum PV surplus quota while keeping the current mode."""
        data = self.data
        mode = data.charge_mode.mode if data else ChargeMode.HYBRID

        self._pending_quota[PV_QUOTA_KEY] = (
            quota,
            time.monotonic() + self.PENDING_TIMEOUT,
        )
        self.async_update_listeners()
        if await self._write_with_retry(self._set_quota, mode, quota):
            self.hass.async_create_task(self._clear_pending_later(self.PENDING_TIMEOUT))
        else:
            self._pending_quota.pop(PV_QUOTA_KEY, None)
            self._pending_quota.pop(MIN_CHARGING_QUOTA_KEY, None)
            self.async_update_listeners()
        await self.async_request_refresh()

    async def async_set_min_charging_quota(self, quota: int) -> None:
        """Write the minimum charging power quota (used by grid/hybrid)."""
        data = self.data
        mode = data.charge_mode.mode if data else ChargeMode.HYBRID
        pv_quota = data.effective_pv_quota if data else 0

        self._pending_quota[MIN_CHARGING_QUOTA_KEY] = (
            quota,
            time.monotonic() + self.PENDING_TIMEOUT,
        )
        self.async_update_listeners()
        if await self._write_with_retry(
            self.client.set_charge_mode, mode, quota, pv_quota
        ):
            self.hass.async_create_task(self._clear_pending_later(self.PENDING_TIMEOUT))
        else:
            self._pending_quota.pop(PV_QUOTA_KEY, None)
            self._pending_quota.pop(MIN_CHARGING_QUOTA_KEY, None)
            self.async_update_listeners()
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
