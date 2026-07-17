"""Build ready-to-use Home Assistant notification messages for CWA warnings."""
from __future__ import annotations

from typing import Any


def _list_text(values: list[Any] | tuple[Any, ...] | None, default: str = "未列出") -> str:
    items = [str(value) for value in (values or []) if value not in (None, "")]
    return "、".join(items) if items else default


def _value(value: Any, default: str = "未知") -> Any:
    return default if value in (None, "") else value


def _wind_detail_lines(alert: dict[str, Any]) -> list[str]:
    advisory = alert.get("wind_advisory")
    if not isinstance(advisory, dict):
        return []
    average_level = advisory.get("average_wind_beaufort_min")
    gust_level = advisory.get("gust_beaufort_min")
    average_speed = advisory.get("average_wind_speed_min_m_s")
    gust_speed = advisory.get("gust_speed_min_m_s")
    lines = [
        "",
        f"官方等級：{_value(advisory.get('warning_level_label'), '資料未提供')}"
        f"（{_value(advisory.get('danger_level'), '資料未提供')}）",
    ]
    if None not in (average_level, gust_level, average_speed, gust_speed):
        lines.extend([
            (
                f"警戒門檻：平均風 {average_level} 級以上（約 {average_speed} m/s 起），"
                f"或陣風 {gust_level} 級以上（約 {gust_speed} m/s 起）"
            ),
            "註：此為警報觸發門檻，不是現場實測風速。",
        ])
    else:
        lines.append("警戒門檻：CWA 原始資料未提供完整風級或風速。")
    danger_explanations = {
        "yellow": "危險程度：注意；強陣風可能吹落未固定物、折損樹枝，戶外與高處作業有風險。",
        "orange": "危險程度：警戒；可能出現顯著樹木與設施損壞，戶外活動及交通風險高。",
        "red": "危險程度：嚴重警戒；可能造成廣泛且嚴重的樹木、建物與設施損壞，應以人身安全為優先。",
    }
    danger_explanation = danger_explanations.get(advisory.get("warning_level"))
    if danger_explanation:
        lines.append(danger_explanation)
    lines.extend([
        "",
        f"作物與設施風險：{_value(advisory.get('crop_risk_level'), '資料未提供')}",
    ])
    for impact in advisory.get("crop_impacts") or []:
        lines.append(f"• {impact}")
    actions = advisory.get("recommended_actions") or []
    if actions:
        lines.extend(["", "建議措施："])
        lines.extend(f"• {action}" for action in actions)
    assessment_note = advisory.get("assessment_note")
    if assessment_note:
        lines.extend(["", str(assessment_note)])
    start_time = alert.get("start_time")
    end_time = alert.get("end_time")
    if start_time or end_time:
        lines.extend(["", f"有效時間：{_value(start_time, '資料未提供')} ～ {_value(end_time, '資料未提供')}"])
    return lines


def _wind_attributes(alerts: list[dict[str, Any]]) -> dict[str, Any]:
    for alert in alerts:
        advisory = alert.get("wind_advisory")
        if not isinstance(advisory, dict):
            continue
        keys = (
            "warning_level",
            "warning_level_label",
            "danger_level",
            "average_wind_beaufort_min",
            "gust_beaufort_min",
            "average_wind_speed_min_m_s",
            "gust_speed_min_m_s",
            "crop_risk_level",
            "crop_impacts",
            "recommended_actions",
            "assessment_note",
        )
        return {key: advisory.get(key) for key in keys if key in advisory}
    return {}


def _cyclone_name(cyclone: dict[str, Any]) -> str:
    cwa_name = cyclone.get("cwa_name")
    international_name = cyclone.get("name")
    if cwa_name and international_name:
        return f"{cwa_name}（{international_name}）"
    if cwa_name or international_name:
        return str(cwa_name or international_name)
    td_no = cyclone.get("cwa_td_no")
    if td_no:
        td_label = str(td_no)
        if not td_label.upper().startswith("TD"):
            td_label = f"TD{td_label}"
        return f"未命名熱帶性低氣壓 {td_label}"
    return "未命名熱帶氣旋"


def _risk_attributes(risk: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "forecast_approaches_taiwan",
        "location_at_risk",
        "official_warning_active",
        "closest_distance_to_taiwan_km",
        "closest_distance_to_location_km",
        "closest_approach_time",
        "taiwan_approach_threshold_km",
        "location_risk_threshold_km",
    )
    return {key: risk.get(key) for key in keys if key in risk}


