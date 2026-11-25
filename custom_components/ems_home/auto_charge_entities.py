"""Entities for the optional automatic charge release.

Everything lives on the existing eMS Home device, so a user finds it next to the
charge mode rather than in a second device. Names come from translation keys;
unique_ids end with a stable suffix the card uses for auto-discovery.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.components.select import SelectEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    AUTO_CHARGE_STATES,
    AUTO_NO_VEHICLE_POLICIES,
    AUTO_TARGET_MODES,
    CONF_AUTO_CHARGE_ENABLED,
    DATA_AUTO_CHARGE,
    DATA_COORDINATOR,
    DOMAIN,
)
from .controller import AutoChargeController
from .coordinator import EMSHomeCoordinator


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


@dataclass(kw_only=True)
class AutoNumberDescription:
    key: str
    attribute: str
    translation_key: str
    minimum: float
    maximum: float
    step: float
    unit: str | None = None
    device_class: NumberDeviceClass | None = None
    icon: str | None = None
    digits: int = 0


AUTO_NUMBER_DESCRIPTIONS: tuple[AutoNumberDescription, ...] = (
    AutoNumberDescription(
        key="auto_surplus_start",
        attribute="surplus_start_w",
        translation_key="auto_surplus_start",
        minimum=200,
        maximum=30000,
        step=100,
        unit=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        icon="mdi:transmission-tower-export",
    ),
    AutoNumberDescription(
        key="auto_surplus_hold",
        attribute="surplus_hold_s",
        translation_key="auto_surplus_hold",
        minimum=0,
        maximum=3600,
        step=10,
        unit=UnitOfTime.SECONDS,
        device_class=NumberDeviceClass.DURATION,
        icon="mdi:timer-outline",
    ),
    AutoNumberDescription(
        key="auto_soc_full",
        attribute="soc_full_pct",
        translation_key="auto_soc_full",
        minimum=20,
        maximum=99,
        step=1,
        unit=PERCENTAGE,
        icon="mdi:battery-heart-variant",
    ),
    AutoNumberDescription(
        key="auto_soc_min",
        attribute="soc_min_pct",
        translation_key="auto_soc_min",
        minimum=0,
        maximum=95,
        step=1,
        unit=PERCENTAGE,
        icon="mdi:battery-50",
    ),
)


class AutoChargeNumber(_AutoEntity, NumberEntity):
    """A threshold the controller reads live, without reloading the entry."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, controller, entry, description: AutoNumberDescription) -> None:
        super().__init__(coordinator, controller, entry, description.key)
        self._auto = description
        self._attr_translation_key = description.translation_key
        self._attr_native_min_value = description.minimum
        self._attr_native_max_value = description.maximum
        self._attr_native_step = description.step
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_icon = description.icon

    @property
    def native_value(self) -> float:
        return float(getattr(self.controller.settings, self._auto.attribute))

    async def async_set_native_value(self, value: float) -> None:
        attribute = self._auto.attribute
        cast = int if attribute.endswith(("_s", "_pct")) else float
        await self.controller.async_update_settings(**{attribute: cast(value)})


@dataclass(kw_only=True)
class AutoSelectDescription:
    key: str
    attribute: str
    translation_key: str
    options: tuple[str, ...]
    icon: str | None = None


AUTO_SELECT_DESCRIPTIONS: tuple[AutoSelectDescription, ...] = (
    AutoSelectDescription(
        key="auto_target_mode",
        attribute="target_mode",
        translation_key="auto_target_mode",
        options=AUTO_TARGET_MODES,
        icon="mdi:solar-power",
    ),
    AutoSelectDescription(
        key="auto_no_vehicle",
        attribute="no_vehicle",
        translation_key="auto_no_vehicle",
        options=AUTO_NO_VEHICLE_POLICIES,
        icon="mdi:car-off",
    ),
)


class AutoChargeSelect(_AutoEntity, SelectEntity):
    """A policy the controller reads live."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, controller, entry, description: AutoSelectDescription) -> None:
        super().__init__(coordinator, controller, entry, description.key)
        self._auto = description
        self._attr_translation_key = description.translation_key
        self._attr_options = list(description.options)
        self._attr_icon = description.icon

    @property
    def current_option(self) -> str:
        return str(getattr(self.controller.settings, self._auto.attribute))

    async def async_select_option(self, option: str) -> None:
        await self.controller.async_update_settings(**{self._auto.attribute: option})


def _controller(hass: HomeAssistant, entry: ConfigEntry) -> AutoChargeController | None:
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id) or {}
    return data.get(DATA_AUTO_CHARGE)


async def async_setup_switches(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    controller = _controller(hass, entry)
    if controller is None:
        return
    add([AutoChargeArmedSwitch(_coordinator(hass, entry), controller, entry)])


async def async_setup_numbers(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    controller = _controller(hass, entry)
    if controller is None:
        return
    coordinator = _coordinator(hass, entry)
    add(
        AutoChargeNumber(coordinator, controller, entry, description)
        for description in AUTO_NUMBER_DESCRIPTIONS
    )


async def async_setup_selects(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    controller = _controller(hass, entry)
    if controller is None:
        return
    coordinator = _coordinator(hass, entry)
    add(
        AutoChargeSelect(coordinator, controller, entry, description)
        for description in AUTO_SELECT_DESCRIPTIONS
    )


async def async_setup_sensor(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    controller = _controller(hass, entry)
    if controller is None:
        return
    coordinator = _coordinator(hass, entry)
    add([AutoChargeStateSensor(coordinator, controller, entry)])


async def async_setup_problem(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    controller = _controller(hass, entry)
    if controller is None:
        return
    add([AutoChargeProblemSensor(_coordinator(hass, entry), controller, entry)])


def _coordinator(hass: HomeAssistant, entry: ConfigEntry) -> EMSHomeCoordinator:
    return hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]


def auto_charge_enabled(options: dict[str, Any]) -> bool:
    return bool(options.get(CONF_AUTO_CHARGE_ENABLED, False))
