"""Climate entity for Turzi Smart Thermostat — one per zone."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_TARGET_TEMP,
    DOMAIN,
    TEMP_STEP,
    BOOST_DURATION_MINUTES,
    HvacSystemType,
    ScheduleMode,
)
from .coordinator import TurziCoordinator, TurziData

_LOGGER = logging.getLogger(__name__)

PRESET_MODES = [
    ScheduleMode.COMFORT,
    ScheduleMode.ECO,
    ScheduleMode.SLEEP,
    ScheduleMode.AWAY,
    ScheduleMode.BOOST,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate entities from a config entry."""
    coordinator: TurziCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = []
    for space_id, space_config in coordinator.store.spaces.items():
        entities.append(
            TurziClimateEntity(coordinator, entry, space_id, space_config)
        )

    async_add_entities(entities)


class TurziClimateEntity(CoordinatorEntity[TurziCoordinator], ClimateEntity):
    """A smart thermostat entity for a single zone/space."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = DEFAULT_MIN_TEMP
    _attr_max_temp = DEFAULT_MAX_TEMP
    _attr_target_temperature_step = TEMP_STEP
    _attr_preset_modes = PRESET_MODES
    _enable_turn_on_off_backwards_compat = False

    def __init__(
        self,
        coordinator: TurziCoordinator,
        entry: ConfigEntry,
        space_id: str,
        space_config: dict[str, Any],
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._space_id = space_id
        self._space_config = space_config
        self._attr_unique_id = f"{entry.entry_id}_{space_id}"
        self._attr_name = space_config.get("name", space_id)
        self._current_hvac_mode: HVACMode = HVACMode.AUTO

        # Determine supported features based on HVAC type
        hvac_type = space_config.get("hvac_type", "radiator")
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.PRESET_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        if hvac_type in (HvacSystemType.FAN_COIL, HvacSystemType.SPLIT_AC):
            features |= ClimateEntityFeature.FAN_MODE
        self._attr_supported_features = features

        # Determine available HVAC modes based on outputs
        modes = [HVACMode.OFF, HVACMode.AUTO]
        if space_config.get("heating_output"):
            modes.append(HVACMode.HEAT)
        if space_config.get("cooling_output"):
            modes.append(HVACMode.COOL)
        if space_config.get("heating_output") and space_config.get("cooling_output"):
            modes.append(HVACMode.HEAT_COOL)
        self._attr_hvac_modes = modes

        # Fan modes for fan-coil / split A/C
        if hvac_type in (HvacSystemType.FAN_COIL, HvacSystemType.SPLIT_AC):
            self._attr_fan_modes = ["auto", "low", "medium", "high"]
            self._attr_fan_mode = "auto"

    @property
    def _space_data(self):
        """Get current space data from coordinator."""
        if self.coordinator.data and self._space_id in self.coordinator.data.spaces:
            return self.coordinator.data.spaces[self._space_id]
        return None

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        data = self._space_data
        return data.current_temp if data else None

    @property
    def current_humidity(self) -> float | None:
        """Return the current humidity."""
        data = self._space_data
        return data.current_humidity if data else None

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        data = self._space_data
        return data.target_temp if data else DEFAULT_TARGET_TEMP

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        return self._current_hvac_mode

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current running action."""
        data = self._space_data
        return data.hvac_action if data else HVACAction.OFF

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        data = self._space_data
        if data:
            mode = data.schedule_mode
            if mode in PRESET_MODES:
                return mode
        return ScheduleMode.COMFORT

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        data = self._space_data
        attrs: dict[str, Any] = {
            "space_id": self._space_id,
            "hvac_type": self._space_config.get("hvac_type", "unknown"),
        }
        if data:
            attrs["base_target_temp"] = data.base_target_temp
            attrs["schedule_mode"] = data.schedule_mode
            attrs["energy_tier"] = data.energy_tier
            if data.comfort:
                attrs["comfort_score"] = data.comfort.score
                attrs["comfort_reason"] = data.comfort.reason
            if data.strategy:
                attrs["strategy_action"] = data.strategy.action
                attrs["strategy_reason"] = data.strategy.reason
                attrs["strategy_confidence"] = data.strategy.confidence
        return attrs

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        self._current_hvac_mode = hvac_mode
        if hvac_mode == HVACMode.OFF:
            self.coordinator.set_manual_override(self._space_id, mode=ScheduleMode.OFF)
        elif hvac_mode == HVACMode.AUTO:
            self.coordinator.clear_manual_override(self._space_id)
        elif hvac_mode in (HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL):
            # Manual mode — keep current target, clear schedule override
            self.coordinator.set_manual_override(
                self._space_id,
                temp=self.target_temperature or DEFAULT_TARGET_TEMP,
            )
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature (manual override)."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            self.coordinator.set_manual_override(self._space_id, temp=temp)
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if preset_mode == ScheduleMode.BOOST:
            # Boost mode: max heat for BOOST_DURATION_MINUTES, then revert
            self.coordinator.set_manual_override(
                self._space_id, temp=DEFAULT_MAX_TEMP, mode=ScheduleMode.BOOST
            )
        elif preset_mode in PRESET_MODES:
            self.coordinator.set_manual_override(self._space_id, mode=preset_mode)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # If we're in AUTO mode and the schedule mode changed, clear manual overrides
        if self._current_hvac_mode == HVACMode.AUTO:
            self.coordinator.clear_manual_override(self._space_id)
        self.async_write_ha_state()
