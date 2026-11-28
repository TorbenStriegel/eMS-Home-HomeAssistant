"""Optional automatic charge release for eMS Home.

The integration does not regulate the charging current – the wallbox does that.
This module owns exactly one job: hold the wallbox in ``lock`` while the house
batteries still need the surplus, then release the charge **once** as soon as the
configured conditions are met. Everything the wallbox does afterwards is
observed, not steered, so a cloud cannot start a lock/hybrid ping-pong.

``AutoChargeCore`` is pure logic with an injectable clock: no Home Assistant, no
I/O. The controller below feeds it and performs the two side effects it asks
for (write a mode, send a message).
"""
from __future__ import annotations

import logging
import asyncio
import time
import uuid
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Callable

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .const import (
    AUTO_CHARGE_STATES,
    CONF_AUTO_NO_VEHICLE,
    CONF_AUTO_SOC_FULL,
    CONF_AUTO_SOC_MIN,
    CONF_AUTO_SURPLUS_HOLD,
    CONF_AUTO_SURPLUS_START,
    CONF_AUTO_TARGET,
    AUTO_NO_VEHICLE_POLICIES,
    AUTO_TARGET_MODES,
    DEFAULT_AUTO_NO_VEHICLE,
    DEFAULT_AUTO_SOC_FULL_PCT,
    DEFAULT_AUTO_SOC_MIN_PCT,
    DEFAULT_AUTO_SURPLUS_HOLD_S,
    DEFAULT_AUTO_SURPLUS_START_W,
    DEFAULT_AUTO_TARGET_MODE,
    DOMAIN,
)
from .coordinator import EMSHomeCoordinator

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
#: A mode write the device has not confirmed within this window is a failure.
CONFIRM_TIMEOUT = 45.0
#: A car that was seen plugged in only counts as gone after this long unplugged.
UNPLUG_CONFIRM_S = 60.0
#: A release that never produced a single watt ends here instead of waiting forever.
NO_CHARGE_TIMEOUT = 900.0
#: Do not trust a single frame when deciding that the car left.
CHARGING_POWER_KW = 0.05


@dataclass
class AutoChargeSettings:
    """Values the user adjusts in everyday life (entities, not options)."""

    surplus_start_w: float = DEFAULT_AUTO_SURPLUS_START_W
    surplus_hold_s: int = DEFAULT_AUTO_SURPLUS_HOLD_S
    soc_full_pct: int = DEFAULT_AUTO_SOC_FULL_PCT
    soc_min_pct: int = DEFAULT_AUTO_SOC_MIN_PCT
    target_mode: str = DEFAULT_AUTO_TARGET_MODE
    no_vehicle: str = DEFAULT_AUTO_NO_VEHICLE


def validate_settings(settings: AutoChargeSettings) -> AutoChargeSettings:
    """Clamp and cross-check, so neither a typo nor a restored store can hurt."""
    start = min(max(float(settings.surplus_start_w), 200.0), 30000.0)
    hold = min(max(int(settings.surplus_hold_s), 0), 3600)
    soc_min = min(max(int(settings.soc_min_pct), 0), 95)
    soc_full = min(max(int(settings.soc_full_pct), soc_min + 1), 99)
    target = settings.target_mode if settings.target_mode in AUTO_TARGET_MODES else DEFAULT_AUTO_TARGET_MODE
    policy = (
        settings.no_vehicle
        if settings.no_vehicle in AUTO_NO_VEHICLE_POLICIES
        else DEFAULT_AUTO_NO_VEHICLE
    )
    return replace(
        settings,
        surplus_start_w=start,
        surplus_hold_s=hold,
        soc_min_pct=soc_min,
        soc_full_pct=soc_full,
        target_mode=target,
        no_vehicle=policy,
    )


