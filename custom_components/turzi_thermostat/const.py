"""Constants for the Turzi Smart Thermostat integration."""

from enum import StrEnum

DOMAIN = "turzi_thermostat"
PLATFORMS = ["climate", "sensor"]

# Storage
STORAGE_KEY = f"{DOMAIN}.config"
STORAGE_VERSION = 1

# Coordinator
DEFAULT_UPDATE_INTERVAL = 60  # seconds

# Config flow keys
CONF_INSTANCE_NAME = "instance_name"
CONF_WEATHER_ENTITY = "weather_entity"


class HvacSystemType(StrEnum):
    """HVAC system types with different thermal characteristics."""

    FLOOR_HEATING = "floor_heating"
    RADIATOR = "radiator"
    FAN_COIL = "fan_coil"
    SPLIT_AC = "split_ac"


HVAC_SYSTEM_LABELS = {
    HvacSystemType.FLOOR_HEATING: "Floor Heating",
    HvacSystemType.RADIATOR: "Radiator",
    HvacSystemType.FAN_COIL: "Fan-Coil",
    HvacSystemType.SPLIT_AC: "Split A/C",
}


class ScheduleMode(StrEnum):
    """Schedule modes with temperature offsets from comfort target."""

    COMFORT = "comfort"
    ECO = "eco"
    SLEEP = "sleep"
    AWAY = "away"
    OFF = "off"
    BOOST = "boost"


# Temperature offsets from comfort target per schedule mode (°C)
SCHEDULE_MODE_OFFSETS: dict[str, float | None] = {
    ScheduleMode.COMFORT: 0.0,
    ScheduleMode.ECO: -2.0,
    ScheduleMode.SLEEP: -1.0,
    ScheduleMode.AWAY: -4.0,
    ScheduleMode.OFF: None,  # System disabled
    ScheduleMode.BOOST: None,  # Handled separately — max output for 30 min
}

BOOST_DURATION_MINUTES = 30


class SeasonalMode(StrEnum):
    """Seasonal operating mode — controls which actions are allowed."""

    WINTER = "winter"   # Heating only (no cooling)
    SUMMER = "summer"   # Cooling only (no heating)
    AUTO = "auto"       # Both heating and cooling allowed


# Thermal inertia defaults per HVAC system type
# heat_up_rate: °C per hour the system can raise indoor temp
# cool_down_rate: °C per hour the space loses temp (passive, system off)
# preconditioning_lead: minutes of lead time needed to reach target
THERMAL_DEFAULTS: dict[str, dict[str, float]] = {
    HvacSystemType.FLOOR_HEATING: {
        "heat_up_rate": 0.3,
        "cool_down_rate": 0.1,
        "preconditioning_lead": 120.0,
    },
    HvacSystemType.RADIATOR: {
        "heat_up_rate": 1.0,
        "cool_down_rate": 0.3,
        "preconditioning_lead": 45.0,
    },
    HvacSystemType.FAN_COIL: {
        "heat_up_rate": 2.0,
        "cool_down_rate": 0.5,
        "preconditioning_lead": 20.0,
    },
    HvacSystemType.SPLIT_AC: {
        "heat_up_rate": 3.0,
        "cool_down_rate": 1.0,
        "preconditioning_lead": 10.0,
    },
}

# Comfort model defaults
DEFAULT_TARGET_TEMP = 21.0  # °C
DEFAULT_MIN_TEMP = 5.0
DEFAULT_MAX_TEMP = 35.0
TEMP_STEP = 0.5

# PMV comfort model constants
DEFAULT_METABOLIC_RATE = 1.2  # met — sedentary activity
DEFAULT_AIR_VELOCITY: dict[str, float] = {
    HvacSystemType.FLOOR_HEATING: 0.05,  # m/s — minimal air movement
    HvacSystemType.RADIATOR: 0.10,
    HvacSystemType.FAN_COIL: 0.20,
    HvacSystemType.SPLIT_AC: 0.25,
}

# Clothing insulation estimates based on outdoor temp (clo)
# Warmer outdoors → lighter clothing indoors
CLOTHING_INSULATION_WARM = 0.5   # clo — summer clothing (outdoor > 25°C)
CLOTHING_INSULATION_MILD = 0.7   # clo — spring/autumn (15-25°C)
CLOTHING_INSULATION_COLD = 1.0   # clo — winter clothing (outdoor < 15°C)

# Wind chill thresholds
WIND_COMPENSATION_THRESHOLD = 20.0  # km/h — start compensating above this
WIND_COMPENSATION_MAX = 1.0  # °C — maximum target increase from wind

# Humidity compensation
HUMIDITY_HIGH_THRESHOLD = 65.0  # % — start reducing target above this
HUMIDITY_LOW_THRESHOLD = 30.0   # % — start increasing target below this
HUMIDITY_COMPENSATION_MAX = 0.5  # °C — maximum adjustment

# Thermal learning
LEARNING_MIN_SAMPLES = 7  # days of data before using learned rates
LEARNING_CONFIDENCE_THRESHOLD = 0.7  # 0.0–1.0

# Weather forecast
FORECAST_SIGNIFICANT_DROP = 5.0  # °C — trigger pre-heating if outdoor temp drops this much
FORECAST_LOOKAHEAD_HOURS = 3  # hours to look ahead for weather changes

# Frontend panel
PANEL_URL = "turzi-thermostat"
PANEL_TITLE = "Smart Thermostat"
PANEL_ICON = "mdi:thermostat-auto"

# Days of week
DAYS_OF_WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]
WEEKENDS = ["sat", "sun"]
