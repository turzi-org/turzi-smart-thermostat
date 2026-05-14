"""Diagnostic sensor entities for Turzi Smart Thermostat."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TurziCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from a config entry."""
    coordinator: TurziCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SensorEntity] = []

    known_ids: set[str] = set()
    for space_id, space_config in coordinator.store.spaces.items():
        name = space_config.get("name", space_id)
        entities.extend([
            TurziComfortScoreSensor(coordinator, entry, space_id, name),
            TurziEffectiveTargetSensor(coordinator, entry, space_id, name),
            TurziScheduleModeSensor(coordinator, entry, space_id, name),
            TurziEnergyTierSensor(coordinator, entry, space_id, name),
            TurziStrategySensor(coordinator, entry, space_id, name),
        ])
        known_ids.add(space_id)

    # Global sensors
    entities.append(TurziOutdoorFeelsLikeSensor(coordinator, entry))

    async_add_entities(entities)

    # Store callback for dynamic entity creation when zones are added via panel
    hass.data[DOMAIN][entry.entry_id]["sensor_add_entities"] = async_add_entities
    hass.data[DOMAIN][entry.entry_id]["sensor_known_ids"] = known_ids


class TurziBaseSensor(CoordinatorEntity[TurziCoordinator], SensorEntity):
    """Base class for Turzi sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TurziCoordinator, entry: ConfigEntry, space_id: str, space_name: str, sensor_key: str) -> None:
        super().__init__(coordinator)
        self._space_id = space_id
        self._attr_unique_id = f"{entry.entry_id}_{space_id}_{sensor_key}"

    @property
    def _space_data(self):
        if self.coordinator.data and self._space_id in self.coordinator.data.spaces:
            return self.coordinator.data.spaces[self._space_id]
        return None


class TurziComfortScoreSensor(TurziBaseSensor):
    """Comfort score sensor (0-100)."""

    _attr_icon = "mdi:emoticon-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, space_id, space_name):
        super().__init__(coordinator, entry, space_id, space_name, "comfort_score")
        self._attr_name = f"{space_name} Comfort Score"

    @property
    def native_value(self) -> float | None:
        data = self._space_data
        return data.comfort.score if data and data.comfort else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._space_data
        if data and data.comfort:
            return data.comfort.as_dict()
        return {}


class TurziEffectiveTargetSensor(TurziBaseSensor):
    """Effective target temperature after all adjustments."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, space_id, space_name):
        super().__init__(coordinator, entry, space_id, space_name, "effective_target")
        self._attr_name = f"{space_name} Effective Target"

    @property
    def native_value(self) -> float | None:
        data = self._space_data
        return data.target_temp if data else None


class TurziScheduleModeSensor(TurziBaseSensor):
    """Current schedule mode."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, entry, space_id, space_name):
        super().__init__(coordinator, entry, space_id, space_name, "schedule_mode")
        self._attr_name = f"{space_name} Schedule Mode"

    @property
    def native_value(self) -> str | None:
        data = self._space_data
        return data.schedule_mode.capitalize() if data else None


class TurziEnergyTierSensor(TurziBaseSensor):
    """Current energy rate tier."""

    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator, entry, space_id, space_name):
        super().__init__(coordinator, entry, space_id, space_name, "energy_tier")
        self._attr_name = f"{space_name} Energy Tier"

    @property
    def native_value(self) -> str | None:
        data = self._space_data
        return data.energy_tier if data else None


class TurziStrategySensor(TurziBaseSensor):
    """Human-readable strategy explanation."""

    _attr_icon = "mdi:head-lightbulb-outline"

    def __init__(self, coordinator, entry, space_id, space_name):
        super().__init__(coordinator, entry, space_id, space_name, "strategy")
        self._attr_name = f"{space_name} Strategy"

    @property
    def native_value(self) -> str | None:
        data = self._space_data
        return data.strategy.reason if data and data.strategy else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._space_data
        if data and data.strategy:
            return data.strategy.as_dict()
        return {}


class TurziOutdoorFeelsLikeSensor(CoordinatorEntity[TurziCoordinator], SensorEntity):
    """Computed outdoor feels-like temperature."""

    _attr_has_entity_name = True
    _attr_name = "Outdoor Feels Like"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer-lines"

    def __init__(self, coordinator: TurziCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_outdoor_feels_like"

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if not data or data.outdoor_temp is None:
            return None
        temp = data.outdoor_temp
        wind = data.wind_speed
        humidity = data.outdoor_humidity

        # Wind chill (for cold conditions)
        if wind and temp < 10.0 and wind > 4.8:
            # Environment Canada wind chill formula
            feels = 13.12 + 0.6215 * temp - 11.37 * (wind ** 0.16) + 0.3965 * temp * (wind ** 0.16)
            return round(feels, 1)

        # Heat index (for warm/humid conditions)
        if humidity and temp > 27.0:
            # Simplified Steadman formula
            hi = temp + 0.5555 * ((humidity / 100.0) * 6.105 * (2.7183 ** ((17.27 * temp) / (237.7 + temp))) - 10.0)
            return round(hi, 1)

        return round(temp, 1)
