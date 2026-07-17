"""Location-aware tropical cyclone risk assessment helpers."""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Any

TAIWAN_REFERENCE_LATITUDE = 23.7
TAIWAN_REFERENCE_LONGITUDE = 120.9
TAIWAN_APPROACH_DISTANCE_KM = 800.0
LOCATION_RISK_DISTANCE_KM = 500.0
EARTH_RADIUS_KM = 6371.0


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres."""
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    latitude_term = sin(delta_lat / 2) ** 2
    longitude_term = cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    value = latitude_term + longitude_term
    return 2 * EARTH_RADIUS_KM * asin(sqrt(value))


def _forecast_fixes(cyclone: dict[str, Any]) -> list[dict[str, Any]]:
    """Return valid CWA forecast fixes; the current fix is not a forecast."""
    forecast_fixes = cyclone.get("forecast_fixes")
    if not isinstance(forecast_fixes, list):
        return []
    return [
        fix
        for fix in forecast_fixes
        if isinstance(fix, dict) and all((
            isinstance(fix.get("latitude"), (int, float)),
            isinstance(fix.get("longitude"), (int, float)),
        ))
    ]


def _names(data: dict[str, Any]) -> set[str]:
    """Return normalized identifiers that can correlate warning and track data."""
    names = set()
    for key in ("name", "cwa_name", "cwa_td_no"):
        value = data.get(key)
        if value not in (None, ""):
            names.add(str(value).strip().casefold())
    return names


def _cyclone_result(
    cyclone: dict[str, Any],
    index: int,
    *,
    location_latitude: float,
    location_longitude: float,
) -> dict[str, Any]:
    closest_taiwan = None
    closest_location = None
    closest_time = None
    for fix in _forecast_fixes(cyclone):
        latitude = float(fix["latitude"])
        longitude = float(fix["longitude"])
        taiwan_distance = _distance_km(
            latitude,
            longitude,
            TAIWAN_REFERENCE_LATITUDE,
            TAIWAN_REFERENCE_LONGITUDE,
        )
        location_distance = _distance_km(
            latitude,
            longitude,
            float(location_latitude),
            float(location_longitude),
        )
        if closest_taiwan is None or taiwan_distance < closest_taiwan:
            closest_taiwan = taiwan_distance
        if closest_location is None or location_distance < closest_location:
            closest_location = location_distance
            closest_time = fix.get("datetime")

    approaches_taiwan = closest_taiwan is not None and closest_taiwan <= TAIWAN_APPROACH_DISTANCE_KM
    location_at_risk = closest_location is not None and closest_location <= LOCATION_RISK_DISTANCE_KM
    return {
        "selected_cyclone_index": index,
        "forecast_approaches_taiwan": approaches_taiwan,
        "location_at_risk": location_at_risk,
        "closest_distance_to_taiwan_km": closest_taiwan,
        "closest_distance_to_location_km": closest_location,
        "closest_approach_time": closest_time,
    }


def assess_typhoon_risk(
    track_data: dict[str, Any] | None,
    typhoon_warning: dict[str, Any] | None,
    *,
    location_latitude: float,
    location_longitude: float,
) -> dict[str, Any]:
    """Assess whether one correlated CWA forecast and warning justify an alert."""
    track_data = track_data or {}
    typhoon_warning = typhoon_warning or {}
    official_warning_active = bool(typhoon_warning.get("active"))
    cyclones = track_data.get("cyclones")
    indexed_cyclones = [
        (index, cyclone)
        for index, cyclone in enumerate(cyclones if isinstance(cyclones, list) else [])
        if isinstance(cyclone, dict)
    ]

    candidates = indexed_cyclones
    warning_typhoon = typhoon_warning.get("typhoon")
    warning_names = _names(warning_typhoon) if isinstance(warning_typhoon, dict) else set()
    if official_warning_active:
        if warning_names:
            candidates = [
                (index, cyclone)
                for index, cyclone in indexed_cyclones
                if _names(cyclone) & warning_names
            ]
        elif len(indexed_cyclones) != 1:
            candidates = []

    results = [
        _cyclone_result(
            cyclone,
            index,
            location_latitude=location_latitude,
            location_longitude=location_longitude,
        )
        for index, cyclone in candidates
    ]
    alert_results = [
        result
        for result in results
        if result["forecast_approaches_taiwan"] and result["location_at_risk"]
    ]
    selected = None
    if alert_results:
        selected = min(
            alert_results,
            key=lambda result: result["closest_distance_to_location_km"],
        )
    elif results:
        selected = min(
            results,
            key=lambda result: (
                result["closest_distance_to_taiwan_km"] is None,
                result["closest_distance_to_taiwan_km"] or float("inf"),
            ),
        )

    selected = selected or {
        "selected_cyclone_index": None,
        "forecast_approaches_taiwan": False,
        "location_at_risk": False,
        "closest_distance_to_taiwan_km": None,
        "closest_distance_to_location_km": None,
        "closest_approach_time": None,
    }
    should_alert = all((
        official_warning_active,
        selected["forecast_approaches_taiwan"],
        selected["location_at_risk"],
    ))
    return {
        "status": "warning" if should_alert else "monitoring",
        "should_alert": should_alert,
        "forecast_approaches_taiwan": selected["forecast_approaches_taiwan"],
        "location_at_risk": selected["location_at_risk"],
        "official_warning_active": official_warning_active,
        "selected_cyclone_index": selected["selected_cyclone_index"],
        "closest_distance_to_taiwan_km": (
            round(selected["closest_distance_to_taiwan_km"], 1)
            if selected["closest_distance_to_taiwan_km"] is not None
            else None
        ),
        "closest_distance_to_location_km": (
            round(selected["closest_distance_to_location_km"], 1)
            if selected["closest_distance_to_location_km"] is not None
            else None
        ),
        "closest_approach_time": selected["closest_approach_time"],
        "taiwan_approach_threshold_km": TAIWAN_APPROACH_DISTANCE_KM,
        "location_risk_threshold_km": LOCATION_RISK_DISTANCE_KM,
    }


def apply_typhoon_risk(
    track_data: dict[str, Any] | None,
    typhoon_warning: dict[str, Any] | None,
    *,
    location_latitude: float,
    location_longitude: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Attach one correlated risk decision to track and warning payloads."""
    track_result = dict(track_data or {})
    warning_result = dict(typhoon_warning or {})
    risk = assess_typhoon_risk(
        track_result,
        warning_result,
        location_latitude=location_latitude,
        location_longitude=location_longitude,
    )
    track_result["risk"] = risk
    warning_result["risk"] = risk
    warning_result["alert_for_location"] = risk["should_alert"]
    return track_result, warning_result