def build_typhoon_warning_notification(data: dict[str, Any] | None) -> dict[str, Any]:
    """Build a notification payload for official CWA typhoon warnings."""
    data = data or {}
    official_warning_active = bool(data.get("active"))
    active = official_warning_active and data.get("alert_for_location") is True
    typhoon = data.get("typhoon") if isinstance(data.get("typhoon"), dict) else {}
    risk = data.get("risk") if isinstance(data.get("risk"), dict) else {}
    headline = _value(data.get("headline"), "目前無有效官方颱風警報")
    title = "⚠️ CWA 官方颱風警報" if active else "CWA 官方颱風警報：目前無有效警報"
    if active:
        message = "\n".join([
            str(headline),
            "",
            f"颱風：{_value(typhoon.get('cwa_name'))}（{_value(typhoon.get('name'), '')}）",
            f"警報類型：{_value(data.get('warning_type'))}",
            f"報數：第 {_value(data.get('report_no'))} 報",
            "",
            f"警戒區：{_list_text(data.get('affected_areas'))}",
            "",
            f"有效時間：{_value(data.get('effective'))} ~ {_value(data.get('expires'))}",
            "",
            f"CWA 官方資訊：{_value(data.get('web'), '未提供')}",
        ])
        summary = str(headline)
        severity = "critical"
    elif official_warning_active:
        title = "CWA 官方颱風警報：設定地點目前未達告警條件"
        message = "CWA 已發布官方颱風警報，但依目前預測路徑，尚未判定會影響設定地點。"
        summary = "官方警報有效，設定地點持續監測中"
        severity = "info"
    else:
        message = "目前沒有 CWA 有效官方颱風警報。熱帶氣旋路徑資料若存在，仍不等於臺灣已有官方颱風警報。"
        summary = "目前無有效官方颱風警報"
        severity = "info"
    result = {
        "active": active,
        "status": "active" if active else ("monitoring" if official_warning_active else "inactive"),
        "severity": severity,
        "title": title,
        "message": message,
        "summary": summary,
        "source_dataset": "W-C0034-001",
    }
    result.update(_risk_attributes(risk))
    return result


def build_weather_alert_notification(data: dict[str, Any] | None) -> dict[str, Any]:
    """Build a notification payload for location-matched CWA weather alerts."""
    data = data or {}
    alerts = data.get("alerts") if isinstance(data.get("alerts"), list) else []
    alerts = [alert for alert in alerts if isinstance(alert, dict)]
    active = bool(data.get("active_for_location"))
    matched_alerts = [alert for alert in alerts if alert.get("matched_locations")]

    # Older payloads may only expose aggregate matching metadata. Keep the
    # single-alert case compatible while never guessing across multiple alerts.
    if active and not matched_alerts and len(alerts) == 1 and data.get("matched_locations"):
        matched_alerts = [{
            **alerts[0],
            "matched_locations": data.get("matched_locations"),
            "match_method": data.get("match_method"),
            "unmatched_special_areas": data.get("unmatched_special_areas"),
        }]

    display_alerts = matched_alerts if active else alerts[:1]
    first_alert = display_alerts[0] if display_alerts else {}
    phenomena = _value(first_alert.get("phenomena"), "重大氣象")
    significance = _value(first_alert.get("significance"), "警特報")
    alert_name = f"{phenomena}{significance}"
    matched_count = len(matched_alerts)

    if active:
        title = f"⚠️ CWA {alert_name}"
        if matched_count > 1:
            title += f"（另 {matched_count - 1} 項）"
        message_lines = ["目前地點命中 CWA 警特報。"]
        for index, alert in enumerate(matched_alerts):
            if index:
                message_lines.extend(["", "──────────"])
            current_name = (
                f"{_value(alert.get('phenomena'), '重大氣象')}"
                f"{_value(alert.get('significance'), '警特報')}"
            )
            message_lines.extend([
                "",
                f"類型：{current_name}",
                f"命中區域：{_list_text(alert.get('matched_locations'))}",
                f"比對方式：{_value(alert.get('match_method'), '無命中')}",
                "",
                f"CWA 影響區域：{_list_text(alert.get('affected_areas'))}",
            ])
            message_lines.extend(_wind_detail_lines(alert))
            unmatched = alert.get("unmatched_special_areas") or []
            if unmatched:
                message_lines.extend(["", f"其他特殊區域：{_list_text(unmatched)}"])
            content_text = alert.get("content_text")
            if content_text:
                message_lines.extend(["", "說明：", str(content_text)])
        summary = alert_name if matched_count == 1 else f"{alert_name}等 {matched_count} 項"
    else:
        title = "CWA 重大氣象警特報：目前未命中所在地"
        message_lines = [
            "目前有 CWA 警特報資料，但尚未命中目前設定地點。",
            "",
            f"類型：{alert_name}",
            f"命中區域：{_list_text(data.get('matched_locations'))}",
            f"比對方式：{_value(data.get('match_method'), '無命中')}",
            "",
            f"CWA 影響區域：{_list_text(first_alert.get('affected_areas'))}",
        ]
        message_lines.extend(_wind_detail_lines(first_alert))
        unmatched = data.get("unmatched_special_areas") or []
        if unmatched:
            message_lines.extend(["", f"其他特殊區域：{_list_text(unmatched)}"])
        content_text = first_alert.get("content_text")
        if content_text:
            message_lines.extend(["", "說明：", str(content_text)])
        summary = alert_name

    result = {
        "active": active,
        "status": "active" if active else "inactive",
        "severity": "warning" if active else "info",
        "title": title,
        "message": "\n".join(message_lines),
        "summary": summary,
        "source_dataset": "W-C0033-002",
    }
    result.update(_wind_attributes(display_alerts))
    return result


