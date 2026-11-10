"""Binary sensors for eMS Home."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import EMSHomeCoordinator, EMSHomeData


@dataclass(kw_only=True)
class EMSBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[EMSHomeData], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[EMSBinarySensorDescription, ...] = (
    EMSBinarySensorDescription(
        key="ev_charging",
        translation_key="ev_charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        icon="mdi:ev-station",
        value_fn=lambda d: d.charge_state == "charging",
    ),
    EMSBinarySensorDescription(
        key="ev_plugged",
        translation_key="ev_plugged",
        device_class=BinarySensorDeviceClass.PLUG,
        icon="mdi:ev-plug-type2",
        value_fn=lambda d: (
            d.evse.is_plugged if d.evse is not None else d.charging_power_kw > 0
        ),
    ),
    EMSBinarySensorDescription(
        key="overload_protection",
        translation_key="overload_protection",
        # No PROBLEM: the flag means "the protection is currently limiting the
        # charging current", which is the feature doing its job, not a fault.
        icon="mdi:shield-check-outline",
        # Debounced: the firmware toggles the flag on single frames.
        value_fn=lambda d: d.overload_sustained,
    ),
    EMSBinarySensorDescription(
        key="smart_meter_connected",
        translation_key="smart_meter_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: None,
    ),
    EMSBinarySensorDescription(
        key="wallbox_connected",
        translation_key="wallbox_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EMSHomeCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities(
        EMSBinarySensor(coordinator, entry, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class EMSBinarySensor(CoordinatorEntity[EMSHomeCoordinator], BinarySensorEntity):
    """Binary sensor for charging/plugged state and stream health."""

    entity_description: EMSBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EMSHomeCoordinator,
        entry: ConfigEntry,
        description: EMSBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="eMS Home",
            manufacturer="ABL",
            model="eMS Home",
            model_id="ems-home",
        )

    @property
    def is_on(self) -> bool | None:
        key = self.entity_description.key
        if key == "smart_meter_connected":
            return self.coordinator.smart_meter_connected
        if key == "wallbox_connected":
            return self.coordinator.evse_connected
        data = self.coordinator.data
        if data is None:
            return None
        try:
            return self.entity_description.value_fn(data)
        except (AttributeError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> dict | None:
        key = self.entity_description.key
        stream = {
            "smart_meter_connected": self.coordinator.smart_meter_ws,
            "wallbox_connected": self.coordinator.evse_ws,
        }.get(key)
        if key == "overload_protection":
            data = self.coordinator.data
            if data is None:
                return None
            # What the device reported on the last poll – the state above is the
            # debounced version of it.
            return {"raw_active": data.overload_raw}
        if stream is None:
            return None
        return stream.stats.as_dict()