def settings_from_options(options: dict[str, Any]) -> AutoChargeSettings:
    """The six thresholds come from the entry options; missing keys mean default."""
    defaults = AutoChargeSettings()
    try:
        return validate_settings(
            AutoChargeSettings(
                surplus_start_w=float(
                    options.get(CONF_AUTO_SURPLUS_START, defaults.surplus_start_w)
                ),
                surplus_hold_s=int(
                    options.get(CONF_AUTO_SURPLUS_HOLD, defaults.surplus_hold_s)
                ),
                soc_full_pct=int(options.get(CONF_AUTO_SOC_FULL, defaults.soc_full_pct)),
                soc_min_pct=int(options.get(CONF_AUTO_SOC_MIN, defaults.soc_min_pct)),
                target_mode=str(
                    options.get(CONF_AUTO_TARGET, defaults.target_mode) or defaults.target_mode
                ),
                no_vehicle=str(
                    options.get(CONF_AUTO_NO_VEHICLE, defaults.no_vehicle)
                    or defaults.no_vehicle
                ),
            )
        )
    except (TypeError, ValueError):
        _LOGGER.warning("Auto charge options are unreadable, using the defaults")
        return validate_settings(defaults)


@dataclass(frozen=True)
class Snapshot:
    """Everything one decision needs, already normalised."""

    mode: str | None = None          # confirmed device mode
    plugged: bool | None = None      # None = unknown
    #: The car was seen plugged in and the latest reading says unplugged, but not
    #: for long enough to count as gone. It still counts as plugged for the wait,
    #: so a single bad frame neither shows "no vehicle" nor restarts the hold,
    #: but nothing is released into a car that may have left.
    plug_settling: bool = False
    soc: float | None = None         # house battery, %
    #: False when no house battery sensor is configured: only the export path
    #: counts then. True with a missing value is still "data missing".
    battery: bool = True
    surplus_w: float | None = None   # feed-in, W
    charging: bool = False
    session_ended: bool = False
    device_ok: bool = True


@dataclass
class Decision:
    state: str
    reason: str | None = None
    #: Mode the caller should write, or None.
    action: str | None = None


