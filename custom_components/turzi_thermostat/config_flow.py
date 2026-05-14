"""Config flow for Turzi Smart Thermostat.

Minimal setup: just instance name + weather entity selection.
All real configuration happens in the sidebar panel.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from .const import CONF_INSTANCE_NAME, CONF_WEATHER_ENTITY, DOMAIN

_LOGGER = logging.getLogger(__name__)


class TurziThermostatConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Turzi Smart Thermostat."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate weather entity
            weather_id = user_input[CONF_WEATHER_ENTITY]
            state = self.hass.states.get(weather_id)
            if state is None or not weather_id.startswith("weather."):
                errors[CONF_WEATHER_ENTITY] = "invalid_weather_entity"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_INSTANCE_NAME],
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_INSTANCE_NAME, default="My Home"): str,
                vol.Required(CONF_WEATHER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="weather")
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
