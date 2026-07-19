"""Client for the optional 高雄農來訊 agricultural data provider."""
from __future__ import annotations

from datetime import date
from typing import Any

import requests

try:
    from .kcg_parser import KCGDataError, parse_business_payload, parse_irrigation_reference
except ImportError:  # Direct module import used by the lightweight unit tests.
    from kcg_parser import KCGDataError, parse_business_payload, parse_irrigation_reference


ROOT = "https://agri-data.kcg.gov.tw"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
CROP_WEATHER_PATH = "/Agri_API/API/Agri/cropweatherTaiwan"
CROP_CATALOG_PATH = "/Agri_API/API/Agri/CropVType"
WARNING_RULES_PATH = "/Agri_API/API/Agri/List_Warning"
ET0_PATH = "/Agri_API/Api/CropWaterGo/SelectDailyEt0"
KC_PATH = "/Agri_API/Api/CropWaterGo/SelectCropCoefficientKc"
ETC_PATH = "/Agri_API/Api/CropWaterGo/SelectEtc"


class KCGOpenDataClient:
    """Small defensive HTTP client; agricultural failures never own CWA weather state."""

    def __init__(
        self,
        token: str | None = None,
        *,
        timeout: int = 30,
        session: requests.Session | None = None,
    ) -> None:
        self.token = token.strip() if isinstance(token, str) and token.strip() else None
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.trust_env = False

    def _get(self, path: str, params: dict[str, Any] | None = None, *, token_required=False):
        query = dict(params or {})
        if token_required:
            if not self.token:
                raise KCGDataError(
                    "Agricultural irrigation credential is not configured",
                    code="not_configured",
                )
            query["TOKEN"] = self.token
        try:
            response = self.session.get(
                f"{ROOT}{path}",
                params=query,
                timeout=(10, self.timeout),
                headers={"Accept": "*/*"},
                stream=True,
            )
        except requests.RequestException as error:
            raise KCGDataError(
                "Agricultural provider connection failed", code="unavailable"
            ) from error
        try:
            if response.status_code >= 400:
                code = "unauthorized" if response.status_code in (401, 403) else "http_error"
                raise KCGDataError(
                    f"Agricultural provider HTTP {response.status_code}", code=code
                )
            body = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise KCGDataError(
                        "Agricultural provider response is too large",
                        code="response_too_large",
                    )
            response_text = body.decode(response.encoding or "utf-8", errors="replace")
        finally:
            response.close()
        return parse_business_payload(response_text)

    def close(self) -> None:
        """Release provider HTTP resources when the config entry unloads."""
        self.session.close()

    @staticmethod
    def _rows(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
        for key in keys:
            if key not in payload:
                continue
            value = payload[key]
            if not isinstance(value, list) or any(
                not isinstance(row, dict) for row in value
            ):
                raise KCGDataError(
                    "Invalid agricultural provider collection",
                    code="malformed_response",
                )
            return value
        raise KCGDataError(
            "Agricultural provider collection is missing",
            code="malformed_response",
        )

    def crop_weather(self, city: str) -> list[dict[str, Any]]:
        """Return the configured city's crop-weather rows, never nationwide rows."""
        payload = self._get(
            CROP_WEATHER_PATH, {"CITY_NAME": city.strip().replace("台", "臺")}
        )
        return self._rows(payload, "crops", "Data", "data")

    def crop_catalog(self) -> list[dict[str, Any]]:
        payload = self._get(CROP_CATALOG_PATH)
        return self._rows(payload, "crops", "Data", "data")

    def warning_rules(self) -> list[dict[str, Any]]:
        payload = self._get(WARNING_RULES_PATH)
        return self._rows(payload, "crops", "Data", "data")

    def daily_et0(self, latitude: float, longitude: float, start_date: str, end_date: str):
        return self._get(
            ET0_PATH,
            {
                "LAT": latitude,
                "LON": longitude,
                "START_DATE": start_date,
                "END_DATE": end_date,
            },
            token_required=True,
        )

    def crop_coefficient(self, crop: str):
        return self._get(KC_PATH, {"SEARCH_NAME": crop}, token_required=True)

    def crop_etc(
        self,
        *,
        latitude: float,
        longitude: float,
        crop: str,
        planting_date: str,
        area_hectares: float,
    ):
        return self._get(
            ETC_PATH,
            {
                "LAT": latitude,
                "LON": longitude,
                "V_NAME": crop,
                "START_DATE": planting_date,
                "AREAS": area_hectares,
            },
            token_required=True,
        )

    def irrigation_reference(
        self,
        *,
        latitude: float,
        longitude: float,
        crop: str,
        planting_date: str | None = None,
        area_hectares: float | None = None,
        target_date: str | None = None,
    ) -> dict[str, Any]:
        """Fetch optional token-gated reference values; no token means no calls."""
        if not self.token:
            return {
                "available": False,
                "et0": None,
                "kc": None,
                "etc": None,
                "water_requirement": None,
                "crop_water_supported": False,
            }
        target_date = target_date or date.today().isoformat()
        try:
            et0_payload = self.daily_et0(
                latitude, longitude, target_date, target_date
            )
        except KCGDataError as error:
            if error.code in ("unauthorized", "unavailable", "http_error"):
                raise
            et0_payload = None
        try:
            kc_payload = self.crop_coefficient(crop)
        except KCGDataError as error:
            if error.code in ("unauthorized", "unavailable", "http_error"):
                raise
            kc_payload = None
        try:
            etc_payload = (
                self.crop_etc(
                    latitude=latitude,
                    longitude=longitude,
                    crop=crop,
                    planting_date=planting_date,
                    area_hectares=area_hectares,
                )
                if planting_date and area_hectares is not None
                else None
            )
        except KCGDataError as error:
            if error.code in ("unauthorized", "unavailable", "http_error"):
                raise
            etc_payload = None
        result = parse_irrigation_reference(
            et0_payload=et0_payload,
            kc_payload=kc_payload,
            etc_payload=etc_payload,
        )
        return result
