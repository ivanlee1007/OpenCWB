"""Warning data coordinator for OpenCWB / CWA warning datasets."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ATTR_TROPICAL_CYCLONE,
    ATTR_TYPHOON_WARNING,
    ATTR_TYPHOON_WARNING_STATUS,
    ATTR_WEATHER_ALERT,
    ATTR_WEATHER_ALERTS,
)
from .core.weatherapi12.warning_client import WarningClient
from .core.weatherapi12.typhoon_risk import apply_typhoon_risk

_LOGGER = logging.getLogger(__name__)

WARNING_UPDATE_INTERVAL = timedelta(minutes=15)


class WarningUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and normalize CWA typhoon and hazardous-weather warning data."""

    def __init__(
        self,
        ocwb_weather_manager,
        location_name: str,
        location_latitude: float,
        location_longitude: float,
        hass,
        *,
        enable_typhoon_warning: bool = False,
        enable_tropical_cyclone_track: bool = False,
        enable_weather_alerts: bool = False,
    ) -> None:
        self._ocwb_client = ocwb_weather_manager
        self._location_name = location_name
        self._location_latitude = location_latitude
        self._location_longitude = location_longitude
        self.enable_typhoon_warning = enable_typhoon_warning
        self.enable_tropical_cyclone_track = enable_tropical_cyclone_track
        self.enable_weather_alerts = enable_weather_alerts
        self._warning_client = WarningClient(
            ocwb_weather_manager.API_key,
            getattr(ocwb_weather_manager.http_client, "config", {}) or {},
        )
        super().__init__(
            hass,
            _LOGGER,
            name="opencwb_warning",
            update_interval=WARNING_UPDATE_INTERVAL,
        )

    @property
    def any_enabled(self) -> bool:
        """Return True if any warning feature is enabled."""
        return any((
            self.enable_typhoon_warning,
            self.enable_tropical_cyclone_track,
            self.enable_weather_alerts,
        ))

    def _location_candidates(self) -> list[str]:
        candidates = [self._location_name]
        try:
            city_name = self._ocwb_client.one_call_city_name(self._location_name)
            if city_name and city_name not in candidates:
                candidates.append(city_name)
        except Exception as exc:  # pragma: no cover - defensive around legacy mapping
            _LOGGER.debug("OpenCWB warning location mapping failed: %s", exc)
        return [candidate for candidate in candidates if candidate]

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch enabled warning datasets.

        Warning feeds should not make the whole weather integration unavailable when a
        specific optional feed is temporarily empty or unavailable; failures are logged
        and represented as inactive/empty data for that feed.
        """
        data: dict[str, Any] = {}
        if self.enable_typhoon_warning:
            data[ATTR_TYPHOON_WARNING_STATUS] = await self._safe_executor(
                self._warning_client.typhoon_warning,
                {"active": False, "affected_areas": [], "typhoon": {}, "error": None},
                "typhoon warning",
            )
            data[ATTR_TYPHOON_WARNING] = bool(
                data[ATTR_TYPHOON_WARNING_STATUS].get("active")
            )

        if self.enable_tropical_cyclone_track:
            data[ATTR_TROPICAL_CYCLONE] = await self._safe_executor(
                self._warning_client.tropical_cyclone_track,
                {"count": 0, "cyclones": [], "error": None},
                "tropical cyclone track",
            )

        if self.enable_typhoon_warning or self.enable_tropical_cyclone_track:
            track_data, warning_data = apply_typhoon_risk(
                data.get(ATTR_TROPICAL_CYCLONE, {"count": 0, "cyclones": []}),
                data.get(ATTR_TYPHOON_WARNING_STATUS, {"active": False}),
                location_latitude=self._location_latitude,
                location_longitude=self._location_longitude,
            )
            if self.enable_tropical_cyclone_track:
                data[ATTR_TROPICAL_CYCLONE] = track_data
            if self.enable_typhoon_warning:
                data[ATTR_TYPHOON_WARNING_STATUS] = warning_data

        if self.enable_weather_alerts:
            data[ATTR_WEATHER_ALERTS] = await self._safe_executor(
                self._warning_client.weather_alerts,
                {
                    "count": 0,
                    "active_for_location": False,
                    "matched_locations": [],
                    "unmatched_special_areas": [],
                    "match_method": None,
                    "alerts": [],
                    "error": None,
                },
                "weather alerts",
                self._location_candidates(),
            )
            data[ATTR_WEATHER_ALERT] = bool(
                data[ATTR_WEATHER_ALERTS].get("active_for_location")
            )
        return data

    async def _safe_executor(self, func, fallback: dict[str, Any], label: str, *args):
        try:
            return await self.hass.async_add_executor_job(func, *args)
        except Exception as exc:  # keep optional warning feeds non-fatal
            _LOGGER.warning("OpenCWB %s fetch failed: %s", label, exc)
            value = dict(fallback)
            value["error"] = str(exc)
            return value
