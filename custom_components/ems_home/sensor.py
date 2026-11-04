"""Sensor platform for eMS Home."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import EMSHomeCoordinator, EMSHomeData

Stream = Literal["smart_meter", "evse"]


@dataclass(kw_only=True)
class EMSSensorEntityDescription(SensorEntityDescription):
    """Sensor description with a value extractor and stream dependency."""

    value_fn: Callable[[EMSHomeData], float | int | str | None]
    requires: Stream | None = None


SENSOR_DESCRIPTIONS: tuple[EMSSensorEntityDescription, ...] = (
    # ── EV charging (HTTP poll) ───────────────────────────────────────────
    EMSSensorEntityDescription(
        key="ev_charging_power_total",
        translation_key="ev_charging_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:ev-station",
        value_fn=lambda d: round(d.emobility_state.ev_charging_power.total / 1_000_000, 3),
    ),
    EMSSensorEntityDescription(
        key="ev_charging_power_l1",
        translation_key="ev_charging_power_l1",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:lightning-bolt",
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.emobility_state.ev_charging_power.l1 / 1_000_000, 3),
    ),
    EMSSensorEntityDescription(
        key="ev_charging_power_l2",
        translation_key="ev_charging_power_l2",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:lightning-bolt",
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.emobility_state.ev_charging_power.l2 / 1_000_000, 3),
    ),
    EMSSensorEntityDescription(
        key="ev_charging_power_l3",
        translation_key="ev_charging_power_l3",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:lightning-bolt",
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.emobility_state.ev_charging_power.l3 / 1_000_000, 3),
    ),
    EMSSensorEntityDescription(
        key="curtailment_setpoint",
        translation_key="curtailment_setpoint",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:transmission-tower-off",
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.emobility_state.curtailment_setpoint.total / 1_000_000, 3),
    ),
    EMSSensorEntityDescription(
        key="ev_charging_state",
        translation_key="ev_charging_state",
        device_class=SensorDeviceClass.ENUM,
        options=["idle", "charging", "locked"],
        icon="mdi:ev-station",
        value_fn=lambda d: d.charge_state,
    ),
    EMSSensorEntityDescription(
        key="charge_mode",
        translation_key="charge_mode",
        device_class=SensorDeviceClass.ENUM,
        options=["lock", "grid", "pv", "hybrid", "unknown"],
        icon="mdi:car-electric",
        value_fn=lambda d: d.charge_mode.mode,
    ),
    # ── smart meter (WebSocket) ───────────────────────────────────────────
    EMSSensorEntityDescription(
        key="grid_power_total",
        translation_key="grid_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        icon="mdi:transmission-tower",
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.power_total / 1000, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_power_l1",
        translation_key="grid_power_l1",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        icon="mdi:lightning-bolt",
        entity_registry_enabled_default=False,
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.power_l1 / 1000, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_power_l2",
        translation_key="grid_power_l2",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        icon="mdi:lightning-bolt",
        entity_registry_enabled_default=False,
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.power_l2 / 1000, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_power_l3",
        translation_key="grid_power_l3",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        icon="mdi:lightning-bolt",
        entity_registry_enabled_default=False,
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.power_l3 / 1000, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_power_export",
        translation_key="grid_power_export",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        icon="mdi:transmission-tower-export",
        entity_registry_enabled_default=False,
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.power_export / 1000, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_apparent_power_total",
        translation_key="grid_apparent_power",
        native_unit_of_measurement="kVA",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        icon="mdi:transmission-tower",
        entity_registry_enabled_default=False,
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.power_apparent / 1000, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_voltage_l1",
        translation_key="grid_voltage_l1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.voltage_l1, 2) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_voltage_l2",
        translation_key="grid_voltage_l2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.voltage_l2, 2) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_voltage_l3",
        translation_key="grid_voltage_l3",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.voltage_l3, 2) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_current_l1",
        translation_key="grid_current_l1",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.current_l1, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_current_l2",
        translation_key="grid_current_l2",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.current_l2, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_current_l3",
        translation_key="grid_current_l3",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.current_l3, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_frequency",
        translation_key="grid_frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        entity_registry_enabled_default=False,
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.frequency, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_energy_import_total",
        translation_key="grid_energy_import",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        icon="mdi:meter-electric",
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.energy_total, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_energy_export_total",
        translation_key="grid_energy_export",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        icon="mdi:meter-electric-outline",
        entity_registry_enabled_default=False,
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.energy_export, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_reactive_power",
        translation_key="grid_reactive_power",
        native_unit_of_measurement="var",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:flash-triangle-outline",
        entity_registry_enabled_default=False,
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.reactive_power, 1) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_power_factor",
        translation_key="grid_power_factor",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        icon="mdi:angle-acute",
        entity_registry_enabled_default=False,
        requires="smart_meter",
        value_fn=lambda d: round(d.smart_meter.power_factor, 3) if d.smart_meter else None,
    ),
    # ── wallbox (WebSocket) ───────────────────────────────────────────────
    EMSSensorEntityDescription(
        key="evse_status",
        translation_key="evse_status",
        icon="mdi:ev-plug-type2",
        requires="evse",
        value_fn=lambda d: d.evse.status_text if d.evse else None,
    ),
    EMSSensorEntityDescription(
        key="evse_session_duration",
        translation_key="evse_session_duration",
        native_unit_of_measurement="min",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:timer-outline",
        requires="evse",
        value_fn=lambda d: d.evse.session_duration_min if d.evse else None,
    ),
    EMSSensorEntityDescription(
        key="evse_session_energy",
        translation_key="evse_session_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        icon="mdi:battery-charging",
        requires="evse",
        value_fn=lambda d: d.evse.session_energy_kwh if d.evse else None,
    ),
    EMSSensorEntityDescription(
        key="evse_energy_total",
        translation_key="evse_energy_total",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        icon="mdi:counter",
        entity_registry_enabled_default=False,
        requires="evse",
        value_fn=lambda d: d.evse.energy_total_kwh if d.evse else None,
    ),
    EMSSensorEntityDescription(
        key="evse_hw_imax",
        translation_key="evse_hw_imax",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac",
        entity_registry_enabled_default=False,
        requires="evse",
        value_fn=lambda d: d.evse.hw_imax_amps if d.evse else None,
    ),
    EMSSensorEntityDescription(
        key="evse_max_current_setting",
        translation_key="evse_max_current_setting",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:tune-variant",
        entity_registry_enabled_default=False,
        requires="evse",
        value_fn=lambda d: round(d.evse.ev_imax_default / 1000, 1) if d.evse else None,
    ),
    EMSSensorEntityDescription(
        key="evse_serial",
        translation_key="evse_serial",
        icon="mdi:identifier",
        entity_registry_enabled_default=False,
        requires="evse",
        value_fn=lambda d: d.evse.evse_serial or None if d.evse else None,
    ),
    EMSSensorEntityDescription(
        key="evse_error_code",
        translation_key="evse_error_code",
        icon="mdi:alert-circle-outline",
        entity_registry_enabled_default=False,
        requires="evse",
        value_fn=lambda d: (d.evse.evse_error_code or "none") if d.evse else None,
    ),
    # ── device health (diagnostic) ────────────────────────────────────────
    EMSSensorEntityDescription(
        key="device_status",
        translation_key="device_status",
        icon="mdi:information-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.device_status.status,
    ),
    EMSSensorEntityDescription(
        key="cpu_load",
        translation_key="cpu_load",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cpu-64-bit",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.device_status.cpu_load,
    ),
    EMSSensorEntityDescription(
        key="cpu_temp",
        translation_key="cpu_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.device_status.cpu_temp,
    ),
    EMSSensorEntityDescription(
        key="ram_used_pct",
        translation_key="ram_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.device_status.ram_used_pct,
    ),
    EMSSensorEntityDescription(
        key="flash_data_used_pct",
        translation_key="flash_data_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:harddisk",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.device_status.flash_data_used_pct,
    ),
    EMSSensorEntityDescription(
        key="smart_meter_frame_age",
        translation_key="smart_meter_frame_age",
        native_unit_of_measurement="s",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-sand",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        requires="smart_meter",
        value_fn=lambda d: None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up eMS Home sensors."""
    coordinator: EMSHomeCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities(
        EMSHomeSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class EMSHomeSensor(CoordinatorEntity[EMSHomeCoordinator], SensorEntity):
    """A single sensor entity backed by the coordinator."""

    entity_description: EMSSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EMSHomeCoordinator,
        entry: ConfigEntry,
        description: EMSSensorEntityDescription,
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
            configuration_url=(
                f"{'https' if coordinator.client.uses_https else 'http'}://"
                f"{coordinator.client.host}:{coordinator.client.port}"
            ),
        )

    @property
    def available(self) -> bool:
        """Unavailable when the required live stream never delivered data.

        This turns the previously confusing ``unknown`` (stream silently dead)
        into a clear ``unavailable``.
        """
        if not super().available:
            return False
        stream = self.entity_description.requires
        if stream == "smart_meter":
            stats = self.coordinator.smart_meter_ws
            return bool(stats and stats.stats.frames > 0)
        if stream == "evse":
            stats = self.coordinator.evse_ws
            return bool(stats and stats.stats.frames > 0)
        return True

    @property
    def native_value(self) -> float | int | str | None:
        # Age of the last smart meter frame is a diagnostic, not device data.
        if self.entity_description.key == "smart_meter_frame_age":
            stream = self.coordinator.smart_meter_ws
            return stream.stats.seconds_since_frame if stream else None

        data = self.coordinator.data
        if data is None:
            return None
        try:
            return self.entity_description.value_fn(data)
        except (AttributeError, TypeError, ZeroDivisionError):
            return None
