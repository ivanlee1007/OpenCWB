from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "opencwb" / "core" / "weatherapi12"))

from notification_builder import (  # noqa: E402
    build_tropical_cyclone_notification,
    build_typhoon_warning_notification,
    build_weather_alert_notification,
)


def test_typhoon_warning_notification_message_contains_official_warning_fields():
    notification = build_typhoon_warning_notification({
        "active": True,
        "headline": "海上陸上颱風警報",
        "warning_type": "海上陸上",
        "report_no": "3",
        "affected_areas": ["臺南市", "高雄市"],
        "effective": "2026-07-08T08:00:00+08:00",
        "expires": "2026-07-08T14:00:00+08:00",
        "web": "https://www.cwa.gov.tw/V8/C/P/Warning/FIFOWS.html",
        "typhoon": {"cwa_name": "巴威", "name": "BAVI"},
    })

    assert notification["active"] is True
    assert notification["status"] == "active"
    assert notification["severity"] == "critical"
    assert notification["title"] == "⚠️ CWA 官方颱風警報"
    assert "海上陸上颱風警報" in notification["message"]
    assert "颱風：巴威（BAVI）" in notification["message"]
    assert "警報類型：海上陸上" in notification["message"]
    assert "警戒區：臺南市、高雄市" in notification["message"]
    assert notification["source_dataset"] == "W-C0034-001"


def test_weather_alert_notification_message_contains_matched_area_and_special_areas():
    notification = build_weather_alert_notification({
        "count": 1,
        "active_for_location": True,
        "matched_locations": ["臺南市"],
        "unmatched_special_areas": ["恆春半島", "蘭嶼綠島"],
        "match_method": "direct",
        "alerts": [{
            "phenomena": "陸上強風",
            "significance": "特報",
            "affected_areas": ["臺南市", "高雄市", "恆春半島"],
            "content_text": "請注意強風。",
        }],
    })

    assert notification["active"] is True
    assert notification["status"] == "active"
    assert notification["severity"] == "warning"
    assert notification["title"] == "⚠️ CWA 陸上強風特報"
    assert "命中區域：臺南市" in notification["message"]
    assert "比對方式：direct" in notification["message"]
    assert "其他特殊區域：恆春半島、蘭嶼綠島" in notification["message"]
    assert "請注意強風。" in notification["message"]
    assert notification["source_dataset"] == "W-C0033-002"


def test_tropical_cyclone_notification_is_suppressed_when_official_warning_active():
    notification = build_tropical_cyclone_notification(
        {
            "count": 1,
            "cyclones": [{
                "cwa_name": "巴威",
                "name": "BAVI",
                "latest_fix": {
                    "datetime": "2026-07-09T02:00:00+08:00",
                    "latitude": 17.6,
                    "longitude": 130.8,
                    "pressure": 915.0,
                    "max_wind_speed": 53.0,
                    "max_gust_speed": 65.0,
                    "moving_direction": "WNW",
                    "moving_speed": 20.0,
                    "circle_15ms": 380.0,
                    "circle_25ms": 180.0,
                },
            }],
        },
        typhoon_warning={"active": True},
    )

    assert notification["active"] is False
    assert notification["status"] == "suppressed"
    assert notification["severity"] == "info"
    assert "已有官方颱風警報" in notification["message"]


def test_tropical_cyclone_notification_message_contains_latest_fix_when_not_suppressed():
    notification = build_tropical_cyclone_notification(
        {
            "count": 1,
            "cyclones": [{
                "cwa_name": "巴威",
                "name": "BAVI",
                "latest_fix": {
                    "datetime": "2026-07-09T02:00:00+08:00",
                    "latitude": 17.6,
                    "longitude": 130.8,
                    "pressure": 915.0,
                    "max_wind_speed": 53.0,
                    "max_gust_speed": 65.0,
                    "moving_direction": "WNW",
                    "moving_speed": 20.0,
                    "circle_15ms": 380.0,
                    "circle_25ms": 180.0,
                },
            }],
        },
        typhoon_warning={"active": False},
    )

    assert notification["active"] is True
    assert notification["status"] == "active"
    assert notification["severity"] == "advisory"
    assert notification["title"] == "🌀 CWA 熱帶氣旋預先注意"
    assert "名稱：巴威（BAVI）" in notification["message"]
    assert "位置：北緯 17.6、東經 130.8" in notification["message"]
    assert "不等於臺灣已有官方颱風警報" in notification["message"]
    assert notification["source_dataset"] == "W-C0034-005"
