"""Simplified PMV (Predicted Mean Vote) comfort model.

Based on ISO 7730 / ASHRAE 55 thermal comfort standard.
Calculates a comfort score (0-100) and temperature adjustment
recommendations based on indoor temp, humidity, air velocity,
and outdoor conditions.
"""

from __future__ import annotations

import math
import logging

from .const import (
    CLOTHING_INSULATION_COLD,
    CLOTHING_INSULATION_MILD,
    CLOTHING_INSULATION_WARM,
    DEFAULT_AIR_VELOCITY,
    DEFAULT_METABOLIC_RATE,
    HUMIDITY_COMPENSATION_MAX,
    HUMIDITY_HIGH_THRESHOLD,
    HUMIDITY_LOW_THRESHOLD,
    WIND_COMPENSATION_MAX,
    WIND_COMPENSATION_THRESHOLD,
    HvacSystemType,
)

_LOGGER = logging.getLogger(__name__)


def _estimate_clothing_insulation(outdoor_temp: float | None) -> float:
    """Estimate clothing insulation (clo) based on outdoor temperature.

    People dress according to outdoor conditions, which affects how
    comfortable they feel at a given indoor temperature.
    """
    if outdoor_temp is None:
        return CLOTHING_INSULATION_MILD
    if outdoor_temp > 25.0:
        return CLOTHING_INSULATION_WARM
    if outdoor_temp < 15.0:
        return CLOTHING_INSULATION_COLD
    # Linear interpolation between cold and warm
    t = (outdoor_temp - 15.0) / 10.0
    return CLOTHING_INSULATION_COLD + t * (CLOTHING_INSULATION_WARM - CLOTHING_INSULATION_COLD)


def _calculate_pmv(
    air_temp: float,
    mean_radiant_temp: float,
    air_velocity: float,
    relative_humidity: float,
    metabolic_rate: float,
    clothing_insulation: float,
) -> float:
    """Calculate the Predicted Mean Vote (PMV) index.

    PMV ranges from -3 (cold) to +3 (hot), with 0 being neutral/comfortable.
    This is a simplified version of the ISO 7730 calculation.

    Args:
        air_temp: Indoor air temperature (°C)
        mean_radiant_temp: Mean radiant temperature (°C), assumed equal to air temp
        air_velocity: Air velocity (m/s)
        relative_humidity: Relative humidity (%)
        metabolic_rate: Metabolic rate (met)
        clothing_insulation: Clothing insulation (clo)

    Returns:
        PMV value (-3 to +3)
    """
    # Convert units
    m = metabolic_rate * 58.15  # W/m²
    w = 0.0  # External work, assumed 0 for sedentary
    icl = clothing_insulation * 0.155  # m²·K/W
    ta = air_temp
    tr = mean_radiant_temp
    va = max(air_velocity, 0.05)  # Minimum air velocity
    pa = relative_humidity * 10.0 * math.exp(16.6536 - 4030.183 / (ta + 235.0))  # Pa

    # Clothing surface area factor
    if icl < 0.078:
        fcl = 1.0 + 1.290 * icl
    else:
        fcl = 1.05 + 0.645 * icl

    # Heat transfer coefficient (iterative)
    tcl = ta  # Initial guess for clothing surface temperature
    for _ in range(150):
        tcl_old = tcl

        # Convective heat transfer coefficient
        hc_natural = 2.38 * abs(tcl - ta) ** 0.25
        hc_forced = 12.1 * math.sqrt(va)
        hc = max(hc_natural, hc_forced)

        # Clothing surface temperature
        tcl = 35.7 - 0.028 * (m - w) - icl * (
            3.96e-8 * fcl * ((tcl + 273.0) ** 4 - (tr + 273.0) ** 4)
            + fcl * hc * (tcl - ta)
        )

        if abs(tcl - tcl_old) < 0.001:
            break

    # Recalculate hc with final tcl
    hc_natural = 2.38 * abs(tcl - ta) ** 0.25
    hc_forced = 12.1 * math.sqrt(va)
    hc = max(hc_natural, hc_forced)

    # PMV calculation
    pm1 = 0.303 * math.exp(-0.036 * m) + 0.028
    pm2 = (m - w) - 3.05e-3 * (5733.0 - 6.99 * (m - w) - pa)
    pm3 = -0.42 * ((m - w) - 58.15)
    pm4 = -1.7e-5 * m * (5867.0 - pa)
    pm5 = -0.0014 * m * (34.0 - ta)
    pm6 = -3.96e-8 * fcl * ((tcl + 273.0) ** 4 - (tr + 273.0) ** 4)
    pm7 = -fcl * hc * (tcl - ta)

    pmv = pm1 * (pm2 + pm3 + pm4 + pm5 + pm6 + pm7)

    # Clamp to valid range
    return max(-3.0, min(3.0, pmv))


def pmv_to_comfort_score(pmv: float) -> float:
    """Convert PMV (-3 to +3) to a comfort score (0 to 100).

    PMV 0 = 100 (perfect comfort)
    PMV ±1 = ~65 (slightly warm/cool)
    PMV ±2 = ~30 (warm/cool)
    PMV ±3 = 0 (hot/cold)
    """
    # Gaussian-like mapping centered on 0
    score = 100.0 * math.exp(-0.5 * (pmv / 1.2) ** 2)
    return max(0.0, min(100.0, round(score, 1)))


