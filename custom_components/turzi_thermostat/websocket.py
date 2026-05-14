"""WebSocket API for the Turzi Smart Thermostat frontend panel."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, HvacSystemType, ComfortSensitivity

_LOGGER = logging.getLogger(__name__)


def _create_entities_for_new_spaces(
    hass: HomeAssistant,
    entry_data: dict,
    entry_id: str,
    space_ids: list[str],
) -> None:
    """Create climate and sensor entities for newly added spaces."""
    from .climate import TurziClimateEntity
    from .sensor import (
        TurziComfortScoreSensor,
        TurziEffectiveTargetSensor,
        TurziScheduleModeSensor,
        TurziEnergyTierSensor,
        TurziStrategySensor,
    )

    store = entry_data["store"]
    coordinator = entry_data["coordinator"]

    # Get the config entry from hass
    entry = hass.config_entries.async_get_entry(entry_id)
    if not entry:
        return

    climate_add = entry_data.get("climate_add_entities")
    climate_known = entry_data.get("climate_known_ids", set())
    sensor_add = entry_data.get("sensor_add_entities")
    sensor_known = entry_data.get("sensor_known_ids", set())

    new_climate = []
    new_sensors = []

    for space_id in space_ids:
        if space_id in climate_known:
            continue  # Already has entities

        space_config = store.spaces.get(space_id)
        if not space_config:
            continue

        name = space_config.get("name", space_id)

        # Climate entity
        if climate_add:
            new_climate.append(
                TurziClimateEntity(coordinator, entry, space_id, space_config)
            )
            climate_known.add(space_id)

        # Sensor entities
        if sensor_add:
            new_sensors.extend([
                TurziComfortScoreSensor(coordinator, entry, space_id, name),
                TurziEffectiveTargetSensor(coordinator, entry, space_id, name),
                TurziScheduleModeSensor(coordinator, entry, space_id, name),
                TurziEnergyTierSensor(coordinator, entry, space_id, name),
                TurziStrategySensor(coordinator, entry, space_id, name),
            ])
            sensor_known.add(space_id)

    if new_climate and climate_add:
        climate_add(new_climate)
        _LOGGER.info("Dynamically added %d climate entities", len(new_climate))

    if new_sensors and sensor_add:
        sensor_add(new_sensors)
        _LOGGER.info("Dynamically added %d sensor entities", len(new_sensors))


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register all websocket commands."""
    websocket_api.async_register_command(hass, ws_get_config)
    websocket_api.async_register_command(hass, ws_save_spaces)
    websocket_api.async_register_command(hass, ws_delete_space)
    websocket_api.async_register_command(hass, ws_save_schedule)
    websocket_api.async_register_command(hass, ws_save_energy_rates)
    websocket_api.async_register_command(hass, ws_save_settings)
    websocket_api.async_register_command(hass, ws_get_strategy)
    websocket_api.async_register_command(hass, ws_get_dashboard)
    websocket_api.async_register_command(hass, ws_get_available_entities)


def _get_entry_data(hass: HomeAssistant, entry_id: str) -> dict | None:
    """Get the integration data for an entry."""
    domain_data = hass.data.get(DOMAIN, {})
    return domain_data.get(entry_id)


def _slugify(name: str) -> str:
    """Convert a name to a slug suitable for use as a space_id."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug or "space"


# --- Get Config ---

@websocket_api.websocket_command({
    vol.Required("type"): "turzi_thermostat/get_config",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def ws_get_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Return the full configuration."""
    entry_data = _get_entry_data(hass, msg["entry_id"])
    if not entry_data:
        connection.send_error(msg["id"], "not_found", "Integration entry not found")
        return
    store = entry_data["store"]
    connection.send_result(msg["id"], store.data)


# --- Save Spaces ---

