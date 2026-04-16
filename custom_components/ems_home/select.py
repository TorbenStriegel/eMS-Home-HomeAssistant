"""Select platform for eMS Home – charge mode control."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .ems_home_api import ChargeMode
from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import EMSHomeCoordinator

_LOGGER = logging.getLogger(__name__)

CHARGE_MODE_OPTIONS = [
    ChargeMode.LOCK,
    ChargeMode.GRID,
    ChargeMode.PV,
    ChargeMode.HYBRID,
]

CHARGE_MODE_ICONS = {
    ChargeMode.LOCK:   "mdi:lock",
    ChargeMode.GRID:   "mdi:transmission-tower",
    ChargeMode.PV:     "mdi:solar-power",
    ChargeMode.HYBRID: "mdi:solar-power-variant",
}

DEFAULT_PV_QUOTA = 100


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
    _attr_name = "Charge Mode"
    _attr_icon = "mdi:car-electric"
    _attr_options = CHARGE_MODE_OPTIONS

    def __init__(self, coordinator: EMSHomeCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_charge_mode_select"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="eMS Home",
            manufacturer="ABL",
            model="eMS Home",
            configuration_url=f"http://{entry.data['host']}:{entry.data.get('port', 80)}",
        )

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.charge_mode.mode

    @property
    def icon(self) -> str:
        return CHARGE_MODE_ICONS.get(self.current_option or "", "mdi:car-electric")

    async def async_select_option(self, option: str) -> None:
        data = self.coordinator.data
        pv_quota = DEFAULT_PV_QUOTA
        if data:
            quota = (
                data.charge_mode.min_pv_power_quota
                or data.charge_mode.last_min_pv_power_quota
            )
            if quota:
                pv_quota = quota

        await self.hass.async_add_executor_job(self._set_mode, option, pv_quota)
        await self.coordinator.async_request_refresh()

    def _set_mode(self, mode: str, pv_quota: int) -> None:
        client = self.coordinator.client
        if mode in (ChargeMode.PV, ChargeMode.HYBRID):
            client.set_charge_mode(mode, min_pv_power_quota=pv_quota)
        else:
            client.set_charge_mode(mode)