@dataclass
class AutoChargeCore:
    """The state machine. Feed it snapshots, act on the returned mode."""

    settings: AutoChargeSettings = field(default_factory=AutoChargeSettings)
    armed: bool = False
    released: bool = False
    charge_seen: bool = False
    state: str = "off"
    reason: str | None = None
    run_id: str | None = None
    surplus_since: float | None = None
    released_at: float | None = None
    expected_mode: str | None = None
    expected_until: float | None = None
    finished: bool = False

    # ---- user actions -------------------------------------------------
    def arm(self, now: float) -> Decision:
        """Arm the controller: hold the wallbox in lock and watch the sources."""
        self.armed = True
        self.released = False
        self.charge_seen = False
        self.finished = False
        self.surplus_since = None
        self.run_id = uuid.uuid4().hex[:12]
        self.expected_mode = "lock"
        self.expected_until = now + CONFIRM_TIMEOUT
        self.state = "arming"
        self.reason = "armed_by_user"
        return Decision("arming", self.reason, "lock")

    def disarm(self, now: float) -> Decision:
        """Drop the order. A running charge is never stopped by this."""
        was_holding = self.armed and not self.released
        self.armed = False
        self.expected_mode = None
        self.expected_until = None
        self.surplus_since = None
        if was_holding:
            # Only the hold is undone: back to the mode a user would expect.
            self.state = "off"
            self.reason = "disarmed_by_user"
            return Decision("off", self.reason, "hybrid")
        self.state = "off" if not self.released else self.state
        self.reason = "disarmed_by_user"
        return Decision(self.state, self.reason, None)

    # ---- the machine --------------------------------------------------
    def step(self, snap: Snapshot, now: float) -> Decision:
        # A write we are still waiting for wins over everything else.
        if self.expected_mode is not None:
            if snap.mode == self.expected_mode:
                return self._confirm(now)
            if self.expected_until is not None and now >= self.expected_until:
                self.armed = False
                self.expected_mode = None
                return self._set("conflict_external", "mode_not_confirmed")
            return Decision(self.state, self.reason)

        # After the release the wallbox owns the current; we only watch.
        if self.released:
            return self._observe(snap, now)

        if not self.armed:
            self.state = "finished" if self.finished else "off"
            return Decision(self.state, self.reason)

        if not snap.device_ok or snap.mode is None:
            # A gap breaks the "uninterrupted" qualification: the export may have
            # dropped while nobody was looking, so the hold starts again.
            self.surplus_since = None
            return self._set("degraded_unavailable", "no_device_data")

        # Somebody else changed the mode: their choice wins, we never write back.
        if snap.mode != "lock":
            self.armed = False
            return self._set("conflict_external", "mode_changed")

        vehicle_confirmed = True
        if self.settings.no_vehicle == "wait":
            vehicle_confirmed = not snap.plug_settling
            if snap.plugged is None:
                self.surplus_since = None
                return self._set("degraded_unavailable", "plugged_unknown")
            if not snap.plugged:
                # Nobody watches the export for the release while the car is away,
                # so a dip in that time would go unseen: the hold starts again.
                self.surplus_since = None
                return self._set("blocked_no_vehicle", "no_vehicle")

        soc = snap.soc
        if snap.battery:
            if soc is None:
                self.surplus_since = None
                return self._set("degraded_unavailable", "soc_unavailable")
            if soc <= self.settings.soc_min_pct:
                # Part of the export path. The full path cannot hold here either,
                # because the full level is always above the minimum.
                self.surplus_since = None
                return self._set("waiting_soc", "soc_below_min")

        # Every input of the rule must be known before either path may release: a full
        # battery next to a dead export sensor is still "data missing", not a release.
        if snap.surplus_w is None:
            self.surplus_since = None
            return self._set("degraded_unavailable", "surplus_unavailable")

        full = snap.battery and soc is not None and soc > self.settings.soc_full_pct
        surplus = snap.surplus_w is not None and snap.surplus_w > self.settings.surplus_start_w
        if surplus and self.surplus_since is None:
            self.surplus_since = now
        elif not surplus:
            self.surplus_since = None
        surplus_ready = (
            self.surplus_since is not None
            and now - self.surplus_since >= self.settings.surplus_hold_s
        )

        if not full and not surplus_ready:
            return self._set("waiting_surplus", "surplus_too_low")
        if not vehicle_confirmed:
            # The rule holds, the car does not: wait without restarting the hold.
            return self._set("blocked_no_vehicle", "vehicle_unconfirmed")

        # Release exactly once. A later manual change is nobody's business but the user's.
        self.armed = False
        self.released = True
        self.charge_seen = False
        self.released_at = now
        self.expected_mode = self.settings.target_mode
        self.expected_until = now + CONFIRM_TIMEOUT
        reason = "battery_full" if full else "surplus_reached"
        self.state = "starting"
        return Decision("starting", reason, self.settings.target_mode)

    # ---- internals ----------------------------------------------------
    def _confirm(self, now: float) -> Decision:
        mode, self.expected_mode, self.expected_until = self.expected_mode, None, None
        if mode == "lock":
            return self._set("armed", "hold_confirmed")
        self.state = "released"
        self.reason = "release_confirmed"
        return Decision(self.state, self.reason)

    def _observe(self, snap: Snapshot, now: float) -> Decision:
        if snap.charging:
            self.charge_seen = True
            return self._set("charging", "charging")
        if self.charge_seen and (snap.session_ended or snap.plugged is False):
            self.finished = True
            self.released = False
            return self._set("finished", "charge_ended")
        if (
            not self.charge_seen
            and self.released_at is not None
            and now - self.released_at >= NO_CHARGE_TIMEOUT
        ):
            self.finished = True
            self.released = False
            return self._set("finished", "no_charge")
        return Decision(self.state, self.reason)

    def _set(self, state: str, reason: str | None) -> Decision:
        self.state = state
        self.reason = reason
        return Decision(state, reason)

    # ---- persistence --------------------------------------------------
    def as_store(self) -> dict[str, Any]:
        # Only what survives a reboot. surplus_since, released_at, expected_mode and
        # expected_until are time.monotonic() values: after a reboot they point at a
        # different clock, and a stale expected_until keeps a release "starting" for
        # days (until the new uptime happens to pass the old timestamp).
        return {
            "armed": self.armed,
            "released": self.released,
            "charge_seen": self.charge_seen,
            "state": self.state,
            "reason": self.reason,
            "run_id": self.run_id,
            "finished": self.finished,
        }

    @staticmethod
    def _flag(value: Any) -> bool:
        """Only a real true counts: "false", 0 and None are false."""
        if value is True:
            return True
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value == 1
        return False

    def restore(self, data: dict[str, Any], *, now: float | None = None) -> None:
        # Settings are configuration and live in the options; an old store must
        # not overwrite them.
        if not isinstance(data, dict):
            return
        self.armed = self._flag(data.get("armed"))
        self.released = self._flag(data.get("released"))
        self.charge_seen = self._flag(data.get("charge_seen"))
        state = str(data.get("state") or "off")
        self.state = state if state in AUTO_CHARGE_STATES else "off"
        self.reason = data.get("reason")
        self.run_id = data.get("run_id")
        self.finished = self._flag(data.get("finished"))
        # Never adopt the previous boot's monotonic stamps, not even from an old store.
        self.surplus_since = None
        self.expected_mode = None
        self.expected_until = None
        self.released_at = now if self.released else None
        if self.released and self.state == "starting":
            # We cannot know whether the write landed before the restart: watch the
            # device and let the no-charge timeout start now, not at an old timestamp.
            self.state = "released"
            self.reason = "restarted_mid_release"
        if self.armed:
            # After a restart nobody can prove the hold still exists: let the
            # first step decide, with no timer carried over.
            self.surplus_since = None
            self.expected_mode = None
            self.expected_until = None
            self.state = "armed"


