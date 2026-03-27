"""Weather data coordinator for the OpenCWB (OCWB) service."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

import async_timeout
import requests
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


class ObservationFallbackCurrent:
    """Minimal current-weather object for pressure/wind/UV fallback."""

    def __init__(self, pressure=None, wind_deg=None, wind_speed=None, uvi=None):
        self.pressure = {"press": pressure, "sea_level": None} if pressure is not None else None
        self._wind = {"deg": wind_deg, "speed": wind_speed, "gust": None}
        self.uvi = uvi

    def wind(self):
        return self._wind


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
            interval = self.forecast_mode.split("_")[1]
            current_weather = await self.hass.async_add_executor_job(
                self._ocwb_client.one_call,
                self._latitude,
                self._longitude,
                self._location_name,
                interval,
            )
            legacy_weather = await self.hass.async_add_executor_job(
                self._get_legacy_weather_and_forecast,
                interval,
            )
            if interval == "hourly":
                return HybridWeather(
                    current=current_weather.current,
                    legacy_current=legacy_weather.current,
                    fallback_current=legacy_weather.fallback_current,
                    forecast_hourly=legacy_weather.forecast,
                )
            return HybridWeather(
                current=current_weather.current,
                legacy_current=legacy_weather.current,
                fallback_current=legacy_weather.fallback_current,
                forecast_daily=legacy_weather.forecast,
            )
        weather = await self.hass.async_add_executor_job(
            self._get_legacy_weather_and_forecast
        )
        return weather

    def _fetch_observation_fallback_current(self):
        """Fetch nearest-station observation data directly for pressure fallback."""
        cfg = getattr(self._ocwb_client.http_client, "config", {}) or {}
        timeout = cfg.get("connection", {}).get("timeout_secs", 15)
        verify = cfg.get("connection", {}).get("verify_ssl_certs", False)
        proxies_cfg = cfg.get("proxies") or {}
        proxies = {
            k: v
            for k, v in proxies_cfg.items()
            if v and "host:port" not in v and "user:pass" not in v
        } or None
        url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001"
        session = requests.Session()
        session.trust_env = False
        resp = session.get(
            url,
            params={
                "Authorization": self._ocwb_client.API_key,
                "format": "JSON",
                "lon": self._longitude,
                "lat": self._latitude,
            },
            timeout=timeout,
            verify=verify,
            proxies=proxies,
        )
        resp.raise_for_status()
        data = resp.json()
        stations = data.get("records", {}).get("Station", [])
        if not stations:
            raise APIRequestError("observation fallback returned 0 stations")

        def _station_wgs84(station):
            coords = station.get("GeoInfo", {}).get("Coordinates", [])
            for c in coords:
                if c.get("CoordinateName") == "WGS84":
                    return float(c.get("StationLatitude")), float(c.get("StationLongitude"))
            first = coords[0]
            return float(first.get("StationLatitude")), float(first.get("StationLongitude"))

        nearest = min(
            stations,
            key=lambda s: (
                (_station_wgs84(s)[0] - self._latitude) ** 2
                + (_station_wgs84(s)[1] - self._longitude) ** 2
            ),
        )
        elem = nearest.get("WeatherElement", {})
        pressure = elem.get("AirPressure")
        wind_deg = elem.get("WindDirection")
        wind_speed = elem.get("WindSpeed")
        uvi = elem.get("UVIndex")

        def _clean_num(v):
            if v in (None, ""):
                return None
            num = float(v)
            return None if num <= -90 else num
        current = ObservationFallbackCurrent(
            pressure=_clean_num(pressure),
            wind_deg=_clean_num(wind_deg),
            wind_speed=_clean_num(wind_speed),
            uvi=_clean_num(uvi),
        )
        return current

    def _get_legacy_weather_and_forecast(self, interval: str | None = None):
        """Get weather and forecast data using the legacy API."""
        if interval is None:
            interval = "hourly" if self.forecast_mode == FORECAST_MODE_HOURLY else "daily"
        weather = self._ocwb_client.weather_at_place(self._location_name, interval)
        forecast = self._ocwb_client.forecast_at_place(
            self._location_name, interval, self._forecast_limit
        )
        observation_current = None
        try:
            observation_current = self._fetch_observation_fallback_current()
        except Exception as exc:
            _LOGGER.warning("OpenCWB observation fallback failed: %s", exc)
            observation_current = None
        return LegacyWeather(weather.weather, forecast.forecast.weathers, observation_current)

    def _convert_weather_response(self, weather_response) -> dict[str, Any]:
        """Convert OpenCWB API response to HA weather entity format."""
        current = weather_response.current
        legacy_current = getattr(weather_response, "legacy_current", None)
        fallback_current = getattr(weather_response, "fallback_current", None)
        pressure = self._extract_pressure(current, legacy_current, fallback_current)
        wind_bearing = self._extract_wind_bearing(current, legacy_current, fallback_current)

        if pressure is None:
            _LOGGER.warning(
                "OpenCWB pressure missing after fallback: current=%s legacy=%s fallback=%s fallback_type=%s",
                getattr(current, "pressure", None),
                getattr(legacy_current, "pressure", None) if legacy_current is not None else None,
                getattr(fallback_current, "pressure", None) if fallback_current is not None else None,
                type(fallback_current).__name__ if fallback_current is not None else None,
            )

        return {
            ATTR_API_TEMPERATURE: current.temperature("celsius").get("temp"),
            ATTR_API_FEELS_LIKE_TEMPERATURE: current.temperature(
                "celsius"
            ).get("feels_like"),
            ATTR_API_DEW_POINT: self._fmt_dewpoint(current.dewpoint),
            ATTR_API_PRESSURE: pressure,
            ATTR_API_HUMIDITY: current.humidity,
            ATTR_API_WIND_BEARING: wind_bearing,
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
        # One Call stores hourly and daily separately.
        if self.forecast_mode == FORECAST_MODE_ONECALL_HOURLY:
            return list(weather_response.forecast_hourly) if forecast_type == "hourly" else []
        if self.forecast_mode == FORECAST_MODE_ONECALL_DAILY:
            return list(weather_response.forecast_daily) if forecast_type == "daily" else []

        # Legacy API returns one forecast collection according to selected mode.
        return list(weather_response.forecast)

    def _convert_forecast_entry(self, entry) -> Forecast | None:
        """Convert a single raw forecast entry into a Forecast dataclass."""
        try:
            rain = getattr(entry, "rain", None)
            snow = getattr(entry, "snow", None)
            precip = self._calc_precipitation(rain, snow)

            precip_prob_raw = getattr(entry, "precipitation_probability", None)
            precip_prob = (
                round(precip_prob_raw * 100)
                if precip_prob_raw is not None
                else None
            )

            wind_dict = entry.wind() if hasattr(entry, "wind") else {}
            wind_speed = wind_dict.get("speed") if isinstance(wind_dict, dict) else None
            wind_bearing = self._normalize_wind_bearing(
                wind_dict.get("deg") if isinstance(wind_dict, dict) else None
            )
            wind_gust = wind_dict.get("gust") if isinstance(wind_dict, dict) else None

            clouds = getattr(entry, "clouds", None)
            humidity = getattr(entry, "humidity", None)

            temp_dict = entry.temperature("celsius") if hasattr(entry, "temperature") else {}
            temp_dict = temp_dict or {}
            feels_like = temp_dict.get("feels_like")
            temp_high = temp_dict.get("max") or temp_dict.get("temp_max")
            temp_low = temp_dict.get("min") or temp_dict.get("temp_min")
            temp = temp_dict.get("temp") or temp_high

            pressure_dict = getattr(entry, "pressure", None) or {}
            pressure = pressure_dict.get("press") if isinstance(pressure_dict, dict) else None

            ref_ts = entry.reference_time("unix") if hasattr(entry, "reference_time") else None
            if ref_ts is None:
                return None
            fc_time = dt.utc_from_timestamp(ref_ts)

            return Forecast(
                datetime=fc_time,
                native_precipitation=precip,
                precipitation_probability=precip_prob,
                native_temperature=temp,
                native_temp_low=temp_low,
                native_dew_point=None,
                cloud_coverage=clouds,
                condition=self._get_condition(getattr(entry, "weather_code", None), ref_ts),
                humidity=humidity,
                native_apparent_temperature=feels_like,
                native_pressure=pressure,
                native_wind_gust_speed=wind_gust,
                native_wind_speed=wind_speed,
                wind_bearing=wind_bearing,
            )
        except Exception:  # noqa: BLE001 – defensive; skip malformed entries
            return None

    @staticmethod
    def _extract_pressure(current, legacy_current=None, fallback_current=None) -> float | None:
        """Return current pressure, falling back to legacy/observation current when omitted."""
        for candidate in (current, legacy_current, fallback_current):
            pressure_dict = getattr(candidate, "pressure", None) or {}
            if isinstance(pressure_dict, dict):
                pressure = pressure_dict.get("press")
                if pressure is not None:
                    return pressure
        return None

    def _extract_wind_bearing(self, current, legacy_current=None, fallback_current=None):
        """Return the first usable wind bearing across current fallbacks."""
        for candidate in (current, legacy_current, fallback_current):
            if candidate is None:
                continue
            try:
                value = candidate.wind().get("deg")
            except Exception:
                value = None
            normalized = self._normalize_wind_bearing(value)
            if normalized is not None:
                return normalized
        return None

    @staticmethod
    def _normalize_wind_bearing(value) -> float | str | None:
        """Normalize wind bearing to HA-supported degrees or 1-3 letter cardinals."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return float(text)
            except ValueError:
                pass
            mapping = {
                "北風": "N",
                "偏北風": "N",
                "北北東風": "NNE",
                "東北風": "NE",
                "東北東風": "ENE",
                "東風": "E",
                "偏東風": "E",
                "東南東風": "ESE",
                "東南風": "SE",
                "南南東風": "SSE",
                "南風": "S",
                "偏南風": "S",
                "南南西風": "SSW",
                "西南風": "SW",
                "西南西風": "WSW",
                "西風": "W",
                "偏西風": "W",
                "西北西風": "WNW",
                "西北風": "NW",
                "北北西風": "NNW",
                "偏東北風": "NE",
                "偏東南風": "SE",
                "偏西南風": "SW",
                "偏西北風": "NW",
            }
            return mapping.get(text, text if len(text) <= 3 and text.isalpha() else None)
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
    """Harmonize weather data model for legacy API."""

    def __init__(self, current_weather, forecast, fallback_current=None) -> None:
        """Initialize with raw API weather and forecast objects."""
        self.current = current_weather
        self.forecast = forecast
        self.fallback_current = fallback_current


class HybridWeather:
    """Use onecall current weather plus legacy district-level forecast."""

    def __init__(self, current, legacy_current=None, fallback_current=None, forecast_hourly=None, forecast_daily=None) -> None:
        self.current = current
        self.legacy_current = legacy_current
        self.fallback_current = fallback_current
        self.forecast_hourly = forecast_hourly
        self.forecast_daily = forecast_daily
