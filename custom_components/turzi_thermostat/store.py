"""Async JSON storage for Turzi Smart Thermostat configuration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_TARGET_TEMP,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


def _default_config() -> dict[str, Any]:
    """Return the default configuration structure."""
    return {
        "spaces": {},
        "schedule": {},
        "energy_rates": {
            "tiers": [],
            "schedule": [],
        },
        "settings": {
            "humidity_compensation": True,
            "wind_compensation": True,
            "preconditioning_enabled": True,
            "seasonal_mode": "auto",
            "seasonal_switch_entity": None,
        },
        "learned_thermal": {},
    }


class TurziStore:
    """Manages persistent configuration storage for the integration.

    All zone/schedule/energy/settings configuration is stored as JSON
    via HA's async Store, rather than in config_entry options, because
    the primary configuration UI is the custom frontend panel.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the store."""
        self._hass = hass
        self._entry_id = entry_id
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry_id}")
        self._data: dict[str, Any] = _default_config()

    @property
    def data(self) -> dict[str, Any]:
        """Return the current configuration data."""
        return self._data

    @property
    def spaces(self) -> dict[str, Any]:
        """Return the spaces configuration."""
        return self._data.get("spaces", {})

    @property
    def schedule(self) -> dict[str, Any]:
        """Return the schedule configuration."""
        return self._data.get("schedule", {})

    @property
    def energy_rates(self) -> dict[str, Any]:
        """Return the energy rates configuration."""
        return self._data.get("energy_rates", {"tiers": [], "schedule": []})

    @property
    def settings(self) -> dict[str, Any]:
        """Return the global settings."""
        return self._data.get("settings", {})

    @property
    def learned_thermal(self) -> dict[str, Any]:
        """Return learned thermal data."""
        return self._data.get("learned_thermal", {})

    async def async_load(self) -> None:
        """Load configuration from disk."""
        stored = await self._store.async_load()
        if stored is not None:
            # Merge with defaults so new keys are always present
            default = _default_config()
            for key in default:
                if key not in stored:
                    stored[key] = default[key]
            self._data = stored
        else:
            self._data = _default_config()
        _LOGGER.debug("Loaded Turzi config with %d spaces", len(self.spaces))

    async def async_save(self) -> None:
        """Save current configuration to disk."""
        await self._store.async_save(self._data)
        _LOGGER.debug("Saved Turzi config with %d spaces", len(self.spaces))

    # --- Space management ---

    def add_space(
        self,
        space_id: str,
        name: str,
        hvac_type: str,
        temp_sensor: str,
        heating_output: str,
        humidity_sensor: str | None = None,
        cooling_output: str | None = None,
        auxiliary_heating: str | None = None,
        target_temp: float = DEFAULT_TARGET_TEMP,
        comfort_sensitivity: str = "medium",
    ) -> None:
        """Add or update a space configuration."""
        self._data["spaces"][space_id] = {
            "name": name,
            "hvac_type": hvac_type,
            "temp_sensor": temp_sensor,
            "humidity_sensor": humidity_sensor,
            "heating_output": heating_output,
            "cooling_output": cooling_output,
            "auxiliary_heating": auxiliary_heating,
            "target_temp": target_temp,
            "comfort_sensitivity": comfort_sensitivity,
        }
        # Initialize empty schedule if new space
        if space_id not in self._data["schedule"]:
            self._data["schedule"][space_id] = []

    def remove_space(self, space_id: str) -> bool:
        """Remove a space configuration. Returns True if removed."""
        removed = False
        if space_id in self._data["spaces"]:
            del self._data["spaces"][space_id]
            removed = True
        if space_id in self._data["schedule"]:
            del self._data["schedule"][space_id]
        if space_id in self._data["learned_thermal"]:
            del self._data["learned_thermal"][space_id]
        return removed

    # --- Schedule management ---

    def set_schedule(self, space_id: str, schedule_blocks: list[dict]) -> None:
        """Set the schedule for a space.

        Each block: {"days": [...], "start": "HH:MM", "end": "HH:MM", "mode": "..."}
        """
        self._data["schedule"][space_id] = schedule_blocks

    # --- Energy rates management ---

    def set_energy_tiers(self, tiers: list[dict]) -> None:
        """Set energy rate tier definitions.

        Each tier: {"name": "Low", "color": "#4CAF50"}
        """
        self._data["energy_rates"]["tiers"] = tiers

    def set_energy_schedule(self, schedule_blocks: list[dict]) -> None:
        """Set the energy rate schedule.

        Each block: {"days": [...], "start": "HH:MM", "end": "HH:MM", "tier": "Low"}
        """
        self._data["energy_rates"]["schedule"] = schedule_blocks

    # --- Settings management ---

    def update_settings(self, settings: dict[str, Any]) -> None:
        """Update global settings (merges with existing)."""
        self._data["settings"].update(settings)

    # --- Thermal learning ---

    def update_learned_thermal(
        self,
        space_id: str,
        heat_up_rate: float,
        cool_down_rate: float,
        samples: int,
        last_updated: str,
    ) -> None:
        """Update learned thermal data for a space."""
        self._data["learned_thermal"][space_id] = {
            "heat_up_rate": heat_up_rate,
            "cool_down_rate": cool_down_rate,
            "samples": samples,
            "last_updated": last_updated,
        }

    async def async_remove(self) -> None:
        """Remove stored data (called on integration unload/removal)."""
        await self._store.async_remove()
