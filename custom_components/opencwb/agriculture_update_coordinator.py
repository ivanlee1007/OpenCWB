"""Optional multi-crop agricultural advisory coordinator for OpenCWA."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Mapping

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ATTR_AGRICULTURE,
    ATTR_AGRICULTURE_ADVISORY,
    ATTR_AGRICULTURE_ET0,
    ATTR_AGRICULTURE_ETC,
    ATTR_AGRICULTURE_KC,
    ATTR_AGRICULTURE_NOTIFICATION,
    ATTR_AGRICULTURE_SUPPORTED,
    ATTR_AGRICULTURE_WARNING,
    ATTR_AGRICULTURE_WATER_REQUIREMENT,
    CONF_AREA_HECTARES,
    CONF_CROP_NAME,
    CONF_GROWTH_STAGE,
    CONF_PLANTING_DATE,
)
from .core.agriculture.kcg_client import KCGOpenDataClient
from .core.agriculture.kcg_parser import (
    build_agriculture_notification,
    build_agriculture_snapshot,
    is_successful_agriculture_cache,
)

_LOGGER = logging.getLogger(__name__)
AGRICULTURE_UPDATE_INTERVAL = timedelta(minutes=30)


class AgricultureUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch shared provider data and build an isolated snapshot per crop."""

    def __init__(
        self,
        weather_manager,
        location_name: str,
        latitude: float,
        longitude: float,
        hass,
        *,
        token: str | None = None,
        crop_profiles: Mapping[str, Mapping[str, Any]],
        client: KCGOpenDataClient | None = None,
    ) -> None:
        self.location_name = location_name
        self.latitude = latitude
        self.longitude = longitude
        self.crop_profiles = {
            str(profile_id): dict(profile)
            for profile_id, profile in crop_profiles.items()
        }
        self.client = client or KCGOpenDataClient(token=token)
        self.city = self._resolve_city(weather_manager, location_name)
        super().__init__(
            hass,
            _LOGGER,
            name="opencwb_agriculture",
            update_interval=AGRICULTURE_UPDATE_INTERVAL,
        )
        self.data = {
            profile_id: self._fallback()
            for profile_id in self.crop_profiles
        }

    @staticmethod
    def _resolve_city(weather_manager, location_name: str) -> str:
        try:
            return weather_manager.one_call_city_name(location_name) or location_name
        except Exception:  # defensive around the legacy location registry
            return location_name

    @staticmethod
    def _fallback(
        error: Exception | str | None = None,
        previous: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        previous_snapshot = previous.get(ATTR_AGRICULTURE) if previous else None
        if is_successful_agriculture_cache(previous_snapshot):
            snapshot = dict(previous[ATTR_AGRICULTURE])
            snapshot.update({
                "status": "stale",
                "stale": True,
                "provider_available": False,
                "error": "Agricultural provider update failed",
                "error_code": getattr(error, "code", type(error).__name__)
                if isinstance(error, Exception)
                else "provider_error",
            })
            irrigation = dict(previous.get("agriculture_irrigation") or {})
            irrigation.update({
                "available": False,
                "stale": True,
                "error": "Agricultural provider update failed",
            })
            return AgricultureUpdateCoordinator._compose(snapshot, irrigation)
        snapshot = {
            "status": "unavailable",
            "provider_available": False,
            "supported": None,
            "warning_active": False,
            "advisory_active": False,
            "warning_count": 0,
            "advisory_count": 0,
            "items": [],
            "rules": [],
            "source_timestamp": None,
            "stale": False,
            "error": "Agricultural provider update failed" if error else None,
            "error_code": getattr(error, "code", type(error).__name__)
            if isinstance(error, Exception)
            else None,
            "source_provider": "高雄農來訊",
            "official_cwa_alert": False,
            "derived_by_opencwa": False,
        }
        irrigation = {
            "available": False,
            "et0": None,
            "kc": None,
            "etc": None,
            "water_requirement": None,
            "crop_water_supported": False,
        }
        return AgricultureUpdateCoordinator._compose(snapshot, irrigation)

    @staticmethod
    def _compose(snapshot: dict[str, Any], irrigation: dict[str, Any]):
        try:
            notification = build_agriculture_notification(snapshot)
        except Exception:
            notification = "農業通知目前無法產生；請直接檢查各作物狀態。"
        entity_snapshot = dict(snapshot)
        entity_snapshot.pop("_notification_item", None)
        return {
            ATTR_AGRICULTURE: entity_snapshot,
            ATTR_AGRICULTURE_NOTIFICATION: notification,
            ATTR_AGRICULTURE_WARNING: bool(snapshot.get("warning_active")),
            ATTR_AGRICULTURE_ADVISORY: bool(snapshot.get("advisory_active")),
            ATTR_AGRICULTURE_SUPPORTED: snapshot.get("supported"),
            ATTR_AGRICULTURE_ET0: irrigation.get("et0"),
            ATTR_AGRICULTURE_KC: irrigation.get("kc"),
            ATTR_AGRICULTURE_ETC: irrigation.get("etc"),
            ATTR_AGRICULTURE_WATER_REQUIREMENT: irrigation.get("water_requirement"),
            "agriculture_irrigation": irrigation,
        }

    @staticmethod
    def _matched_rules(rules: list[dict[str, Any]], crop: str) -> list[dict[str, Any]]:
        return [
            {
                "crop": row.get("C_NAME"),
                "disaster": row.get("Disaster"),
                "growth": row.get("GROWTH"),
                "stage": row.get("STAGE"),
                "duration": row.get("DURATION"),
                "threshold": row.get("THRESHOLD"),
                "measures": row.get("MEASURES"),
                "effect": row.get("EFFECT"),
                "prevention": row.get("PREVENTION"),
                "recovery": row.get("RECOVERY"),
            }
            for row in rules
            if str(row.get("C_NAME", "")).strip() == crop
        ]

    def _build_snapshot(
        self,
        profile_id: str,
        profile: Mapping[str, Any],
        rows: list[dict[str, Any]],
        supported_crops: set[str],
        rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        crop = profile[CONF_CROP_NAME]
        snapshot = build_agriculture_snapshot(
            rows,
            city=self.city,
            town=self.location_name if self.location_name != self.city else None,
            crop=crop,
            growth_stage=profile.get(CONF_GROWTH_STAGE),
            supported_crops=supported_crops,
        )
        matched_rules = self._matched_rules(rules, crop)
        snapshot.update({
            "profile_id": profile_id,
            "crop_name": crop,
            "growth_stage": profile.get(CONF_GROWTH_STAGE) or None,
            "planting_date": profile.get(CONF_PLANTING_DATE) or None,
            "area_hectares": profile.get(CONF_AREA_HECTARES),
            "rules_total": len(matched_rules),
            "rules": matched_rules[:25],
            "rules_truncated": len(matched_rules) > 25,
            "source_provider": "高雄農來訊",
            "official_cwa_alert": False,
            "derived_by_opencwa": False,
            "provider_available": True,
            "last_success_at": datetime.now(timezone.utc).isoformat(),
            "error_code": None,
            "error": None,
        })
        return snapshot

    async def _irrigation_reference(
        self, profile: Mapping[str, Any]
    ) -> dict[str, Any]:
        try:
            return await self.hass.async_add_executor_job(
                lambda: self.client.irrigation_reference(
                    latitude=self.latitude,
                    longitude=self.longitude,
                    crop=profile[CONF_CROP_NAME],
                    planting_date=profile.get(CONF_PLANTING_DATE) or None,
                    area_hectares=profile.get(CONF_AREA_HECTARES),
                )
            )
        except Exception as error:  # advisory values are independently optional
            error_code = getattr(error, "code", type(error).__name__)
            _LOGGER.warning(
                "OpenCWA optional irrigation reference failed (%s)", error_code
            )
            return {
                "available": False,
                "et0": None,
                "kc": None,
                "etc": None,
                "water_requirement": None,
                "crop_water_supported": False,
                "error": "Agricultural irrigation reference update failed",
                "error_code": error_code,
            }

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch shared data once, then isolate every crop result and cache."""
        previous = self.data or {}
        try:
            rows = await self.hass.async_add_executor_job(
                self.client.crop_weather, self.city
            )
            catalog = await self.hass.async_add_executor_job(self.client.crop_catalog)
            rules = await self.hass.async_add_executor_job(self.client.warning_rules)
            supported_crops = {
                str(row.get("C_NAME")).strip()
                for row in catalog
                if row.get("C_NAME")
            }
        except Exception as error:  # optional provider is deliberately non-fatal
            error_code = getattr(error, "code", type(error).__name__)
            _LOGGER.warning(
                "OpenCWA optional agricultural update failed (%s)", error_code
            )
            return {
                profile_id: self._fallback(error, previous.get(profile_id))
                for profile_id in self.crop_profiles
            }

        results: dict[str, dict[str, Any]] = {}
        for profile_id, profile in self.crop_profiles.items():
            try:
                snapshot = self._build_snapshot(
                    profile_id, profile, rows, supported_crops, rules
                )
                irrigation = await self._irrigation_reference(profile)
                results[profile_id] = self._compose(snapshot, irrigation)
            except Exception as error:
                error_code = getattr(error, "code", type(error).__name__)
                _LOGGER.warning(
                    "OpenCWA crop profile update failed (%s)", error_code
                )
                results[profile_id] = self._fallback(
                    error, previous.get(profile_id)
                )
        return results
