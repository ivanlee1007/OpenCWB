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
        "alert_for_location": True,
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


def test_official_warning_without_location_risk_fails_closed():
    notification = build_typhoon_warning_notification({
        "active": True,
        "headline": "海上陸上颱風警報",
    })

    assert notification["active"] is False
    assert notification["status"] == "monitoring"
    assert notification["severity"] == "info"


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


def test_strong_wind_notification_explains_level_danger_and_crop_risk():
    notification = build_weather_alert_notification({
        "count": 1,
        "active_for_location": True,
        "matched_locations": ["臺中市"],
        "match_method": "direct",
        "alerts": [{
            "phenomena": "陸上強風",
            "significance": "特報",
            "affected_areas": ["臺中市"],
            "matched_locations": ["臺中市"],
            "match_method": "direct",
            "start_time": "2026-07-17T16:22:00+08:00",
            "end_time": "2026-07-18T23:00:00+08:00",
            "content_text": "平均風6級以上或陣風8級以上發生的機率(黃色燈號)。",
            "wind_advisory": {
                "warning_level": "yellow",
                "warning_level_label": "黃色燈號",
                "danger_level": "注意",
                "average_wind_beaufort_min": 6,
                "gust_beaufort_min": 8,
                "average_wind_speed_min_m_s": 10.8,
                "gust_speed_min_m_s": 17.2,
                "crop_risk_level": "中度",
                "crop_impacts": ["作物可能倒伏、折枝、落花落果", "棚架與網布可能鬆脫或破損"],
                "recommended_actions": ["加固棚架、支柱、網布與溫室外膜", "收妥或綁牢戶外資材"],
                "assessment_note": "農業風險為依 CWA 風力門檻整理的提示，並非 CWA 官方農損預測。",
            },
        }],
    })

    assert "官方等級：黃色燈號（注意）" in notification["message"]
    assert "警戒門檻：平均風 6 級以上（約 10.8 m/s 起），或陣風 8 級以上（約 17.2 m/s 起）" in notification["message"]
    assert "此為警報觸發門檻，不是現場實測風速" in notification["message"]
    assert "危險程度：注意；強陣風可能吹落未固定物、折損樹枝，戶外與高處作業有風險" in notification["message"]
    assert "作物與設施風險：中度" in notification["message"]
    assert "作物可能倒伏、折枝、落花落果" in notification["message"]
    assert "加固棚架、支柱、網布與溫室外膜" in notification["message"]
    assert "有效時間：2026-07-17T16:22:00+08:00 ～ 2026-07-18T23:00:00+08:00" in notification["message"]
    assert notification["warning_level"] == "yellow"
    assert notification["average_wind_beaufort_min"] == 6
    assert notification["gust_beaufort_min"] == 8
    assert notification["crop_risk_level"] == "中度"


def test_weather_alert_notification_uses_location_matched_alerts_only():
    notification = build_weather_alert_notification({
        "count": 3,
        "active_for_location": True,
        "matched_locations": ["臺中市山區", "臺中市"],
        "unmatched_special_areas": ["基隆北海岸", "恆春半島"],
        "match_method": "direct",
        "alerts": [
            {
                "phenomena": "陸上強風",
                "significance": "特報",
                "affected_areas": ["基隆北海岸", "雲林縣", "高雄市"],
                "matched_locations": [],
                "unmatched_special_areas": ["基隆北海岸"],
                "match_method": None,
            },
            {
                "phenomena": "豪雨",
                "significance": "特報",
                "affected_areas": ["苗栗縣山區", "臺中市山區", "南投縣"],
                "matched_locations": ["臺中市山區"],
                "unmatched_special_areas": ["苗栗縣山區"],
                "match_method": "direct",
            },
            {
                "phenomena": "大雨",
                "significance": "特報",
                "affected_areas": ["新竹市", "臺中市", "彰化縣"],
                "matched_locations": ["臺中市"],
                "unmatched_special_areas": [],
                "match_method": "direct",
            },
        ],
    })

    assert notification["title"] == "⚠️ CWA 豪雨特報（另 1 項）"
    assert notification["summary"] == "豪雨特報等 2 項"
    assert "類型：豪雨特報" in notification["message"]
    assert "命中區域：臺中市山區" in notification["message"]
    assert "CWA 影響區域：苗栗縣山區、臺中市山區、南投縣" in notification["message"]
    assert "類型：大雨特報" in notification["message"]
    assert "命中區域：臺中市" in notification["message"]
    assert "CWA 影響區域：新竹市、臺中市、彰化縣" in notification["message"]
    assert "陸上強風" not in notification["message"]
    assert "基隆北海岸" not in notification["message"]


