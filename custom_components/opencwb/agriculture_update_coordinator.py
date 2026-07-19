"""Optional agricultural advisory coordinator for OpenCWA."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

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
    """Fetch optional agricultural data without affecting CWA coordinators."""

    def __init__(
        self,
        weather_manager,
        location_name: str,
        latitude: float,
        longitude: float,
        hass,
        *,
        token: str | None = None,
        crop: str | None = None,
        growth_stage: str | None = None,
        planting_date: str | None = None,
        area_hectares: float | None = None,
        client: KCGOpenDataClient | None = None,
    ) -> None:
        self.location_name = location_name
        self.latitude = latitude
        self.longitude = longitude
        self.crop = crop.strip() if isinstance(crop, str) and crop.strip() else None
        self.growth_stage = (
            growth_stage.strip()
            if isinstance(growth_stage, str) and growth_stage.strip()
            else None
        )
        self.planting_date = planting_date or None
        self.area_hectares = area_hectares
        self.client = client or KCGOpenDataClient(token=token)
        self.city = self._resolve_city(weather_manager, location_name)
        super().__init__(
            hass,
            _LOGGER,
            name="opencwb_agriculture",
            update_interval=AGRICULTURE_UPDATE_INTERVAL,
        )
        self.data = self._not_configured() if not self.crop else self._fallback()

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
        notification = build_agriculture_notification(snapshot)
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
    def _not_configured() -> dict[str, Any]:
        snapshot = {
            "status": "not_configured",
            "provider_available": None,
            "supported": None,
            "warning_active": False,
            "advisory_active": False,
            "warning_count": 0,
            "advisory_count": 0,
            "matched_total": 0,
            "items": [],
            "items_truncated": False,
            "rules": [],
            "source_timestamp": None,
            "stale": False,
            "error": None,
            "error_code": "crop_not_configured",
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
            "error_code": "crop_not_configured",
        }
        return AgricultureUpdateCoordinator._compose(snapshot, irrigation)

    async def _async_update_data(self) -> dict[str, Any]:
        """Return fallback data on every provider failure; never raise UpdateFailed."""
        if not self.crop:
            return self._not_configured()
        try:
            rows = await self.hass.async_add_executor_job(
                self.client.crop_weather, self.city
            )
            catalog = await self.hass.async_add_executor_job(self.client.crop_catalog)
            supported_crops = {
                str(row.get("C_NAME")).strip()
                for row in catalog
                if row.get("C_NAME")
            }
            snapshot = build_agriculture_snapshot(
                rows,
                city=self.city,
                town=self.location_name if self.location_name != self.city else None,
                crop=self.crop,
                growth_stage=self.growth_stage,
                supported_crops=supported_crops,
            )
            rules = await self.hass.async_add_executor_job(self.client.warning_rules)
            matched_rules = [
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
                if str(row.get("C_NAME", "")).strip() == self.crop
            ]
            snapshot["rules_total"] = len(matched_rules)
            snapshot["rules"] = matched_rules[:25]
            snapshot["rules_truncated"] = len(matched_rules) > 25
            snapshot["source_provider"] = "高雄農來訊"
            snapshot["official_cwa_alert"] = False
            snapshot["derived_by_opencwa"] = False
            snapshot["provider_available"] = True
            snapshot["last_success_at"] = datetime.now(timezone.utc).isoformat()
            snapshot["error_code"] = None
            snapshot["error"] = None
        except Exception as error:  # optional provider is deliberately non-fatal
            error_code = getattr(error, "code", type(error).__name__)
            _LOGGER.warning(
                "OpenCWA optional agricultural update failed (%s)", error_code
            )
            return self._fallback(error, self.data)

        try:
            irrigation = await self.hass.async_add_executor_job(
                lambda: self.client.irrigation_reference(
                    latitude=self.latitude,
                    longitude=self.longitude,
                    crop=self.crop or "",
                    planting_date=self.planting_date,
                    area_hectares=self.area_hectares,
                )
            )
        except Exception as error:  # advisory values are optional even when alerts work
            error_code = getattr(error, "code", type(error).__name__)
            _LOGGER.warning(
                "OpenCWA optional irrigation reference failed (%s)", error_code
            )
            irrigation = {
                "available": False,
                "et0": None,
                "kc": None,
                "etc": None,
                "water_requirement": None,
                "crop_water_supported": False,
                "error": "Agricultural irrigation reference update failed",
                "error_code": getattr(error, "code", type(error).__name__),
            }
        return self._compose(snapshot, irrigation)