@websocket_api.websocket_command({
    vol.Required("type"): "turzi_thermostat/save_spaces",
    vol.Required("entry_id"): str,
    vol.Required("spaces"): [
        {
            vol.Required("name"): str,
            vol.Required("hvac_type"): vol.In([e.value for e in HvacSystemType]),
            vol.Required("temp_sensor"): str,
            vol.Optional("humidity_sensor"): vol.Any(str, None),
            vol.Required("heating_output"): str,
            vol.Optional("cooling_output"): vol.Any(str, None),
            vol.Optional("auxiliary_heating"): vol.Any(str, None),
            vol.Optional("target_temp", default=21.0): vol.Coerce(float),
            vol.Optional("comfort_sensitivity", default="medium"): vol.In([e.value for e in ComfortSensitivity]),
        }
    ],
})
@websocket_api.async_response
async def ws_save_spaces(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Save/update space configurations."""
    entry_data = _get_entry_data(hass, msg["entry_id"])
    if not entry_data:
        connection.send_error(msg["id"], "not_found", "Integration entry not found")
        return

    store = entry_data["store"]
    coordinator = entry_data["coordinator"]

    new_space_ids = []
    for space in msg["spaces"]:
        space_id = _slugify(space["name"])
        store.add_space(
            space_id=space_id,
            name=space["name"],
            hvac_type=space["hvac_type"],
            temp_sensor=space["temp_sensor"],
            humidity_sensor=space.get("humidity_sensor"),
            heating_output=space["heating_output"],
            cooling_output=space.get("cooling_output"),
            auxiliary_heating=space.get("auxiliary_heating"),
            target_temp=space.get("target_temp", 21.0),
            comfort_sensitivity=space.get("comfort_sensitivity", "medium"),
        )
        new_space_ids.append(space_id)

    await store.async_save()
    await coordinator.async_request_refresh()

    # Dynamically create entities for any new spaces
    _create_entities_for_new_spaces(hass, entry_data, msg["entry_id"], new_space_ids)

    connection.send_result(msg["id"], {"success": True, "spaces": store.spaces})


# --- Delete Space ---

@websocket_api.websocket_command({
    vol.Required("type"): "turzi_thermostat/delete_space",
    vol.Required("entry_id"): str,
    vol.Required("space_id"): str,
})
@websocket_api.async_response
async def ws_delete_space(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Remove a space."""
    entry_data = _get_entry_data(hass, msg["entry_id"])
    if not entry_data:
        connection.send_error(msg["id"], "not_found", "Integration entry not found")
        return

    store = entry_data["store"]
    coordinator = entry_data["coordinator"]

    removed = store.remove_space(msg["space_id"])
    if removed:
        await store.async_save()
        await coordinator.async_request_refresh()

    connection.send_result(msg["id"], {"success": removed})


# --- Save Schedule ---

@websocket_api.websocket_command({
    vol.Required("type"): "turzi_thermostat/save_schedule",
    vol.Required("entry_id"): str,
    vol.Required("space_id"): str,
    vol.Required("blocks"): [
        {
            vol.Required("days"): [str],
            vol.Required("start"): str,
            vol.Required("end"): str,
            vol.Required("mode"): str,
            vol.Optional("temp_override"): vol.Any(float, None),
        }
    ],
})
@websocket_api.async_response
async def ws_save_schedule(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Save schedule for a space."""
    entry_data = _get_entry_data(hass, msg["entry_id"])
    if not entry_data:
        connection.send_error(msg["id"], "not_found", "Integration entry not found")
        return

    store = entry_data["store"]
    coordinator = entry_data["coordinator"]

    store.set_schedule(msg["space_id"], msg["blocks"])
    await store.async_save()
    await coordinator.async_request_refresh()

    connection.send_result(msg["id"], {"success": True})


# --- Save Energy Rates ---

@websocket_api.websocket_command({
    vol.Required("type"): "turzi_thermostat/save_energy_rates",
    vol.Required("entry_id"): str,
    vol.Required("tiers"): [
        {
            vol.Required("name"): str,
            vol.Optional("color", default="#888888"): str,
        }
    ],
    vol.Required("schedule"): [
        {
            vol.Required("days"): [str],
            vol.Required("start"): str,
            vol.Required("end"): str,
            vol.Required("tier"): str,
        }
    ],
})
@websocket_api.async_response
async def ws_save_energy_rates(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Save energy rate tiers and schedule."""
    entry_data = _get_entry_data(hass, msg["entry_id"])
    if not entry_data:
        connection.send_error(msg["id"], "not_found", "Integration entry not found")
        return

    store = entry_data["store"]
    coordinator = entry_data["coordinator"]

    store.set_energy_tiers(msg["tiers"])
    store.set_energy_schedule(msg["schedule"])
    await store.async_save()
    await coordinator.async_request_refresh()

    connection.send_result(msg["id"], {"success": True})


# --- Save Settings ---

@websocket_api.websocket_command({
    vol.Required("type"): "turzi_thermostat/save_settings",
    vol.Required("entry_id"): str,
    vol.Required("settings"): dict,
})
@websocket_api.async_response
async def ws_save_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Save global settings."""
    entry_data = _get_entry_data(hass, msg["entry_id"])
    if not entry_data:
        connection.send_error(msg["id"], "not_found", "Integration entry not found")
        return

    store = entry_data["store"]
    coordinator = entry_data["coordinator"]

    store.update_settings(msg["settings"])
    await store.async_save()
    await coordinator.async_request_refresh()

    connection.send_result(msg["id"], {"success": True})


# --- Get Strategy ---

@websocket_api.websocket_command({
    vol.Required("type"): "turzi_thermostat/get_strategy",
    vol.Required("entry_id"): str,
    vol.Required("space_id"): str,
})
@websocket_api.async_response
async def ws_get_strategy(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Get current strategy for a space."""
    entry_data = _get_entry_data(hass, msg["entry_id"])
    if not entry_data:
        connection.send_error(msg["id"], "not_found", "Integration entry not found")
        return

    coordinator = entry_data["coordinator"]
    if coordinator.data and msg["space_id"] in coordinator.data.spaces:
        space = coordinator.data.spaces[msg["space_id"]]
        result: dict[str, Any] = {
            "strategy": space.strategy.as_dict() if space.strategy else None,
            "comfort": space.comfort.as_dict() if space.comfort else None,
            "schedule_mode": space.schedule_mode,
            "energy_tier": space.energy_tier,
        }
        # Include learned thermal data
        store = entry_data["store"]
        learned = store.learned_thermal.get(msg["space_id"])
        if learned:
            result["learned_thermal"] = learned
        connection.send_result(msg["id"], result)
    else:
        connection.send_error(msg["id"], "not_found", "Space not found")


# --- Get Dashboard ---

@websocket_api.websocket_command({
    vol.Required("type"): "turzi_thermostat/get_dashboard",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def ws_get_dashboard(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Get live dashboard data for all spaces."""
    entry_data = _get_entry_data(hass, msg["entry_id"])
    if not entry_data:
        connection.send_error(msg["id"], "not_found", "Integration entry not found")
        return

    coordinator = entry_data["coordinator"]
    data = coordinator.data

    result: dict[str, Any] = {
        "spaces": {},
        "weather": {
            "outdoor_temp": data.outdoor_temp if data else None,
            "outdoor_humidity": data.outdoor_humidity if data else None,
            "wind_speed": data.wind_speed if data else None,
            "condition": data.weather_condition if data else None,
            "forecast_hourly": (data.forecast_hourly[:12] if data else []),
        },
    }

    if data:
        for space_id, space in data.spaces.items():
            result["spaces"][space_id] = {
                "name": space.name,
                "hvac_type": space.hvac_type,
                "current_temp": space.current_temp,
                "current_humidity": space.current_humidity,
                "target_temp": space.target_temp,
                "schedule_mode": space.schedule_mode,
                "hvac_action": space.hvac_action.value if space.hvac_action else "idle",
                "comfort_score": space.comfort.score if space.comfort else None,
                "energy_tier": space.energy_tier,
                "strategy_reason": space.strategy.reason if space.strategy else None,
            }

    connection.send_result(msg["id"], result)


# --- Get Available Entities ---

@websocket_api.websocket_command({
    vol.Required("type"): "turzi_thermostat/get_available_entities",
})
@callback
def ws_get_available_entities(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """List available sensor/switch/climate entities for zone configuration."""
    result: dict[str, list[dict]] = {
        "temperature_sensors": [],
        "humidity_sensors": [],
        "heating_outputs": [],
        "cooling_outputs": [],
        "switches": [],
    }

    for state in hass.states.async_all():
        entity_id = state.entity_id
        domain = entity_id.split(".")[0]
        attrs = state.attributes
        friendly_name = attrs.get("friendly_name", entity_id)
        entry = {"entity_id": entity_id, "name": friendly_name}

        # Temperature sensors
        if domain == "sensor" and attrs.get("device_class") == "temperature":
            result["temperature_sensors"].append(entry)

        # Humidity sensors
        if domain == "sensor" and attrs.get("device_class") == "humidity":
            result["humidity_sensors"].append(entry)

        # Switches (potential heating/cooling outputs + seasonal mode toggle)
        if domain == "switch":
            result["heating_outputs"].append(entry)
            result["cooling_outputs"].append(entry)
            result["switches"].append(entry)

        # Climate entities (potential heating/cooling outputs)
        if domain == "climate" and not entity_id.startswith("climate.turzi_"):
            result["heating_outputs"].append(entry)
            result["cooling_outputs"].append(entry)

    connection.send_result(msg["id"], result)
