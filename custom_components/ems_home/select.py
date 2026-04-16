"""Select and Number platforms for eMS Home charge mode control."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
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


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="eMS Home",
        manufacturer="ABL",
        model="eMS Home",
        configuration_url=f"http://{entry.data['host']}:{entry.data.get('port', 80)}",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up eMS Home select and number entities."""
    coordinator: EMSHomeCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    async_add_entities([
        EMSChargeModeSelect(coordinator, entry),
        EMSPVQuotaNumber(coordinator, entry),
    ])


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
        self._attr_device_info = _device_info(entry)

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
            if quota is not None:
                pv_quota = quota

        await self.hass.async_add_executor_job(self._set_mode, option, pv_quota)
        await self.coordinator.async_request_refresh()

    def _set_mode(self, mode: str, pv_quota: int) -> None:
        client = self.coordinator.client
        if mode in (ChargeMode.PV, ChargeMode.HYBRID):
            client.set_charge_mode(mode, min_pv_power_quota=pv_quota)
        else:
            client.set_charge_mode(mode)


class EMSPVQuotaNumber(CoordinatorEntity[EMSHomeCoordinator], NumberEntity):
    """Slider (0–100 %) for the minimum PV surplus quota."""

    _attr_has_entity_name = True
    _attr_name = "Min PV Power Quota"
    _attr_icon = "mdi:solar-power"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: EMSHomeCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_pv_quota_number"
        self._attr_device_info = _device_info(entry)
        self._last_known_quota: int = DEFAULT_PV_QUOTA

    @property
    def native_value(self) -> float:
        if self.coordinator.data is not None:
            cm = self.coordinator.data.charge_mode
            quota = cm.min_pv_power_quota or cm.last_min_pv_power_quota
            if quota is not None:
                self._last_known_quota = int(quota)
        return float(self._last_known_quota)

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        return {"charge_mode": self.coordinator.data.charge_mode.mode}

    async def async_set_native_value(self, value: float) -> None:
        self._last_known_quota = int(value)
        data = self.coordinator.data
        current_mode = data.charge_mode.mode if data else ChargeMode.HYBRID

        await self.hass.async_add_executor_job(self._set_quota, current_mode, int(value))
        await self.coordinator.async_request_refresh()

    def _set_quota(self, mode: str, quota: int) -> None:
        self.coordinator.client.set_charge_mode(
            mode,
            min_pv_power_quota=quota,
            min_charging_power_quota=(0 if mode == ChargeMode.HYBRID else None),
        )

