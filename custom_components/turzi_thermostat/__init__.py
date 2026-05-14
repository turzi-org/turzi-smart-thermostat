"""Turzi Smart Thermostat — Integration entry point.

Sets up the coordinator, registers the sidebar panel,
WebSocket commands, and forwards platform setup.
"""

from __future__ import annotations

import logging
import os

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_WEATHER_ENTITY,
    DOMAIN,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL,
    PLATFORMS,
)
from .coordinator import TurziCoordinator
from .store import TurziStore
from .websocket import async_register_websocket_commands

_LOGGER = logging.getLogger(__name__)

PANEL_FRONTEND_PATH = os.path.join(os.path.dirname(__file__), "frontend")


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Turzi Smart Thermostat component."""
    hass.data.setdefault(DOMAIN, {})

    # Register WebSocket commands (once, not per entry)
    async_register_websocket_commands(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Turzi Smart Thermostat from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    weather_entity_id = entry.data[CONF_WEATHER_ENTITY]

    # Initialize store
    store = TurziStore(hass, entry.entry_id)
    await store.async_load()

    # Initialize coordinator
    coordinator = TurziCoordinator(hass, store, weather_entity_id)

    # Store references
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "store": store,
    }

    # Register frontend panel (static path + sidebar entry)
    hass.http.register_static_path(
        f"/turzi_thermostat_panel",
        PANEL_FRONTEND_PATH,
        cache_headers=False,
    )

    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_URL,
        config={
            "_panel_custom": {
                "name": "turzi-thermostat-panel",
                "module_url": "/turzi_thermostat_panel/panel.js",
            }
        },
        require_admin=False,
    )

    # Initial data fetch
    await coordinator.async_config_entry_first_refresh()

    # Forward platform setup
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

        # Remove sidebar panel
        frontend.async_remove_panel(hass, PANEL_URL)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove a config entry and its stored data."""
    store = TurziStore(hass, entry.entry_id)
    await store.async_remove()
