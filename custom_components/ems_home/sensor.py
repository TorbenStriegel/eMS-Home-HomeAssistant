"""Sensor platform for eMS Home."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import EMSHomeCoordinator, EMSHomeData


@dataclass
class EMSSensorEntityDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with a value extractor."""
    value_fn: Callable[[EMSHomeData], float | int | str | None] = lambda _: None


SENSOR_DESCRIPTIONS: tuple[EMSSensorEntityDescription, ...] = (
    # ── e-mobility state ─────────────────────────────────────────────────────
    EMSSensorEntityDescription(
        key="ev_charging_power_total",
        name="EV Charging Power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:ev-station",
        value_fn=lambda d: round(d.emobility_state.ev_charging_power.total / 1_000_000, 3),
    ),
    EMSSensorEntityDescription(
        key="ev_charging_power_l1",
        name="EV Charging Power L1",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.emobility_state.ev_charging_power.l1 / 1_000_000, 3),
    ),
    EMSSensorEntityDescription(
        key="ev_charging_power_l2",
        name="EV Charging Power L2",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.emobility_state.ev_charging_power.l2 / 1_000_000, 3),
    ),
    EMSSensorEntityDescription(
        key="ev_charging_power_l3",
        name="EV Charging Power L3",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.emobility_state.ev_charging_power.l3 / 1_000_000, 3),
    ),
    EMSSensorEntityDescription(
        key="curtailment_setpoint",
        name="Curtailment Setpoint",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower-off",
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.emobility_state.curtailment_setpoint.total / 1_000_000, 3),
    ),
    # ── smart meter (WebSocket, real-time) ───────────────────────────────────
    EMSSensorEntityDescription(
        key="grid_power_total",
        name="Grid Power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower",
        value_fn=lambda d: round(d.smart_meter.power_total / 1000, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_power_l1",
        name="Grid Power L1",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.smart_meter.power_l1 / 1000, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_power_l2",
        name="Grid Power L2",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.smart_meter.power_l2 / 1000, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_power_l3",
        name="Grid Power L3",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.smart_meter.power_l3 / 1000, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_apparent_power_total",
        name="Grid Apparent Power",
        native_unit_of_measurement="kVA",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower",
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.smart_meter.power_apparent / 1000, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_voltage_l1",
        name="Grid Voltage L1",
        native_unit_of_measurement="V",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.smart_meter.voltage_l1, 2) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_voltage_l2",
        name="Grid Voltage L2",
        native_unit_of_measurement="V",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.smart_meter.voltage_l2, 2) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_voltage_l3",
        name="Grid Voltage L3",
        native_unit_of_measurement="V",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.smart_meter.voltage_l3, 2) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_current_l1",
        name="Grid Current L1",
        native_unit_of_measurement="A",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.smart_meter.current_l1, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_current_l2",
        name="Grid Current L2",
        native_unit_of_measurement="A",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.smart_meter.current_l2, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_current_l3",
        name="Grid Current L3",
        native_unit_of_measurement="A",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.smart_meter.current_l3, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_frequency",
        name="Grid Frequency",
        native_unit_of_measurement="Hz",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.smart_meter.frequency, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_energy_import_total",
        name="Grid Energy Import",
        native_unit_of_measurement="kWh",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:meter-electric",
        value_fn=lambda d: round(d.smart_meter.energy_total, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_energy_export_total",
        name="Grid Energy Export",
        native_unit_of_measurement="kWh",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:meter-electric-outline",
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.smart_meter.energy_export, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_power_export",
        name="Grid Power Export",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower-export",
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.smart_meter.power_export / 1000, 3) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_reactive_power",
        name="Grid Reactive Power",
        native_unit_of_measurement="var",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash-triangle-outline",
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.smart_meter.reactive_power, 1) if d.smart_meter else None,
    ),
    EMSSensorEntityDescription(
        key="grid_power_factor",
        name="Grid Power Factor",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:angle-acute",
        entity_registry_enabled_default=False,
        value_fn=lambda d: round(d.smart_meter.power_factor, 3) if d.smart_meter else None,
    ),
    # ── EV charging state ────────────────────────────────────────────────────
    EMSSensorEntityDescription(
        key="ev_charging_state",
        name="EV Charging State",
        icon="mdi:ev-station",
        value_fn=lambda d: (
            "locked"   if d.charge_mode.mode == "lock" else
            "charging" if d.emobility_state.ev_charging_power.total > 0 else
            "idle"
        ),
    ),
    # ── charge mode ──────────────────────────────────────────────────────────
    EMSSensorEntityDescription(
        key="charge_mode",
        name="Charge Mode",
        icon="mdi:car-electric",
        value_fn=lambda d: d.charge_mode.mode,
    ),
    # ── device health ─────────────────────────────────────────────────────────
    EMSSensorEntityDescription(
        key="device_status",
        name="Device Status",
        icon="mdi:information-outline",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.device_status.status,
    ),
    EMSSensorEntityDescription(
        key="cpu_load",
        name="CPU Load",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cpu-64-bit",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.device_status.cpu_load,
    ),
    EMSSensorEntityDescription(
        key="cpu_temp",
        name="CPU Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.device_status.cpu_temp,
    ),
    EMSSensorEntityDescription(
        key="ram_used_pct",
        name="RAM Usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.device_status.ram_used_pct,
    ),
    EMSSensorEntityDescription(
        key="flash_data_used_pct",
        name="Flash Data Usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:harddisk",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.device_status.flash_data_used_pct,
    ),
    # ── EVSE / Wallbox (WebSocket, real-time) ─────────────────────────────
    EMSSensorEntityDescription(
        key="evse_status",
        name="Wallbox Status",
        icon="mdi:ev-plug-type2",
        value_fn=lambda d: d.evse.status_text if d.evse else None,
    ),
    EMSSensorEntityDescription(
        key="evse_session_duration",
        name="Charging Session Duration",
        native_unit_of_measurement="min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
        value_fn=lambda d: d.evse.session_duration_min if d.evse else None,
    ),
    EMSSensorEntityDescription(
        key="evse_serial",
        name="Wallbox Serial",
        icon="mdi:identifier",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.evse.evse_serial if d.evse else None,
    ),
    EMSSensorEntityDescription(
        key="evse_hw_imax",
        name="Wallbox Max Current",
        native_unit_of_measurement="A",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.evse.hw_imax_amps if d.evse else None,
    ),
    EMSSensorEntityDescription(
        key="evse_error_code",
        name="Wallbox Error Code",
        icon="mdi:alert-circle-outline",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.evse.evse_error_code if d.evse and d.evse.evse_error_code else "none",
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
            configuration_url=f"http://{entry.data['host']}:{entry.data.get('port', 80)}",
            model_id="ems-home",
        )

    @property
    def native_value(self) -> float | int | str | None:
        data = self.coordinator.data
        if data is None:
            return None
        try:
            data.smart_meter = self.coordinator.get_fresh_smart_meter()
            data.evse = self.coordinator.get_fresh_evse()
            return self.entity_description.value_fn(data)
        except Exception:
            return None
