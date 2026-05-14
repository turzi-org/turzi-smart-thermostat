"""Data update coordinator for Turzi Smart Thermostat.

Glues sensors, weather, schedule, comfort model, and strategy engine
into a unified data object consumed by climate and sensor entities.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.components.climate import HVACAction
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .comfort import ComfortResult, calculate_comfort
from .const import (
    DEFAULT_TARGET_TEMP,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SCHEDULE_MODE_OFFSETS,
    ScheduleMode,
)
from .scheduler import EnergyTierScheduler, TurziScheduler
from .store import TurziStore
from .strategy import SpaceStrategy, StrategyEngine

_LOGGER = logging.getLogger(__name__)


@dataclass
class SpaceData:
    """Aggregated data for a single space/zone."""

    name: str
    hvac_type: str
    current_temp: float | None = None
    current_humidity: float | None = None
    target_temp: float | None = None
    base_target_temp: float = DEFAULT_TARGET_TEMP
    schedule_mode: str = ScheduleMode.COMFORT
    hvac_action: HVACAction = HVACAction.IDLE
    comfort: ComfortResult | None = None
    strategy: SpaceStrategy | None = None
    energy_tier: str | None = None
    manual_override_temp: float | None = None
    manual_override_mode: str | None = None
    boost_until: float | None = None  # timestamp


@dataclass
class TurziData:
    """Complete data snapshot from a coordinator update cycle."""

    spaces: dict[str, SpaceData] = field(default_factory=dict)
    outdoor_temp: float | None = None
    outdoor_humidity: float | None = None
    wind_speed: float | None = None
    weather_condition: str | None = None
    forecast_hourly: list[dict] = field(default_factory=list)
    forecast_daily: list[dict] = field(default_factory=list)


class TurziCoordinator(DataUpdateCoordinator[TurziData]):
    """Central coordinator that runs the control loop every 60 seconds."""

    def __init__(
        self,
        hass: HomeAssistant,
        store: TurziStore,
        weather_entity_id: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
        )
        self.store = store
        self.weather_entity_id = weather_entity_id

        self.scheduler = TurziScheduler()
        self.energy_scheduler = EnergyTierScheduler()
        self.strategy_engine = StrategyEngine()

        # Manual overrides (set via climate entity, cleared on next schedule transition)
        self._manual_overrides: dict[str, dict[str, Any]] = {}

    def set_manual_override(self, space_id: str, temp: float | None = None, mode: str | None = None) -> None:
        """Set a manual temperature or mode override for a space."""
        self._manual_overrides[space_id] = {"temp": temp, "mode": mode}

    def clear_manual_override(self, space_id: str) -> None:
        """Clear manual override for a space."""
        self._manual_overrides.pop(space_id, None)

    async def _async_update_data(self) -> TurziData:
        """Run the full control loop: read → compute → decide."""
        try:
            # Reload config from store
            self.scheduler.load_schedules(self.store.schedule)
            self.energy_scheduler.load(self.store.energy_rates)
            self.strategy_engine.load_learned_thermal(self.store.learned_thermal)
            settings = self.store.settings

            # Read weather
            outdoor_temp, outdoor_humidity, wind_speed, weather_condition = self._read_weather()
            forecast_hourly = await self._get_forecast("hourly")
            forecast_daily = await self._get_forecast("daily")

            # Extract forecast temps for strategy engine
            forecast_temps = [
                f.get("temperature", 0) for f in forecast_hourly
                if f.get("temperature") is not None
            ]

            data = TurziData(
                outdoor_temp=outdoor_temp,
                outdoor_humidity=outdoor_humidity,
                wind_speed=wind_speed,
                weather_condition=weather_condition,
                forecast_hourly=forecast_hourly,
                forecast_daily=forecast_daily,
            )

            # Process each space
            for space_id, space_config in self.store.spaces.items():
                space_data = await self._process_space(
                    space_id, space_config, outdoor_temp, outdoor_humidity,
                    wind_speed, forecast_temps, settings,
                )
                data.spaces[space_id] = space_data

                # Execute control action
                await self._execute_action(space_id, space_config, space_data, settings)

            return data

        except Exception as err:
            _LOGGER.error("Error updating Turzi thermostat: %s", err)
            raise UpdateFailed(f"Update failed: {err}") from err

    async def _process_space(
        self,
        space_id: str,
        config: dict,
        outdoor_temp: float | None,
        outdoor_humidity: float | None,
        wind_speed: float | None,
        forecast_temps: list[float],
        settings: dict,
    ) -> SpaceData:
        """Process a single space through the full pipeline."""
        name = config.get("name", space_id)
        hvac_type = config.get("hvac_type", "radiator")
        base_target = config.get("target_temp", DEFAULT_TARGET_TEMP)

        # Read sensors
        current_temp = self._read_sensor(config.get("temp_sensor"))
        current_humidity = self._read_sensor(config.get("humidity_sensor"))

        # Schedule
        schedule_result = self.scheduler.resolve(space_id)
        schedule_mode = schedule_result.mode

        # Check manual override
        override = self._manual_overrides.get(space_id, {})
        if override.get("temp") is not None:
            effective_target = override["temp"]
        elif override.get("mode") is not None:
            schedule_mode = override["mode"]
            offset = SCHEDULE_MODE_OFFSETS.get(schedule_mode, 0.0)
            effective_target = base_target + offset if offset is not None else None
        else:
            effective_target = schedule_result.get_effective_target(base_target)

        # Comfort model
        comfort = calculate_comfort(
            indoor_temp=current_temp,
            indoor_humidity=current_humidity,
            outdoor_temp=outdoor_temp,
            wind_speed=wind_speed,
            hvac_type=hvac_type,
            humidity_compensation=settings.get("humidity_compensation", True),
            wind_compensation=settings.get("wind_compensation", True),
        )

        # Apply comfort adjustments to target
        if effective_target is not None:
            effective_target = round(effective_target + comfort.total_adjustment, 1)

        # Energy tier
        energy_tier = self.energy_scheduler.resolve()
        energy_is_high = self.energy_scheduler.is_high_rate(energy_tier)
        energy_is_low = self.energy_scheduler.is_low_rate(energy_tier)
        next_tier_change, _ = self.energy_scheduler.get_next_tier_change()

        # Resolve seasonal mode
        seasonal_mode = settings.get("seasonal_mode", "auto")

        # Strategy
        strategy = self.strategy_engine.evaluate(
            space_id=space_id,
            hvac_type=hvac_type,
            current_temp=current_temp,
            target_temp=effective_target,
            schedule_mode=schedule_mode,
            next_transition=schedule_result.next_transition,
            next_mode=schedule_result.next_mode,
            outdoor_temp=outdoor_temp,
            forecast_temps=forecast_temps,
            energy_tier=energy_tier,
            energy_is_high=energy_is_high,
            energy_is_low=energy_is_low,
            next_tier_change=next_tier_change,
            preconditioning_enabled=settings.get("preconditioning_enabled", True),
            has_auxiliary=bool(config.get("auxiliary_heating")),
            seasonal_mode=seasonal_mode,
        )

        # Determine HVAC action from strategy
        # Downgrade cooling to idle if this zone has no cooling output
        has_cooling = bool(config.get("cooling_output"))
        action_map = {
            "heat": HVACAction.HEATING,
            "pre_heat": HVACAction.HEATING,
            "cool": HVACAction.COOLING if has_cooling else HVACAction.IDLE,
            "pre_cool": HVACAction.COOLING if has_cooling else HVACAction.IDLE,
            "idle": HVACAction.IDLE,
            "off": HVACAction.OFF,
        }
        hvac_action = action_map.get(strategy.action, HVACAction.IDLE)

        return SpaceData(
            name=name,
            hvac_type=hvac_type,
            current_temp=current_temp,
            current_humidity=current_humidity,
            target_temp=effective_target,
            base_target_temp=base_target,
            schedule_mode=schedule_mode,
            hvac_action=hvac_action,
            comfort=comfort,
            strategy=strategy,
            energy_tier=energy_tier,
        )

    def _read_sensor(self, entity_id: str | None) -> float | None:
        """Read a numeric value from a sensor entity."""
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    def _read_sensor_state(self, entity_id: str | None) -> str | None:
        """Read the raw state string from any entity."""
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        return state.state

    def _read_weather(self) -> tuple[float | None, float | None, float | None, str | None]:
        """Read current weather from the weather entity."""
        state = self.hass.states.get(self.weather_entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return None, None, None, None
        attrs = state.attributes
        temp = attrs.get("temperature")
        humidity = attrs.get("humidity")
        wind = attrs.get("wind_speed")
        condition = state.state
        return (
            float(temp) if temp is not None else None,
            float(humidity) if humidity is not None else None,
            float(wind) if wind is not None else None,
            condition,
        )

    async def _get_forecast(self, forecast_type: str) -> list[dict]:
        """Get weather forecast via the weather.get_forecasts service."""
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": self.weather_entity_id, "type": forecast_type},
                blocking=True,
                return_response=True,
            )
            if response and self.weather_entity_id in response:
                return response[self.weather_entity_id].get("forecast", [])
        except Exception as err:
            _LOGGER.debug("Could not get %s forecast: %s", forecast_type, err)
        return []

    async def _execute_action(self, space_id: str, config: dict, space_data: SpaceData, settings: dict) -> None:
        """Execute the strategy's decision on the underlying entity."""
        strategy = space_data.strategy
        if not strategy:
            return

        # Control seasonal HVAC switch if configured
        seasonal_switch = settings.get("seasonal_switch_entity")
        seasonal_mode = settings.get("seasonal_mode", "auto")
        if seasonal_switch and seasonal_mode in ("winter", "summer"):
            switch_state = self._read_sensor_state(seasonal_switch)
            if seasonal_mode == "winter" and switch_state == "off":
                await self._control_output(seasonal_switch, True)
            elif seasonal_mode == "summer" and switch_state == "on":
                await self._control_output(seasonal_switch, False)

        heating_output = config.get("heating_output")
        cooling_output = config.get("cooling_output")
        auxiliary_heating = config.get("auxiliary_heating")

        if strategy.action in ("heat", "pre_heat"):
            await self._control_output(heating_output, True, strategy.target_temp)
            # Engage auxiliary heating if strategy recommends it
            if strategy.use_auxiliary and auxiliary_heating:
                await self._control_output(auxiliary_heating, True, strategy.target_temp)
            elif auxiliary_heating:
                await self._control_output(auxiliary_heating, False)
            if cooling_output:
                await self._control_output(cooling_output, False)
        elif strategy.action in ("cool", "pre_cool"):
            if cooling_output:
                await self._control_output(cooling_output, True, strategy.target_temp)
            if heating_output:
                await self._control_output(heating_output, False)
            if auxiliary_heating:
                await self._control_output(auxiliary_heating, False)
        elif strategy.action in ("idle", "off"):
            if heating_output:
                await self._control_output(heating_output, False)
            if cooling_output:
                await self._control_output(cooling_output, False)
            if auxiliary_heating:
                await self._control_output(auxiliary_heating, False)

    async def _control_output(self, entity_id: str | None, turn_on: bool, target_temp: float | None = None) -> None:
        """Control an output entity (switch or climate).

        Only sends commands when the state actually needs to change,
        to avoid spamming devices (e.g., IR-controlled A/C units beep
        on every command).
        """
        if not entity_id:
            return

        state = self.hass.states.get(entity_id)
        if state is None:
            _LOGGER.warning("Output entity %s not found", entity_id)
            return

        domain = entity_id.split(".")[0]
        current_state = state.state  # "on"/"off" for switches, hvac_mode for climate

        if domain == "switch":
            if turn_on and current_state != "on":
                await self.hass.services.async_call("switch", "turn_on", {"entity_id": entity_id})
            elif not turn_on and current_state != "off":
                await self.hass.services.async_call("switch", "turn_off", {"entity_id": entity_id})

        elif domain == "climate":
            if turn_on and target_temp is not None:
                current_temp_target = state.attributes.get("temperature")
                is_off = current_state == "off"
                temp_changed = current_temp_target != target_temp

                # Only send if turning on from off, or target temp changed
                if is_off or temp_changed:
                    await self.hass.services.async_call(
                        "climate", "set_temperature",
                        {"entity_id": entity_id, "temperature": target_temp},
                    )
            elif not turn_on and current_state != "off":
                await self.hass.services.async_call(
                    "climate", "set_hvac_mode",
                    {"entity_id": entity_id, "hvac_mode": "off"},
                )
