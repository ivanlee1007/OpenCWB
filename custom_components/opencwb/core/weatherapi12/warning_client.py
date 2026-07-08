#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CWA warning and typhoon data client."""
from __future__ import annotations

import requests

from ..commons import exceptions
from . import warning_parser

ROOT_REST_DATASTORE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
ROOT_FILE_API = "https://opendata.cwa.gov.tw/fileapi/v1/opendataapi"

TYPHOON_WARNING_CAP_URI = "W-C0034-001"
TROPICAL_CYCLONE_TRACK_URI = "W-C0034-005"
WEATHER_ALERTS_BY_LOCATION_URI = "W-C0033-001"
WEATHER_ALERTS_BY_EVENT_URI = "W-C0033-002"
TYPHOON_WIND_FORECAST_URI = "F-C0034-005"
TYPHOON_24H_RAIN_FORECAST_URI = "F-C0034-006"
TYPHOON_TOTAL_RAIN_FORECAST_URI = "F-C0034-007"


class WarningClient:
    """Small client for CWA warning, CAP, and typhoon datasets."""

    def __init__(self, api_key: str, config: dict):
        assert isinstance(api_key, str), "You must provide a valid API Key"
        assert isinstance(config, dict)
        self.api_key = api_key
        self.config = config

    def _request_text(self, url: str, params: dict) -> str:
        timeout = self.config.get("connection", {}).get("timeout_secs", 15)
        verify = self.config.get("connection", {}).get("verify_ssl_certs", False)
        proxies_cfg = self.config.get("proxies") or {}
        proxies = {
            key: value
            for key, value in proxies_cfg.items()
            if value and "host:port" not in value and "user:pass" not in value
        } or None
        session = requests.Session()
        session.trust_env = False
        try:
            resp = session.get(url, params=params, timeout=timeout, verify=verify, proxies=proxies)
        except requests.exceptions.SSLError as exc:
            raise exceptions.InvalidSSLCertificateError(str(exc))
        except requests.exceptions.ConnectionError as exc:
            raise exceptions.APIRequestError(str(exc))
        except requests.exceptions.Timeout:
            raise exceptions.TimeoutError("API call timeouted")
        if resp.status_code == 401:
            raise exceptions.UnauthorizedError(resp.text)
        if resp.status_code >= 400:
            raise exceptions.APIRequestError(f"CWA warning request failed: {resp.status_code} {resp.text[:200]}")
        return resp.text

    def _get_fileapi_xml(self, dataset_id: str, fmt: str = "CAP") -> str:
        return self._request_text(
            f"{ROOT_FILE_API}/{dataset_id}",
            {
                "Authorization": self.api_key,
                "downloadType": "WEB",
                "format": fmt,
            },
        )

    def _get_rest_xml(self, dataset_id: str) -> str:
        return self._request_text(
            f"{ROOT_REST_DATASTORE}/{dataset_id}",
            {
                "Authorization": self.api_key,
                "format": "XML",
            },
        )

    def typhoon_warning(self):
        """Fetch and parse official typhoon warning CAP data."""
        return warning_parser.parse_typhoon_warning_cap(
            self._get_fileapi_xml(TYPHOON_WARNING_CAP_URI, "CAP")
        )

    def tropical_cyclone_track(self):
        """Fetch and parse active tropical cyclone track data."""
        return warning_parser.parse_tropical_cyclone_track(
            self._get_rest_xml(TROPICAL_CYCLONE_TRACK_URI)
        )

    def weather_alerts(self, location_names=None):
        """Fetch and parse current hazardous weather alerts by event."""
        return warning_parser.parse_weather_alerts(
            self._get_rest_xml(WEATHER_ALERTS_BY_EVENT_URI),
            location_name=location_names,
        )
