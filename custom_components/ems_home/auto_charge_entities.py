"""Entities for the optional automatic charge release.

Only the runtime side lives here: arm, watch, report. The six thresholds are
configuration and sit in the entry options, like "lock after charge".
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    AUTO_CHARGE_STATES,
    DATA_AUTO_CHARGE,
    DATA_COORDINATOR,
    DOMAIN,
)
from .controller import AutoChargeController
from .coordinator import EMSHomeCoordinator

#: Unique-id suffixes of the beta.1 number/select entities. They are gone; the
#: registry keeps them as "restored" unless we remove them on purpose.
AUTO_LEGACY_SUFFIXES = (
    "_auto_surplus_start",
    "_auto_surplus_hold",
    "_auto_soc_full",
    "_auto_soc_min",
    "_auto_target_mode",
    "_auto_no_vehicle",
)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="eMS Home",
        manufacturer="ABL",
        model="eMS Home",
        model_id="ems-home",
    )


class _AutoEntity(CoordinatorEntity[EMSHomeCoordinator]):
    """Shared plumbing: device, controller, live updates."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EMSHomeCoordinator,
        controller: AutoChargeController,
        entry: ConfigEntry,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self.controller = controller
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_device_info = _device_info(entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.controller.add_listener(self._controller_updated))

    @callback
    def _controller_updated(self) -> None:
        self.async_write_ha_state()


class AutoChargeArmedSwitch(_AutoEntity, SwitchEntity):
    """Arm the one-shot release. Off does not stop a running charge."""

    _attr_translation_key = "auto_charge_armed"
    _attr_icon = "mdi:auto-mode"

    def __init__(self, coordinator, controller, entry) -> None:
        super().__init__(coordinator, controller, entry, "auto_charge_armed")

    @property
    def is_on(self) -> bool:
        return self.controller.armed

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.controller.async_set_armed(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.controller.async_set_armed(False)


class AutoChargeStateSensor(_AutoEntity, SensorEntity):
    """What the controller is doing right now, with the numbers behind it."""

    _attr_translation_key = "auto_charge_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(AUTO_CHARGE_STATES)
    _attr_icon = "mdi:car-clock"

    def __init__(self, coordinator, controller, entry) -> None:
        super().__init__(coordinator, controller, entry, "auto_charge_state")

    @property
    def native_value(self) -> str:
        return self.controller.state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.controller.attributes()


class AutoChargeProblemSensor(_AutoEntity, BinarySensorEntity):
    """On when the controller needs attention, not while it simply waits."""

    _attr_translation_key = "auto_charge_problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, controller, entry) -> None:
        super().__init__(coordinator, controller, entry, "auto_charge_problem")

    @property
    def is_on(self) -> bool:
        return self.controller.problem


def _controller(hass: HomeAssistant, entry: ConfigEntry) -> AutoChargeController | None:
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id) or {}
    return data.get(DATA_AUTO_CHARGE)


def _coordinator(hass: HomeAssistant, entry: ConfigEntry) -> EMSHomeCoordinator:
    return hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]


async def async_setup_switches(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    controller = _controller(hass, entry)
    if controller is None:
        return
    add([AutoChargeArmedSwitch(_coordinator(hass, entry), controller, entry)])


async def async_setup_sensor(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    controller = _controller(hass, entry)
    if controller is None:
        return
    add([AutoChargeStateSensor(_coordinator(hass, entry), controller, entry)])


async def async_setup_problem(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    controller = _controller(hass, entry)
    if controller is None:
        return
    add([AutoChargeProblemSensor(_coordinator(hass, entry), controller, entry)])


@callback
def async_remove_legacy_entities(hass: HomeAssistant, entry: ConfigEntry) -> int:
    """Delete the beta.1 threshold entities, exactly those and nothing else."""
    if not isinstance(getattr(hass, "data", None), dict) or getattr(hass, "states", None) is None:
        return 0  # unit-test hass without a registry
    registry = er.async_get(hass)
    wanted = {f"{entry.entry_id}{suffix}" for suffix in AUTO_LEGACY_SUFFIXES}
    removed = 0
    for item in er.async_entries_for_config_entry(registry, entry.entry_id):
        if item.unique_id in wanted and item.domain in ("number", "select"):
            registry.async_remove(item.entity_id)
            removed += 1
    return removed
