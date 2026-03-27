"""Support for the OpenCWB (OCWB) service."""
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.weather import Forecast, WeatherEntityFeature, SingleCoordinatorWeatherEntity
from homeassistant.const import UnitOfLength, UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_API_CLOUDS,
    ATTR_API_CONDITION,
    ATTR_API_DEW_POINT,
    ATTR_API_FEELS_LIKE_TEMPERATURE,
    ATTR_API_FORECAST_DAILY,
    ATTR_API_FORECAST_HOURLY,
    ATTR_API_HUMIDITY,
    ATTR_API_PRESSURE,
    ATTR_API_RAIN,
    ATTR_API_SNOW,
    ATTR_API_TEMPERATURE,
    ATTR_API_UV_INDEX,
    ATTR_API_WIND_BEARING,
    ATTR_API_WIND_GUST,
    ATTR_API_WIND_SPEED,
    ATTRIBUTION,
    CONF_LOCATION_NAME,
    DEFAULT_NAME,
    DOMAIN,
    ENTRY_NAME,
    ENTRY_WEATHER_COORDINATOR,
    FORECAST_MODE_DAILY,
    FORECAST_MODE_HOURLY,
    FORECAST_MODE_ONECALL_DAILY,
    FORECAST_MODE_ONECALL_HOURLY,
    MANUFACTURER,
)
from .weather_update_coordinator import WeatherUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OpenCWB weather entity based on a config entry."""
    domain_data = hass.data[DOMAIN][config_entry.entry_id]
    name = domain_data[ENTRY_NAME]
    weather_coordinator = domain_data[ENTRY_WEATHER_COORDINATOR]
    location_name = domain_data[CONF_LOCATION_NAME]

    unique_id = f"{config_entry.unique_id}"
    ocwb_weather = OpenCWBWeather(
        f"{name} {location_name}",
        f"{unique_id}-{location_name}",
        weather_coordinator,
    )

    async_add_entities([ocwb_weather], False)


class OpenCWBWeather(SingleCoordinatorWeatherEntity[WeatherUpdateCoordinator]):
    """Implementation of an OpenCWB weather entity."""

    _attr_attribution = ATTRIBUTION
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_precipitation_unit = UnitOfLength.MILLIMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND

    def __init__(
        self,
        name: str,
        unique_id: str,
        weather_coordinator: WeatherUpdateCoordinator,
    ) -> None:
        """Initialize the weather entity."""
        super().__init__(weather_coordinator)
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._weather_coordinator = weather_coordinator

        split_unique_id = unique_id.split("-")
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, f"{split_unique_id[0]}-{split_unique_id[1]}")},
            manufacturer=MANUFACTURER,
            name=DEFAULT_NAME,
        )

        mode = weather_coordinator.forecast_mode
        if mode in (FORECAST_MODE_DAILY, FORECAST_MODE_ONECALL_DAILY):
            self._attr_supported_features = WeatherEntityFeature.FORECAST_DAILY
        elif mode in (FORECAST_MODE_HOURLY, FORECAST_MODE_ONECALL_HOURLY):
            self._attr_supported_features = WeatherEntityFeature.FORECAST_HOURLY
        else:
            # Default to daily; One Call 2.5 supports both
            self._attr_supported_features = (
                WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
            )

    @property
    def should_poll(self) -> bool:
        """Return False; updates are driven by the coordinator."""
        return False

    @property
    def condition(self) -> str | None:
        """Return the current weather condition."""
        return self._weather_coordinator.data.get(ATTR_API_CONDITION)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._weather_coordinator.last_update_success

    async def async_added_to_hass(self) -> None:
        """Connect to dispatcher listening for entity data notifications."""
        self.async_on_remove(
            self._weather_coordinator.async_add_listener(
                self.async_write_ha_state
            )
        )

    # ── HA spec required / recommended properties ────────────────────────

    @property
    def cloud_coverage(self) -> float | None:
        """Return the cloud coverage in percent."""
        return self._weather_coordinator.data.get(ATTR_API_CLOUDS)

    @property
    def native_apparent_temperature(self) -> float | None:
        """Return the apparent temperature."""
        return self._weather_coordinator.data.get(ATTR_API_FEELS_LIKE_TEMPERATURE)

    @property
    def native_temperature(self) -> float | None:
        """Return the temperature."""
        return self._weather_coordinator.data.get(ATTR_API_TEMPERATURE)

    @property
    def native_dew_point(self) -> float | None:
        """Return the dew point temperature."""
        return self._weather_coordinator.data.get(ATTR_API_DEW_POINT)

    @property
    def humidity(self) -> float | None:
        """Return the humidity in percent."""
        return self._weather_coordinator.data.get(ATTR_API_HUMIDITY)

    @property
    def native_pressure(self) -> float | None:
        """Return the pressure."""
        return self._weather_coordinator.data.get(ATTR_API_PRESSURE)

    @property
    def native_precipitation(self) -> float | None:
        """Return the total precipitation amount (rain + snow) in mm."""
        return self._weather_coordinator.data.get(ATTR_API_RAIN)

    @property
    def native_rain(self) -> float | None:
        """Return the rain amount in mm."""
        return self._weather_coordinator.data.get(ATTR_API_RAIN)

    @property
    def native_snow(self) -> float | None:
        """Return the snow amount in mm."""
        return self._weather_coordinator.data.get(ATTR_API_SNOW)

    @property
    def native_uv_index(self) -> float | None:
        """Return the UV index."""
        return self._weather_coordinator.data.get(ATTR_API_UV_INDEX)

    @property
    def native_wind_gust_speed(self) -> float | None:
        """Return the wind gust speed."""
        return self._weather_coordinator.data.get(ATTR_API_WIND_GUST)

    @property
    def native_wind_speed(self) -> float | None:
        """Return the wind speed."""
        return self._weather_coordinator.data.get(ATTR_API_WIND_SPEED)

    @property
    def wind_bearing(self) -> float | str | None:
        """Return the wind bearing in degrees."""
        return self._weather_coordinator.data.get(ATTR_API_WIND_BEARING)

    @property
    def extra_state_attributes(self):
        """Return temporary debug attributes for runtime diagnosis."""
        data = self._weather_coordinator.data or {}
        return {
            "debug_pressure_current": data.get("debug_pressure_current"),
            "debug_pressure_legacy": data.get("debug_pressure_legacy"),
            "debug_pressure_fallback": data.get("debug_pressure_fallback"),
            "debug_pressure_resolved": data.get("debug_pressure_resolved"),
        }

    # ── Forecast (HA spec requires _async_forecast_daily / _async_forecast_hourly) ──

    @property
    def forecast(self) -> list[Forecast] | None:
        """Return the default forecast (daily). DEPRECATED – use _async_forecast_* methods."""
        return self._async_forecast_daily()

    @callback
    def _async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast in native units."""
        return self._weather_coordinator.data.get(ATTR_API_FORECAST_DAILY)

    @callback
    def _async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the hourly forecast in native units."""
        return self._weather_coordinator.data.get(ATTR_API_FORECAST_HOURLY)