def calculate_comfort(
    indoor_temp: float | None,
    indoor_humidity: float | None,
    outdoor_temp: float | None,
    wind_speed: float | None,
    hvac_type: str,
    humidity_compensation: bool = True,
    wind_compensation: bool = True,
) -> ComfortResult:
    """Calculate comfort score and temperature adjustments.

    Args:
        indoor_temp: Current indoor temperature (°C)
        indoor_humidity: Current indoor relative humidity (%)
        outdoor_temp: Current outdoor temperature (°C)
        wind_speed: Current outdoor wind speed (km/h)
        hvac_type: HVAC system type (affects air velocity estimate)
        humidity_compensation: Whether to adjust target for humidity
        wind_compensation: Whether to adjust target for wind

    Returns:
        ComfortResult with score and adjustments
    """
    if indoor_temp is None:
        return ComfortResult(
            score=None,
            temp_adjustment=0.0,
            humidity_adjustment=0.0,
            wind_adjustment=0.0,
            total_adjustment=0.0,
            pmv=None,
            reason="No indoor temperature data available",
        )

    humidity = indoor_humidity if indoor_humidity is not None else 50.0
    clothing = _estimate_clothing_insulation(outdoor_temp)
    air_velocity = DEFAULT_AIR_VELOCITY.get(hvac_type, 0.1)

    # Calculate PMV
    pmv = _calculate_pmv(
        air_temp=indoor_temp,
        mean_radiant_temp=indoor_temp,  # Simplified: assume MRT = air temp
        air_velocity=air_velocity,
        relative_humidity=humidity,
        metabolic_rate=DEFAULT_METABOLIC_RATE,
        clothing_insulation=clothing,
    )

    score = pmv_to_comfort_score(pmv)

    # Humidity adjustment
    humidity_adj = 0.0
    if humidity_compensation and indoor_humidity is not None:
        if indoor_humidity > HUMIDITY_HIGH_THRESHOLD:
            # High humidity makes it feel warmer — reduce target
            excess = (indoor_humidity - HUMIDITY_HIGH_THRESHOLD) / (100.0 - HUMIDITY_HIGH_THRESHOLD)
            humidity_adj = -min(excess * HUMIDITY_COMPENSATION_MAX * 2, HUMIDITY_COMPENSATION_MAX)
        elif indoor_humidity < HUMIDITY_LOW_THRESHOLD:
            # Low humidity makes it feel cooler — increase target
            deficit = (HUMIDITY_LOW_THRESHOLD - indoor_humidity) / HUMIDITY_LOW_THRESHOLD
            humidity_adj = min(deficit * HUMIDITY_COMPENSATION_MAX * 2, HUMIDITY_COMPENSATION_MAX)

    # Wind chill adjustment
    wind_adj = 0.0
    if wind_compensation and wind_speed is not None:
        if wind_speed > WIND_COMPENSATION_THRESHOLD:
            # High wind increases heat loss — increase target
            excess = (wind_speed - WIND_COMPENSATION_THRESHOLD) / 30.0  # normalize
            wind_adj = min(excess * WIND_COMPENSATION_MAX, WIND_COMPENSATION_MAX)

    total_adj = round(humidity_adj + wind_adj, 1)

    # Build reason string
    reasons = []
    if humidity_adj != 0.0:
        direction = "reducing" if humidity_adj < 0 else "increasing"
        reasons.append(
            f"Humidity at {indoor_humidity:.0f}%, {direction} target by {abs(humidity_adj):.1f}°C"
        )
    if wind_adj != 0.0:
        reasons.append(
            f"Wind at {wind_speed:.0f} km/h, increasing target by {wind_adj:.1f}°C"
        )

    return ComfortResult(
        score=score,
        temp_adjustment=total_adj,
        humidity_adjustment=round(humidity_adj, 1),
        wind_adjustment=round(wind_adj, 1),
        total_adjustment=total_adj,
        pmv=round(pmv, 2),
        reason="; ".join(reasons) if reasons else "Comfortable",
    )


class ComfortResult:
    """Result of a comfort calculation."""

    def __init__(
        self,
        score: float | None,
        temp_adjustment: float,
        humidity_adjustment: float,
        wind_adjustment: float,
        total_adjustment: float,
        pmv: float | None,
        reason: str,
    ) -> None:
        """Initialize comfort result."""
        self.score = score
        self.temp_adjustment = temp_adjustment
        self.humidity_adjustment = humidity_adjustment
        self.wind_adjustment = wind_adjustment
        self.total_adjustment = total_adjustment
        self.pmv = pmv
        self.reason = reason

    def as_dict(self) -> dict:
        """Return as dictionary for serialization."""
        return {
            "score": self.score,
            "temp_adjustment": self.temp_adjustment,
            "humidity_adjustment": self.humidity_adjustment,
            "wind_adjustment": self.wind_adjustment,
            "total_adjustment": self.total_adjustment,
            "pmv": self.pmv,
            "reason": self.reason,
        }
