"""Predictive strategy engine for Turzi Smart Thermostat.

Makes heating/cooling decisions based on schedule transitions,
weather forecasts, energy tiers, and learned thermal behaviour.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from .const import (
    FORECAST_LOOKAHEAD_HOURS,
    FORECAST_SIGNIFICANT_DROP,
    THERMAL_DEFAULTS,
    ScheduleMode,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class SpaceStrategy:
    """Strategy decision for a single space."""

    action: Literal["heat", "cool", "idle", "off", "pre_heat", "pre_cool"]
    reason: str
    target_temp: float | None
    energy_note: str | None
    confidence: float  # 0.0–1.0

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "reason": self.reason,
            "target_temp": self.target_temp,
            "energy_note": self.energy_note,
            "confidence": self.confidence,
        }


class StrategyEngine:
    """Makes intelligent heating/cooling decisions per space."""

    def __init__(self) -> None:
        self._learned_thermal: dict[str, dict[str, Any]] = {}

    def load_learned_thermal(self, data: dict[str, Any]) -> None:
        """Load learned thermal data from store."""
        self._learned_thermal = data

    def get_thermal_params(self, space_id: str, hvac_type: str) -> dict[str, float]:
        """Get thermal parameters — learned if available, else defaults."""
        defaults = THERMAL_DEFAULTS.get(hvac_type, THERMAL_DEFAULTS["radiator"])
        learned = self._learned_thermal.get(space_id)
        if learned and learned.get("samples", 0) >= 7:
            return {
                "heat_up_rate": learned.get("heat_up_rate", defaults["heat_up_rate"]),
                "cool_down_rate": learned.get("cool_down_rate", defaults["cool_down_rate"]),
                "preconditioning_lead": defaults["preconditioning_lead"],
            }
        return defaults

    def evaluate(
        self,
        space_id: str,
        hvac_type: str,
        current_temp: float | None,
        target_temp: float | None,
        schedule_mode: str,
        next_transition: datetime | None,
        next_mode: str | None,
        outdoor_temp: float | None,
        forecast_temps: list[float] | None,
        energy_tier: str | None,
        energy_is_high: bool,
        energy_is_low: bool,
        next_tier_change: datetime | None,
        preconditioning_enabled: bool = True,
    ) -> SpaceStrategy:
        """Evaluate and return the best strategy for a space.

        Args:
            space_id: Space identifier
            hvac_type: HVAC system type
            current_temp: Current indoor temperature
            target_temp: Effective target temperature (after schedule + comfort adjustments)
            schedule_mode: Current schedule mode
            next_transition: When the next schedule mode change happens
            next_mode: What the next schedule mode will be
            outdoor_temp: Current outdoor temperature
            forecast_temps: List of forecast outdoor temps for next N hours
            energy_tier: Current energy tier name (or None)
            energy_is_high: Whether current tier is highest rate
            energy_is_low: Whether current tier is lowest rate
            next_tier_change: When the energy tier changes next
            preconditioning_enabled: Whether pre-conditioning is enabled
        """
        # System off
        if schedule_mode == ScheduleMode.OFF or target_temp is None:
            return SpaceStrategy(action="off", reason="Schedule mode: Off", target_temp=None, energy_note=None, confidence=1.0)

        # No sensor data
        if current_temp is None:
            return SpaceStrategy(action="idle", reason="No temperature data — waiting for sensor", target_temp=target_temp, energy_note=None, confidence=0.0)

        thermal = self.get_thermal_params(space_id, hvac_type)
        confidence = self._calculate_confidence(space_id)
        now = datetime.now()
        delta = target_temp - current_temp

        # --- Pre-conditioning logic ---
        if preconditioning_enabled and next_transition and next_mode:
            precondition = self._check_preconditioning(
                now, current_temp, target_temp, schedule_mode, next_transition, next_mode, thermal, hvac_type,
            )
            if precondition:
                energy_note = f"Current tier: {energy_tier}" if energy_tier else None
                return SpaceStrategy(action=precondition["action"], reason=precondition["reason"], target_temp=precondition["target"], energy_note=energy_note, confidence=confidence)

        # --- Energy tier optimization ---
        energy_strategy = self._check_energy_optimization(
            current_temp, target_temp, delta, energy_is_high, energy_is_low, energy_tier, next_tier_change, thermal, now,
        )
        if energy_strategy:
            return SpaceStrategy(**energy_strategy, confidence=confidence)

        # --- Weather anticipation ---
        weather_strategy = self._check_weather_anticipation(
            current_temp, target_temp, outdoor_temp, forecast_temps, delta, thermal,
        )
        if weather_strategy:
            energy_note = f"Current tier: {energy_tier}" if energy_tier else None
            return SpaceStrategy(**weather_strategy, energy_note=energy_note, confidence=confidence)

        # --- Standard thermostat logic ---
        hysteresis = 0.3  # °C deadband
        if delta > hysteresis:
            return SpaceStrategy(
                action="heat", reason=f"Heating: {current_temp:.1f}°C → {target_temp:.1f}°C",
                target_temp=target_temp,
                energy_note=f"Current tier: {energy_tier}" if energy_tier else None,
                confidence=confidence,
            )
        elif delta < -hysteresis:
            return SpaceStrategy(
                action="cool", reason=f"Cooling: {current_temp:.1f}°C → {target_temp:.1f}°C",
                target_temp=target_temp,
                energy_note=f"Current tier: {energy_tier}" if energy_tier else None,
                confidence=confidence,
            )
        else:
            return SpaceStrategy(
                action="idle", reason=f"At target ({current_temp:.1f}°C ≈ {target_temp:.1f}°C)",
                target_temp=target_temp,
                energy_note=f"Current tier: {energy_tier}" if energy_tier else None,
                confidence=confidence,
            )

    def _check_preconditioning(
        self, now: datetime, current_temp: float, target_temp: float, current_mode: str,
        next_transition: datetime, next_mode: str, thermal: dict, hvac_type: str,
    ) -> dict | None:
        """Check if we should start pre-conditioning for an upcoming transition."""
        minutes_until = (next_transition - now).total_seconds() / 60.0
        if minutes_until <= 0 or minutes_until > thermal["preconditioning_lead"] * 1.5:
            return None

        # Only pre-condition for transitions TO a higher-comfort mode
        mode_priority = {ScheduleMode.OFF: 0, ScheduleMode.AWAY: 1, ScheduleMode.ECO: 2, ScheduleMode.SLEEP: 3, ScheduleMode.COMFORT: 4, ScheduleMode.BOOST: 5}
        if mode_priority.get(next_mode, 0) <= mode_priority.get(current_mode, 0):
            return None

        # Estimate how much heating/cooling we'll need
        # For now, use a simple threshold: if we need to raise temp and lead time is approaching
        future_target = target_temp  # simplified — actual target will change at transition
        if current_temp < future_target - 0.5:
            return {
                "action": "pre_heat",
                "reason": f"Pre-heating: {current_mode}→{next_mode} in {minutes_until:.0f} min ({hvac_type} needs {thermal['preconditioning_lead']:.0f} min lead)",
                "target": future_target,
            }
        elif current_temp > future_target + 0.5:
            return {
                "action": "pre_cool",
                "reason": f"Pre-cooling: {current_mode}→{next_mode} in {minutes_until:.0f} min",
                "target": future_target,
            }
        return None

    def _check_energy_optimization(
        self, current_temp: float, target_temp: float, delta: float,
        energy_is_high: bool, energy_is_low: bool, energy_tier: str | None,
        next_tier_change: datetime | None, thermal: dict, now: datetime,
    ) -> dict | None:
        """Check if we can optimize around energy tier transitions."""
        if energy_tier is None:
            return None

        # During high rate: coast if possible (don't heat unless absolutely necessary)
        if energy_is_high and delta > 0 and delta < 1.5:
            coast_rate = thermal["cool_down_rate"]  # °C/hr loss
            if next_tier_change:
                hours_until = (next_tier_change - now).total_seconds() / 3600.0
                temp_loss = coast_rate * hours_until
                if current_temp - temp_loss > target_temp - 1.0:
                    return {
                        "action": "idle",
                        "reason": f"Coasting through high rate — temp loss ~{temp_loss:.1f}°C in {hours_until:.1f}h, still above minimum",
                        "target_temp": target_temp,
                        "energy_note": f"Saving energy: avoiding {energy_tier} tier",
                    }

        # During low rate: pre-heat slightly above target if high rate is coming
        if energy_is_low and next_tier_change:
            hours_until = (next_tier_change - now).total_seconds() / 3600.0
            if 0 < hours_until < 2.0 and delta <= 0.3:
                overshoot = min(1.0, thermal["cool_down_rate"] * 2.0)
                return {
                    "action": "heat",
                    "reason": f"Pre-heating +{overshoot:.1f}°C during low rate — rate change in {hours_until:.1f}h",
                    "target_temp": target_temp + overshoot,
                    "energy_note": f"Using {energy_tier} rate to pre-heat",
                }
        return None

    def _check_weather_anticipation(
        self, current_temp: float, target_temp: float, outdoor_temp: float | None,
        forecast_temps: list[float] | None, delta: float, thermal: dict,
    ) -> dict | None:
        """Check if weather forecast warrants preemptive action."""
        if outdoor_temp is None or not forecast_temps:
            return None

        # Check for significant temperature drop in the next few hours
        min_forecast = min(forecast_temps[:FORECAST_LOOKAHEAD_HOURS]) if len(forecast_temps) >= FORECAST_LOOKAHEAD_HOURS else min(forecast_temps)
        temp_drop = outdoor_temp - min_forecast

        if temp_drop >= FORECAST_SIGNIFICANT_DROP and delta >= -0.5:
            return {
                "action": "pre_heat",
                "reason": f"Weather: outdoor temp dropping {temp_drop:.1f}°C in next {FORECAST_LOOKAHEAD_HOURS}h ({outdoor_temp:.0f}°C → {min_forecast:.0f}°C) — starting gentle pre-heat",
                "target_temp": target_temp + 0.5,
            }

        # Check for significant temperature rise (for cooling systems)
        max_forecast = max(forecast_temps[:FORECAST_LOOKAHEAD_HOURS]) if len(forecast_temps) >= FORECAST_LOOKAHEAD_HOURS else max(forecast_temps)
        temp_rise = max_forecast - outdoor_temp

        if temp_rise >= FORECAST_SIGNIFICANT_DROP and delta <= 0.5:
            return {
                "action": "pre_cool",
                "reason": f"Weather: outdoor temp rising {temp_rise:.1f}°C in next {FORECAST_LOOKAHEAD_HOURS}h ({outdoor_temp:.0f}°C → {max_forecast:.0f}°C) — starting pre-cool",
                "target_temp": target_temp - 0.5,
            }
        return None

    def _calculate_confidence(self, space_id: str) -> float:
        """Calculate confidence level based on learned data quality."""
        learned = self._learned_thermal.get(space_id)
        if not learned:
            return 0.3  # Default confidence with no learned data
        samples = learned.get("samples", 0)
        if samples >= 30:
            return 1.0
        if samples >= 14:
            return 0.8
        if samples >= 7:
            return 0.6
        return 0.3
