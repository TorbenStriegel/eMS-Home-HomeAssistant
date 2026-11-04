"""Number platform for eMS Home – load management sliders."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import EMSHomeCoordinator, EMSHomeData


@dataclass(kw_only=True)
class EMSNumberDescription(NumberEntityDescription):
    value_fn: Callable[[EMSHomeData], float | None]
    set_fn: Callable[[EMSHomeCoordinator, int], Awaitable[None]]


async def _set_pv_quota(coordinator: EMSHomeCoordinator, value: int) -> None:
    await coordinator.async_set_pv_quota(value)


async def _set_min_charging_quota(coordinator: EMSHomeCoordinator, value: int) -> None:
    await coordinator.async_set_min_charging_quota(value)


NUMBER_DESCRIPTIONS: tuple[EMSNumberDescription, ...] = (
    EMSNumberDescription(
        key="pv_quota_number",
        translation_key="pv_quota",
        icon="mdi:solar-power",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        value_fn=lambda d: float(d.effective_pv_quota),
        set_fn=_set_pv_quota,
    ),
    EMSNumberDescription(
        key="min_charging_quota_number",
        translation_key="min_charging_quota",
        icon="mdi:battery-charging-60",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_registry_enabled_default=False,
        value_fn=lambda d: float(d.charge_mode.min_charging_power_quota or 0),
        set_fn=_set_min_charging_quota,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up eMS Home number entities."""
    coordinator: EMSHomeCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities(
        EMSNumber(coordinator, entry, description) for description in NUMBER_DESCRIPTIONS
    )


class EMSNumber(CoordinatorEntity[EMSHomeCoordinator], NumberEntity):
    """A percentage slider written straight back to the eMS Home."""

    entity_description: EMSNumberDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EMSHomeCoordinator,
        entry: ConfigEntry,
        description: EMSNumberDescription,
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
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is None:
            return None
        try:
            return self.entity_description.value_fn(data)
        except (AttributeError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        if data is None:
            return {}
        return {"charge_mode": data.charge_mode.mode}

    async def async_set_native_value(self, value: float) -> None:
        await self.entity_description.set_fn(self.coordinator, int(round(value)))
