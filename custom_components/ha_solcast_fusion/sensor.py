from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


@dataclass(frozen=True, kw_only=True)
class SolcastFusionSensorDescription(SensorEntityDescription):
    data_key: str = ""


SENSOR_DESCRIPTIONS: tuple[SolcastFusionSensorDescription, ...] = (
    SolcastFusionSensorDescription(
        key="energy_production_today",
        translation_key="energy_production_today",
        data_key="today_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SolcastFusionSensorDescription(
        key="energy_production_today_remaining",
        translation_key="energy_production_today_remaining",
        data_key="today_remaining_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SolcastFusionSensorDescription(
        key="energy_production_tomorrow",
        translation_key="energy_production_tomorrow",
        data_key="tomorrow_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SolcastFusionSensorDescription(
        key="power_production_now",
        translation_key="power_production_now",
        data_key="power_now",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SolcastFusionSensorDescription(
        key="power_highest_peak_time_today",
        translation_key="power_highest_peak_time_today",
        data_key="peak_time_today",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SolcastFusionSensorDescription(
        key="power_highest_peak_time_tomorrow",
        translation_key="power_highest_peak_time_tomorrow",
        data_key="peak_time_tomorrow",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SolcastFusionSensorDescription(
        key="energy_current_hour",
        translation_key="energy_current_hour",
        data_key="current_hour_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SolcastFusionSensorDescription(
        key="energy_next_hour",
        translation_key="energy_next_hour",
        data_key="next_hour_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Diagnostics
    SolcastFusionSensorDescription(
        key="solcast_calls_remaining",
        translation_key="solcast_calls_remaining",
        data_key="solcast_calls_remaining",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SolcastFusionSensorDescription(
        key="last_solcast_update",
        translation_key="last_solcast_update",
        data_key="last_solcast_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SolcastFusionSensorDescription(
        key="correction_factor",
        translation_key="correction_factor",
        data_key="correction_factor",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SolcastFusionSensorDescription(
        key="source",
        translation_key="source",
        data_key="source",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SolcastFusionSensorDescription(
        key="pct_periods_clamped",
        translation_key="pct_periods_clamped",
        data_key="pct_periods_clamped",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


class SolcastFusionSensor(CoordinatorEntity, SensorEntity):
    """Generic sensor reading from OpenMeteoCoordinator data."""

    _unrecorded_attributes: frozenset[str] = frozenset()

    def __init__(
        self,
        coordinator,
        description: SolcastFusionSensorDescription,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"

    @property
    def available(self) -> bool:
        return bool(self.coordinator.data)

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data
        if not data:
            return None
        return data.get(self.entity_description.data_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return None


class _WattsAttributeSensor(SolcastFusionSensor):
    """Sensor that carries the full watts curve as an unrecorded extra attribute."""

    _unrecorded_attributes: frozenset[str] = frozenset({"watts"})

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        if not data:
            return None
        watts = data.get("watts")
        if watts is None:
            return None
        return {"watts": watts}


EnergyProductionTodaySensor = _WattsAttributeSensor


def build_sensors(coordinator, entry_id: str) -> list[SolcastFusionSensor]:
    """Create all sensor entities."""
    sensors: list[SolcastFusionSensor] = []
    for desc in SENSOR_DESCRIPTIONS:
        if desc.key == "energy_production_today":
            sensors.append(_WattsAttributeSensor(coordinator, desc, entry_id))
        else:
            sensors.append(SolcastFusionSensor(coordinator, desc, entry_id))
    return sensors


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up SolcastFusion sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(build_sensors(coordinator, entry.entry_id))