def test_tropical_cyclone_notification_is_suppressed_when_official_warning_active():
    notification = build_tropical_cyclone_notification(
        {
            "count": 1,
            "risk": {"should_alert": True, "selected_cyclone_index": 0},
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


def test_track_without_risk_assessment_remains_monitoring():
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

    assert notification["active"] is False
    assert notification["status"] == "monitoring"
    assert notification["severity"] == "info"
    assert notification["title"] == "🌀 CWA 熱帶氣旋監測中"
    assert "名稱：巴威（BAVI）" in notification["message"]
    assert "位置：北緯 17.6、東經 130.8" in notification["message"]
    assert "尚未完成位置風險判定" in notification["message"]
    assert notification["source_dataset"] == "W-C0034-005"


def test_unnamed_distant_cyclone_is_monitoring_not_an_alert():
    notification = build_tropical_cyclone_notification(
        {
            "count": 1,
            "risk": {
                "status": "monitoring",
                "should_alert": False,
                "forecast_approaches_taiwan": False,
                "location_at_risk": False,
                "official_warning_active": False,
                "closest_distance_to_taiwan_km": 3400.0,
                "closest_distance_to_location_km": 3500.0,
                "closest_approach_time": "2026-07-17T02:00:00+08:00",
            },
            "cyclones": [{
                "cwa_name": None,
                "name": None,
                "cwa_td_no": "12",
                "latest_fix": {
                    "datetime": "2026-07-17T02:00:00+08:00",
                    "latitude": 5.6,
                    "longitude": 152.6,
                    "pressure": 1004.0,
                    "max_wind_speed": 15.0,
                    "max_gust_speed": 23.0,
                    "moving_direction": "NNE",
                    "moving_speed": 28.0,
                    "circle_15ms": None,
                    "circle_25ms": None,
                },
            }],
        },
        typhoon_warning={"active": False},
    )

    assert notification["active"] is False
    assert notification["status"] == "monitoring"
    assert notification["severity"] == "info"
    assert notification["title"] == "🌀 CWA 熱帶氣旋監測中"
    assert "未命名熱帶性低氣壓 TD12" in notification["message"]
    assert "未知" not in notification["message"]
    assert notification["forecast_approaches_taiwan"] is False
    assert notification["location_at_risk"] is False
    assert notification["summary"] == "未命名熱帶性低氣壓 TD12"


def test_monitoring_notification_describes_the_selected_cyclone():
    notification = build_tropical_cyclone_notification(
        {
            "count": 2,
            "risk": {
                "should_alert": False,
                "selected_cyclone_index": 1,
            },
            "cyclones": [
                {"name": "REMOTE", "latest_fix": {}},
                {
                    "name": "BAVI",
                    "cwa_name": "巴威",
                    "latest_fix": {
                        "latitude": 22.8,
                        "longitude": 120.4,
                    },
                },
            ],
        },
        typhoon_warning={"active": False},
    )

    assert notification["summary"] == "巴威（BAVI）"
    assert "名稱：巴威（BAVI）" in notification["message"]


def test_official_warning_notification_is_filtered_when_location_not_at_risk():
    notification = build_typhoon_warning_notification({
        "active": True,
        "alert_for_location": False,
        "headline": "海上颱風警報",
        "warning_type": "海上",
        "risk": {
            "status": "monitoring",
            "should_alert": False,
            "forecast_approaches_taiwan": True,
            "location_at_risk": False,
            "official_warning_active": True,
        },
    })

    assert notification["active"] is False
    assert notification["status"] == "monitoring"
    assert notification["severity"] == "info"
    assert "尚未判定會影響設定地點" in notification["message"]
