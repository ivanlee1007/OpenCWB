from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "opencwb" / "core" / "weatherapi12"))

from typhoon_risk import apply_typhoon_risk, assess_typhoon_risk  # noqa: E402


def _track(latitude, longitude, forecast_latitude=None, forecast_longitude=None):
    forecast_fixes = []
    if forecast_latitude is not None and forecast_longitude is not None:
        forecast_fixes.append({
            "datetime": "2026-07-18T02:00:00+08:00",
            "latitude": forecast_latitude,
            "longitude": forecast_longitude,
        })
    return {
        "count": 1,
        "cyclones": [{
            "cwa_td_no": "TD10",
            "latest_fix": {
                "datetime": "2026-07-17T02:00:00+08:00",
                "latitude": latitude,
                "longitude": longitude,
            },
            "forecast_fixes": forecast_fixes,
        }],
    }


def test_far_tropical_depression_is_monitored_without_alerting():
    result = assess_typhoon_risk(
        _track(5.6, 152.6),
        {"active": False},
        location_latitude=23.0,
        location_longitude=120.2,
    )

    assert result["status"] == "monitoring"
    assert result["should_alert"] is False
    assert result["forecast_approaches_taiwan"] is False
    assert result["location_at_risk"] is False
    assert result["official_warning_active"] is False
    assert result["closest_distance_to_taiwan_km"] is None


def test_alert_requires_official_warning_and_forecast_near_user_location():
    result = assess_typhoon_risk(
        _track(18.0, 128.0, forecast_latitude=22.8, forecast_longitude=120.4),
        {"active": True},
        location_latitude=23.0,
        location_longitude=120.2,
    )

    assert result["status"] == "warning"
    assert result["should_alert"] is True
    assert result["forecast_approaches_taiwan"] is True
    assert result["location_at_risk"] is True
    assert result["official_warning_active"] is True
    assert result["closest_approach_time"] == "2026-07-18T02:00:00+08:00"


def test_nearby_forecast_without_official_warning_remains_monitoring():
    result = assess_typhoon_risk(
        _track(18.0, 128.0, forecast_latitude=22.8, forecast_longitude=120.4),
        {"active": False},
        location_latitude=23.0,
        location_longitude=120.2,
    )

    assert result["status"] == "monitoring"
    assert result["should_alert"] is False
    assert result["forecast_approaches_taiwan"] is True
    assert result["location_at_risk"] is True


def test_risk_is_attached_to_track_and_official_warning_payloads():
    track, warning = apply_typhoon_risk(
        _track(18.0, 128.0, forecast_latitude=22.8, forecast_longitude=120.4),
        {"active": True},
        location_latitude=23.0,
        location_longitude=120.2,
    )

    assert track["risk"]["should_alert"] is True
    assert warning["risk"]["should_alert"] is True
    assert warning["alert_for_location"] is True


def test_current_position_without_forecast_does_not_trigger_alert():
    result = assess_typhoon_risk(
        _track(23.0, 120.2),
        {"active": True},
        location_latitude=23.0,
        location_longitude=120.2,
    )

    assert result["forecast_approaches_taiwan"] is False
    assert result["location_at_risk"] is False
    assert result["should_alert"] is False


def test_official_warning_without_track_data_fails_closed():
    track, warning = apply_typhoon_risk(
        {"count": 0, "cyclones": []},
        {"active": True},
        location_latitude=23.0,
        location_longitude=120.2,
    )

    assert track["risk"]["should_alert"] is False
    assert warning["alert_for_location"] is False


def test_multiple_cyclones_cannot_combine_separate_proximity_conditions():
    track = {
        "count": 2,
        "cyclones": [
            {
                "name": "TAIWAN",
                "forecast_fixes": [{"latitude": 23.7, "longitude": 120.9}],
            },
            {
                "name": "JAPAN",
                "forecast_fixes": [{"latitude": 35.0, "longitude": 140.0}],
            },
        ],
    }

    result = assess_typhoon_risk(
        track,
        {"active": True},
        location_latitude=35.0,
        location_longitude=140.0,
    )

    assert result["should_alert"] is False


def test_official_warning_selects_matching_cyclone():
    track = {
        "count": 2,
        "cyclones": [
            {
                "name": "REMOTE",
                "forecast_fixes": [{"latitude": 5.6, "longitude": 152.6}],
            },
            {
                "name": "BAVI",
                "cwa_name": "巴威",
                "forecast_fixes": [{
                    "datetime": "2026-07-18T02:00:00+08:00",
                    "latitude": 22.8,
                    "longitude": 120.4,
                }],
            },
        ],
    }

    result = assess_typhoon_risk(
        track,
        {"active": True, "typhoon": {"name": "BAVI", "cwa_name": "巴威"}},
        location_latitude=23.0,
        location_longitude=120.2,
    )

    assert result["should_alert"] is True
    assert result["selected_cyclone_index"] == 1