class AutoChargeController:
    """Feeds the core from Home Assistant, performs its writes, persists state."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: EMSHomeCoordinator,
        entry_id: str,
        *,
        surplus_entity: str | None,
        soc_entity: str | None,
        guard_entity: str | None,
        settings: AutoChargeSettings | None = None,
    ) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.entry_id = entry_id
        self.surplus_entity = surplus_entity
        self.soc_entity = soc_entity
        self.guard_entity = guard_entity
        self.core = AutoChargeCore(settings=validate_settings(settings or AutoChargeSettings()))
        self.blocking_entity: str | None = None
        self._fingerprint: tuple | None = None
        self.last_origin = "start"
        self._store: Store = Store(hass, STORE_VERSION, f"{DOMAIN}.auto_charge.{entry_id}")
        self._timer: CALLBACK_TYPE | None = None
        self._unsub: CALLBACK_TYPE | None = None
        self._unplug_since: float | None = None
        self._seen_plugged = False
        self._loaded = False
        self._monotonic = time.monotonic
        self._listeners: list[Callable[[], None]] = []
        # One evaluation at a time: a burst of stream frames must not interleave two
        # writes or persist a stale fingerprint. The task is tracked so unload can
        # cancel it: a write after unload would reach a device nobody watches.
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._stopped = False

    # ---- lifecycle ----------------------------------------------------
    async def async_start(self) -> None:
        self._stopped = False
        try:
            stored = await self._store.async_load()
        except Exception as exc:  # noqa: BLE001 - the integration has to keep working
            _LOGGER.warning("Could not load the auto charge state, starting off: %s", exc)
            stored = None
        if isinstance(stored, dict):
            try:
                self.core.restore(stored, now=self._monotonic())
            except Exception as exc:  # noqa: BLE001 - an old shape is not a crash
                _LOGGER.warning("Ignoring a damaged auto charge state: %s", exc)
        self._loaded = True
        self._unsub = self.coordinator.async_add_listener(self._on_update)
        await self.async_evaluate()

    @callback
    def async_stop(self) -> None:
        self._stopped = True
        self._cancel_timer()
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    # ---- public API ---------------------------------------------------
    @property
    def state(self) -> str:
        return self.core.state

    @property
    def armed(self) -> bool:
        return self.core.armed

    @property
    def settings(self) -> AutoChargeSettings:
        return self.core.settings

    def add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(listener)

        @callback
        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    async def async_set_armed(self, armed: bool, *, origin: str = "user") -> None:
        blocked, blocker = self._guard_blocks()
        if blocked and not armed:
            # The guard owns the wallbox: clearing our order must not write a mode
            # behind its back, the same rule that keeps us from locking it.
            self.blocking_entity = blocker
            self.core.armed = False
            self.core.expected_mode = None
            self.core.state = "conflict_external" if self.core.released else "off"
            self.core.reason = "external_control"
            await self._persist()
            self._notify()
            return
        if armed:
            # An external controller owns the wallbox: do not even request lock.
            if blocked:
                self.blocking_entity = blocker
                self.core.armed = False
                self.core.expected_mode = None
                self.core.state = "conflict_external"
                self.core.reason = "external_control"
                await self._persist()
                self._notify()
                return
        self.last_origin = origin
        now = self._monotonic()
        decision = self.core.arm(now) if armed else self.core.disarm(now)
        _LOGGER.info(
            "Auto charge %s via %s: %s (%s)",
            "armed" if armed else "disarmed",
            origin,
            decision.state,
            decision.reason,
        )
        if decision.action:
            await self._write_mode(decision.action)
        await self._persist()
        self._notify()
        self._schedule()

    async def async_apply_options(self, options: dict[str, Any]) -> None:
        """Thresholds changed in the options: apply without reloading the entry."""
        settings = settings_from_options(options)
        if settings == self.core.settings:
            return
        self.core.settings = settings
        # A new threshold invalidates a running qualification, not the order.
        self.core.surplus_since = None
        self._schedule()
        await self._persist()
        self._notify()
        await self.async_evaluate()

    async def async_evaluate(self) -> None:
        if not self._loaded or self._stopped:
            return
        async with self._lock:
            if self._stopped:
                return
            await self._evaluate_locked()

    async def _evaluate_locked(self) -> None:
        blocked, blocker = self._guard_blocks()
        self.blocking_entity = blocker
        if blocked:
            # An external controller owns the wallbox. We never write against it,
            # and we never claim a release happened. Idle stays idle: a guard that
            # is on while nothing was armed is not a conflict.
            core = self.core
            if core.armed or core.released:
                _LOGGER.info("Auto charge yields to %s", blocker)
                core.state = "conflict_external"
                core.reason = "external_control"
            elif core.finished:
                core.state, core.reason = "finished", core.reason or "charge_ended"
            else:
                core.state, core.reason = "off", None
            core.armed = False
            core.released = False
            core.expected_mode = None
            core.expected_until = None
            core.surplus_since = None
        else:
            decision = self.core.step(self._snapshot(), self._monotonic())
            if decision.action:
                await self._write_mode(decision.action)
        await self._persist()
        self._notify()
        self._schedule()

    # ---- internals ----------------------------------------------------
    @callback
    def _on_update(self) -> None:
        self._spawn()

    def _spawn(self) -> None:
        """Start one evaluation; a burst coalesces instead of queueing."""
        if self._stopped or not self._loaded:
            return
        if self._task is not None and not self._task.done():
            return
        self._task = self.hass.async_create_task(self.async_evaluate())

    def _snapshot(self, *, track_unplug: bool = True) -> Snapshot:
        data = self.coordinator.data
        # The coordinator keeps the last object after a failed poll: without this
        # check the automatic would treat stale data as a healthy device and release.
        if data is None or getattr(self.coordinator, "last_update_success", True) is False:
            return Snapshot(device_ok=False)
        evse = data.evse
        plugged: bool | None
        settling = False
        if evse is None:
            plugged = None
        elif not track_unplug:
            plugged = evse.is_plugged
        elif evse.is_plugged:
            plugged = True
            self._seen_plugged = True
            self._unplug_since = None
        elif self._seen_plugged:
            # A car we saw plugged in reads unplugged: one bad frame must not look
            # like a car that left, so it counts as plugged for a while. It never
            # counts as confirmed, though, and the core does not release meanwhile.
            now = self._monotonic()
            if self._unplug_since is None:
                self._unplug_since = now
            if now - self._unplug_since < UNPLUG_CONFIRM_S:
                plugged = True
                settling = True
            else:
                plugged = False
                self._seen_plugged = False
                self._unplug_since = None
        else:
            # Never seen plugged since the start, or already confirmed gone: no car.
            # Treating this as plugged would release into the void after a restart.
            plugged = False
        charging = bool(
            (evse is not None and evse.is_charging)
            or (data.charging_power_kw or 0) > CHARGING_POWER_KW
        )
        return Snapshot(
            mode=getattr(data.charge_mode, "mode", None),
            plugged=plugged,
            plug_settling=settling,
            battery=self.soc_entity is not None,
            soc=self._read_soc(),
            surplus_w=self._read_surplus(),
            charging=charging,
            session_ended=bool(data.session_ended),
            device_ok=True,
        )

    def _guard_blocks(self) -> tuple[bool, str | None]:
        if not self.guard_entity:
            return False, None
        state = self.hass.states.get(self.guard_entity)
        if state is None:
            return True, self.guard_entity
        if state.state in ("on", "unknown", "unavailable"):
            return True, self.guard_entity
        return False, None

    def _read_number(self, entity_id: str | None, *, scale: dict[str, float] | None = None) -> float | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None
        if scale:
            unit = str((state.attributes or {}).get("unit_of_measurement") or "")
            value *= scale.get(unit, 1.0)
        return value

    def _read_soc(self) -> float | None:
        return self._read_number(self.soc_entity)

    def _read_surplus(self) -> float | None:
        return self._read_number(self.surplus_entity, scale={"kW": 1000.0, "W": 1.0})

    async def _write_mode(self, mode: str) -> bool:
        try:
            await self.coordinator.async_set_charge_mode(mode)
        except Exception as exc:  # noqa: BLE001 - a failed write must not kill the cycle
            _LOGGER.warning("Auto charge could not write mode %s: %s", mode, exc)
            self.core.expected_mode = None
            self.core.armed = False
            self.core.state = "degraded_unavailable"
            self.core.reason = "mode_write_failed"
            return False
        return True

    def _schedule(self) -> None:
        self._cancel_timer()
        delay: float | None = None
        now = self._monotonic()
        core = self.core
        if core.expected_until is not None:
            delay = max(core.expected_until - now, 1.0)
        elif core.surplus_since is not None and not core.released:
            remaining = core.settings.surplus_hold_s - (now - core.surplus_since)
            delay = max(remaining, 1.0)
        if self._unplug_since is not None and self._seen_plugged and core.armed:
            # Decide the unplugged car even if no frame arrives in the meantime.
            settle = max(UNPLUG_CONFIRM_S - (now - self._unplug_since), 1.0)
            delay = settle if delay is None else min(delay, settle)
        if delay is None:
            return
        self._timer = async_call_later(
            self.hass, min(delay, 3600.0), self._timer_fired
        )

    @callback
    def _timer_fired(self, _now: Any) -> None:
        self._timer = None
        self._spawn()

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer()
            self._timer = None

    def _notify(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:  # noqa: BLE001 - one broken entity must not stop the rest
                _LOGGER.debug("Auto charge listener failed", exc_info=True)

    async def _persist(self) -> None:
        core = self.core
        fingerprint = (
            core.state,
            core.reason,
            core.armed,
            core.released,
            core.charge_seen,
            core.run_id,
            core.finished,
            tuple(sorted(asdict(core.settings).items())),
        )
        if fingerprint == self._fingerprint:
            return  # a stream frame every second must not write the store
        try:
            await self._store.async_save(self.core.as_store())
        except Exception as exc:  # noqa: BLE001 - persistence must not break charging
            # Do not remember the fingerprint: the next tick may succeed, and a lost
            # order must not be lost silently until the next state change.
            self._fingerprint = None
            _LOGGER.warning("Could not store the auto charge state: %s", exc)
            return
        self._fingerprint = fingerprint

    @property
    def problem(self) -> bool:
        """True only for states a user should act on, not for normal waiting."""
        return self.core.state in ("degraded_unavailable", "conflict_external")

    # ---- attributes for the state sensor ------------------------------
    def attributes(self) -> dict[str, Any]:
        core = self.core
        # Reading attributes is not an evaluation: no side effects on the unplug timer.
        snap = self._snapshot(track_unplug=False)
        deficit = None
        if snap.surplus_w is not None:
            deficit = max(0, round(core.settings.surplus_start_w - snap.surplus_w))
        return {
            "armed": core.armed,
            "released": core.released,
            "run_id": core.run_id,
            "reason_code": core.reason,
            "target_mode": core.settings.target_mode,
            "surplus_w": None if snap.surplus_w is None else round(snap.surplus_w),
            "soc": None if snap.soc is None else round(snap.soc, 1),
            "surplus_deficit_w": deficit,
            "confirmed_mode": snap.mode,
            "last_command_origin": self.last_origin,
            "blocking_entity": self.blocking_entity,
            "next_transition_at": (
                None if core.expected_until is None else round(core.expected_until, 3)
            ),
            # Seconds the feed-in has to stay above the threshold, for the card's
            # countdown. None while the surplus path is not qualifying.
            "hold_remaining_s": (
                None
                if core.surplus_since is None or core.released
                else max(0, round(core.settings.surplus_hold_s - (self._monotonic() - core.surplus_since)))
            ),
            # `battery` tells the card which rule to show: without a house battery
            # sensor only the export path exists.
            "settings": {**asdict(core.settings), "battery": self.soc_entity is not None},
        }
