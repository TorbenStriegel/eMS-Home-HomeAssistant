"""Select platform for eMS Home – charge mode control."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import EMSHomeCoordinator
from .ems_home_api import ChargeMode

_LOGGER = logging.getLogger(__name__)

CHARGE_MODE_OPTIONS = [
    ChargeMode.LOCK,
    ChargeMode.GRID,
    ChargeMode.PV,
    ChargeMode.HYBRID,
]

CHARGE_MODE_ICONS = {
    ChargeMode.LOCK: "mdi:lock",
    ChargeMode.GRID: "mdi:transmission-tower",
    ChargeMode.PV: "mdi:solar-power",
    ChargeMode.HYBRID: "mdi:solar-power-variant",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up eMS Home select entities."""
    coordinator: EMSHomeCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities([EMSChargeModeSelect(coordinator, entry)])


class EMSChargeModeSelect(CoordinatorEntity[EMSHomeCoordinator], SelectEntity):
    """Dropdown to select the active charge mode."""

    _attr_has_entity_name = True
    _attr_translation_key = "charge_mode"
    _attr_icon = "mdi:car-electric"
    _attr_options = CHARGE_MODE_OPTIONS

    def __init__(self, coordinator: EMSHomeCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_charge_mode_select"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="eMS Home",
            manufacturer="ABL",
            model="eMS Home",
            model_id="ems-home",
        )

    @property
    def current_option(self) -> str | None:
        pending = self.coordinator.pending_charge_mode
        if pending is not None and pending in self._attr_options:
            # Show what the user picked until the device confirms it.
            return pending
        if self.coordinator.data is None:
            return None
        mode = self.coordinator.data.charge_mode.mode
        return mode if mode in self._attr_options else None

    @property
    def icon(self) -> str:
        return CHARGE_MODE_ICONS.get(self.current_option or "", "mdi:car-electric")

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_charge_mode(option)
