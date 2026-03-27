"""Support for the OpenCWB (OCWB) service."""
from .abstract_ocwb_sensor import AbstractOpenCWBSensor
from .const import (
    ATTR_API_FORECAST_DAILY,
    ATTR_API_FORECAST_HOURLY,
    CONF_LOCATION_NAME,
    DOMAIN,
    ENTRY_NAME,
    ENTRY_WEATHER_COORDINATOR,
    FORECAST_MODE_HOURLY,
    FORECAST_MODE_ONECALL_HOURLY,
    FORECAST_MONITORED_CONDITIONS,
    FORECAST_SENSOR_TYPES,
    MONITORED_CONDITIONS,
    WEATHER_SENSOR_TYPES,
)
from .weather_update_coordinator import WeatherUpdateCoordinator


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up OpenCWB sensor entities based on a config entry."""
    domain_data = hass.data[DOMAIN][config_entry.entry_id]
    name = domain_data[ENTRY_NAME]
    weather_coordinator = domain_data[ENTRY_WEATHER_COORDINATOR]
    location_name = domain_data[CONF_LOCATION_NAME]

    weather_sensor_types = WEATHER_SENSOR_TYPES
    forecast_sensor_types = FORECAST_SENSOR_TYPES

    entities = []
    for sensor_type in MONITORED_CONDITIONS:
        unique_id = f"{config_entry.unique_id}-{sensor_type}-{location_name}"
        entities.append(
            OpenCWBSensor(
                f"{name} {location_name} {sensor_type}",
                unique_id,
                sensor_type,
                weather_sensor_types[sensor_type],
                weather_coordinator,
            )
        )

    for sensor_type in FORECAST_MONITORED_CONDITIONS:
        if (
            weather_coordinator.forecast_mode in (
                FORECAST_MODE_HOURLY,
                FORECAST_MODE_ONECALL_HOURLY,
            )
            and sensor_type == "templow"
        ):
            continue
        unique_id = f"{config_entry.unique_id}-forecast-{sensor_type}-{location_name}"
        entities.append(
            OpenCWBForecastSensor(
                f"{name} {location_name} Forecast {sensor_type}",
                unique_id,
                sensor_type,
                forecast_sensor_types[sensor_type],
                weather_coordinator,
            )
        )

    async_add_entities(entities)


class OpenCWBSensor(AbstractOpenCWBSensor):
    """Implementation of an OpenCWB sensor."""

    def __init__(
        self,
        name,
        unique_id,
        sensor_type,
        sensor_configuration,
        weather_coordinator: WeatherUpdateCoordinator,
    ):
        """Initialize the sensor."""
        super().__init__(
            name,
            unique_id,
            sensor_type,
            sensor_configuration,
            weather_coordinator
        )
        self._weather_coordinator = weather_coordinator
        self._attr_name = name.replace("_", " ")
        self._attr_unique_id = unique_id


    @property
    def state(self):
        """Return the state of the device."""
        return self._weather_coordinator.data.get(self._sensor_type, None)


class OpenCWBForecastSensor(AbstractOpenCWBSensor):
    """Implementation of an OpenCWB forecast sensor."""

    def __init__(
        self,
        name,
        unique_id,
        sensor_type,
        sensor_configuration,
        weather_coordinator: WeatherUpdateCoordinator,
    ):
        """Initialize the sensor."""
        super().__init__(
            name,
            unique_id,
            sensor_type,
            sensor_configuration,
            weather_coordinator
        )
        self._weather_coordinator = weather_coordinator
        self._attr_name = name.replace("_", " ")
        self._attr_unique_id = unique_id

    def _forecast_key(self):
        """Return the coordinator forecast key for the current forecast mode."""
        if self._weather_coordinator.forecast_mode in (
            FORECAST_MODE_HOURLY,
            FORECAST_MODE_ONECALL_HOURLY,
        ):
            return ATTR_API_FORECAST_HOURLY
        return ATTR_API_FORECAST_DAILY

    def _extract_value(self, forecast):
        """Extract a single forecast field from HA Forecast mapping/object."""
        attr_map = {
            "precipitation": ["precipitation", "native_precipitation"],
            "temperature": ["temperature", "native_temperature"],
            "templow": ["templow", "native_temp_low"],
            "wind_speed": ["wind_speed", "native_wind_speed"],
            "wind_bearing": ["wind_bearing"],
            "datetime": ["datetime"],
            "condition": ["condition"],
            "precipitation_probability": ["precipitation_probability"],
        }
        candidates = attr_map.get(self._sensor_type, [self._sensor_type])
        if isinstance(forecast, dict):
            for name in candidates:
                if name in forecast and forecast.get(name) is not None:
                    return forecast.get(name)
            return None
        for name in candidates:
            value = getattr(forecast, name, None)
            if value is not None:
                return value
        return None

    @property
    def state(self):
        """Return the state of the device."""
        forecasts = self._weather_coordinator.data.get(self._forecast_key())
        if forecasts:
            return self._extract_value(forecasts[0])
        return None
