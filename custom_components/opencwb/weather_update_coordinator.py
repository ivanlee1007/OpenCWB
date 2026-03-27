"""Weather data coordinator for the OpenCWB (OCWB) service."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

import async_timeout
from .core.commons.exceptions import APIRequestError, UnauthorizedError

from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_SUNNY,
    Forecast,
)
from homeassistant.const import UnitOfSpeed, UnitOfTemperature
from homeassistant.helpers import sun
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt

from .const import (
    ATTR_API_CLOUDS,
    ATTR_API_CONDITION,
    ATTR_API_DEW_POINT,
    ATTR_API_FEELS_LIKE_TEMPERATURE,
    ATTR_API_FORECAST,
    ATTR_API_HUMIDITY,
    ATTR_API_PRECIPITATION_KIND,
    ATTR_API_PRESSURE,
    ATTR_API_RAIN,
    ATTR_API_SNOW,
    ATTR_API_TEMPERATURE,
    ATTR_API_UV_INDEX,
    ATTR_API_WEATHER,
    ATTR_API_WEATHER_CODE,
    ATTR_API_WIND_BEARING,
    ATTR_API_WIND_GUST,
    ATTR_API_WIND_SPEED,
    CONDITION_CLASSES,
    DOMAIN,
    FORECAST_MODE_DAILY,
    FORECAST_MODE_HOURLY,
    FORECAST_MODE_ONECALL_DAILY,
    FORECAST_MODE_ONECALL_HOURLY,
    WEATHER_CODE_SUNNY_OR_CLEAR_NIGHT,
)

_LOGGER = logging.getLogger(__name__)

WEATHER_UPDATE_INTERVAL = timedelta(minutes=15)


class WeatherUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Weather data update coordinator for OpenCWB."""

    def __init__(
        self,
        ocwb,
        location_name: str,
        latitude: float,
        longitude: float,
        forecast_mode: str,
        hass,
    ) -> None:
        """Initialize the coordinator."""
        self._ocwb_client = ocwb
        self._location_name = location_name
        self._latitude = latitude
        self._longitude = longitude
        self.forecast_mode = forecast_mode
        self._forecast_limit: int | None = None

        if forecast_mode == FORECAST_MODE_DAILY:
            self._forecast_limit = 15

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=WEATHER_UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch weather data from OpenCWB API."""
        data: dict[str, Any] = {}
        try:
            weather_response = await self._get_ocwb_weather()
            data = self._convert_weather_response(weather_response)
        except (APIRequestError, UnauthorizedError) as error:
            raise UpdateFailed(error) from error
        return data

    async def _get_ocwb_weather(self):
        """Poll weather data from OpenData CWB."""
        if self.forecast_mode in (
            FORECAST_MODE_ONECALL_HOURLY,
            FORECAST_MODE_ONECALL_DAILY,
        ):
            weather = await self.hass.async_add_executor_job(
                self._ocwb_client.one_call,
                self._latitude,
                self._longitude,
                self._location_name,
                self.forecast_mode.split("_")[1],
            )
        else:
            weather = await self.hass.async_add_executor_job(
                self._get_legacy_weather_and_forecast
            )
        return weather

    def _get_legacy_weather_and_forecast(self):
        """Get weather and forecast data using the legacy API."""
        interval = "hourly" if self.forecast_mode == FORECAST_MODE_HOURLY else "daily"
        weather = self._ocwb_client.weather_at_place(self._location_name, interval)
        forecast = self._ocwb_client.forecast_at_place(
            self._location_name, interval, self._forecast_limit
        )
        return LegacyWeather(weather.weather, forecast.forecast.weathers)

    def _convert_weather_response(self, weather_response) -> dict[str, Any]:
        """Convert OpenCWB API response to HA weather entity format."""
        current = weather_response.current

        return {
            ATTR_API_TEMPERATURE: current.temperature("celsius").get("temp"),
            ATTR_API_FEELS_LIKE_TEMPERATURE: current.temperature(
                "celsius"
            ).get("feels_like"),
            ATTR_API_DEW_POINT: self._fmt_dewpoint(current.dewpoint),
            ATTR_API_PRESSURE: current.pressure.get("press"),
            ATTR_API_HUMIDITY: current.humidity,
            ATTR_API_WIND_BEARING: current.wind().get("deg"),
            ATTR_API_WIND_GUST: current.wind().get("gust"),
            ATTR_API_WIND_SPEED: current.wind().get("speed"),
            ATTR_API_CLOUDS: current.clouds,
            ATTR_API_RAIN: self._get_rain(current.rain),
            ATTR_API_SNOW: self._get_snow(current.snow),
            ATTR_API_PRECIPITATION_KIND: self._calc_precipitation_kind(
                current.rain, current.snow
            ),
            ATTR_API_WEATHER: current.detailed_status,
            ATTR_API_CONDITION: self._get_condition(current.weather_code),
            ATTR_API_UV_INDEX: getattr(current, "uvi", None),
            ATTR_API_WEATHER_CODE: current.weather_code,
            # Store daily and hourly forecasts separately as list[Forecast]
            "forecast_daily": self._build_forecast(weather_response, "daily"),
            "forecast_hourly": self._build_forecast(weather_response, "hourly"),
        }

    def _build_forecast(
        self, weather_response, forecast_type: str
    ) -> list[Forecast] | None:
        """Build a list of Forecast dataclass instances from API response."""
        try:
            raw: list = self._get_raw_forecast(weather_response, forecast_type)
        except Exception:  # noqa: BLE001 – defensive; API may omit some fields
            return None

        result: list[Forecast] = []
        for entry in raw:
            fc = self._convert_forecast_entry(entry)
            if fc is not None:
                result.append(fc)

        return result if result else None

    def _get_raw_forecast(
        self, weather_response, forecast_type: str
    ) -> list:
        """Return the raw forecast list for the given type from API response."""
        # One Call 2.5 stores hourly and daily separately
        if self.forecast_mode == FORECAST_MODE_ONECALL_HOURLY:
            return list(weather_response.forecast_hourly)
        if self.forecast_mode == FORECAST_MODE_ONECALL_DAILY:
            return list(weather_response.forecast_daily)

        # Legacy API – interval determines which forecast we get
        if forecast_type == "hourly":
            return list(weather_response.forecast)
        # Legacy daily or freedaily
        return list(weather_response.forecast)

    def _convert_forecast_entry(self, entry) -> Forecast | None:
        """Convert a single raw forecast entry into a Forecast dataclass."""
        try:
            precip = self._calc_precipitation(entry.rain, entry.snow)
            precip_prob = round(entry.precipitation_probability * 100)
            wind_speed = entry.wind().get("speed")
            wind_bearing = entry.wind().get("deg")
            clouds = getattr(entry, "clouds", None)
            feels_like = entry.temperature("celsius").get("feels_like")
            humidity = getattr(entry, "humidity", None)

            temp_dict = entry.temperature("celsius")
            temp_high = temp_dict.get("max") or temp_dict.get("temp_max")
            temp_low = temp_dict.get("min") or temp_dict.get("temp_min")
            temp = temp_dict.get("temp") or temp_high

            pressure = entry.pressure.get("press") if entry.pressure else None
            wind_gust = getattr(entry, "wind_gust", None)

            # Reference time as datetime
            ref_ts = entry.reference_time("unix")
            fc_time = dt.utc_from_timestamp(ref_ts)

            return Forecast(
                datetime=fc_time,
                native_precipitation=precip,
                precipitation_probability=precip_prob,
                native_temperature=temp,
                native_temp_low=temp_low,
                native_dew_point=None,
                cloud_coverage=clouds,
                condition=self._get_condition(
                    entry.weather_code, ref_ts
                ),
                humidity=humidity,
                native_apparent_temperature=feels_like,
                native_pressure=pressure,
                native_wind_gust_speed=wind_gust,
                native_wind_speed=wind_speed,
                wind_bearing=wind_bearing,
            )
        except Exception:  # noqa: BLE001 – defensive; skip malformed entries
            return None

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _fmt_dewpoint(dewpoint) -> float | None:
        """Format dewpoint from API units (×100) to °C."""
        if dewpoint is not None:
            return round(dewpoint / 100, 1)
        return None

    @staticmethod
    def _get_rain(rain) -> float:
        """Return rain amount in mm."""
        if not rain:
            return 0.0
        if "all" in rain:
            return round(float(rain["all"]), 2)
        if "1h" in rain:
            return round(float(rain["1h"]), 2)
        return 0.0

    @staticmethod
    def _get_snow(snow) -> float:
        """Return snow amount in mm."""
        if not snow:
            return 0.0
        if "all" in snow:
            return round(float(snow["all"]), 2)
        if "1h" in snow:
            return round(float(snow["1h"]), 2)
        return 0.0

    @staticmethod
    def _calc_precipitation(rain, snow) -> float:
        """Calculate total precipitation (rain + snow) in mm."""
        return round(WeatherUpdateCoordinator._get_rain(rain)
                      + WeatherUpdateCoordinator._get_snow(snow), 2)

    @staticmethod
    def _calc_precipitation_kind(rain, snow) -> str:
        """Determine the precipitation kind string."""
        has_rain = WeatherUpdateCoordinator._get_rain(rain) > 0
        has_snow = WeatherUpdateCoordinator._get_snow(snow) > 0
        if has_rain and has_snow:
            return "Snow and Rain"
        if has_rain:
            return "Rain"
        if has_snow:
            return "Snow"
        return "None"

    def _get_condition(self, weather_code, timestamp=None) -> str:
        """Map CWB weather code to HA weather condition string."""
        if weather_code == WEATHER_CODE_SUNNY_OR_CLEAR_NIGHT:
            ts = dt.utc_from_timestamp(timestamp) if timestamp else None
            if sun.is_up(self.hass, ts):
                return ATTR_CONDITION_SUNNY
            return ATTR_CONDITION_CLEAR_NIGHT

        for condition, codes in CONDITION_CLASSES.items():
            if weather_code in codes:
                return condition
        return "exceptional"


class LegacyWeather:
    """Harmonize weather data model for legacy and One Call APIs."""

    def __init__(self, current_weather, forecast) -> None:
        """Initialize with raw API weather and forecast objects."""
        self.current = current_weather
        self.forecast = forecast