def build_tropical_cyclone_notification(
    data: dict[str, Any] | None,
    typhoon_warning: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a pre-alert payload for tropical cyclone track data."""
    data = data or {}
    typhoon_warning = typhoon_warning or {}
    count = int(data.get("count") or 0)
    cyclones = data.get("cyclones") if isinstance(data.get("cyclones"), list) else []
    risk = data.get("risk") if isinstance(data.get("risk"), dict) else {}
    selected_index = risk.get("selected_cyclone_index", 0)
    if not isinstance(selected_index, int) or not 0 <= selected_index < len(cyclones):
        selected_index = 0
    cyclone = cyclones[selected_index] if cyclones and isinstance(cyclones[selected_index], dict) else {}
    fix = cyclone.get("latest_fix") if isinstance(cyclone.get("latest_fix"), dict) else {}
    official_warning_active = bool(typhoon_warning.get("active"))

    if count > 0 and not risk.get("should_alert"):
        cyclone_name = _cyclone_name(cyclone)
        reason = (
            "尚未同時符合接近臺灣、可能影響設定地點及官方颱風警報三項告警條件。"
            if risk
            else "尚未完成位置風險判定，因此不能確認符合告警條件。"
        )
        message = "\n".join([
            f"CWA 目前追蹤到熱帶氣旋，但{reason}",
            "",
            f"名稱：{cyclone_name}",
            f"最新定位：{_value(fix.get('datetime'))}",
            f"位置：北緯 {_value(fix.get('latitude'), '?')}、東經 {_value(fix.get('longitude'), '?')}",
            "",
            "目前僅持續監測，不建議發送告警通知。",
        ])
        result = {
            "active": False,
            "status": "monitoring",
            "severity": "info",
            "title": "🌀 CWA 熱帶氣旋監測中",
            "message": message,
            "summary": cyclone_name,
            "source_dataset": "W-C0034-005",
        }
        result.update(_risk_attributes(risk))
        return result

    if official_warning_active and count > 0:
        return {
            "active": False,
            "status": "suppressed",
            "severity": "info",
            "title": "🌀 CWA 熱帶氣旋資訊已由官方颱風警報涵蓋",
            "message": "CWA 目前有熱帶氣旋路徑資料，但已有官方颱風警報；建議以官方颱風警報通知為主要告警，避免重複通知。",
            "summary": "已有官方颱風警報，熱帶氣旋預先注意已抑制",
            "source_dataset": "W-C0034-005",
        }

    if count == 0:
        return {
            "active": False,
            "status": "inactive",
            "severity": "info",
            "title": "CWA 熱帶氣旋預先注意：目前無資料",
            "message": "目前 CWA 熱帶氣旋路徑資料沒有活動中熱帶氣旋。",
            "summary": "目前無活動中熱帶氣旋",
            "source_dataset": "W-C0034-005",
        }

    cyclone_name = _cyclone_name(cyclone)
    return {
        "active": False,
        "status": "monitoring",
        "severity": "info",
        "title": "🌀 CWA 熱帶氣旋監測中",
        "message": f"CWA 目前追蹤到 {cyclone_name}，但告警條件資料不完整，僅持續監測。",
        "summary": cyclone_name,
        "source_dataset": "W-C0034-005",
    }
