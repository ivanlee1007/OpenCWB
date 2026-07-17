#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Parsers for CWA warning, typhoon, and hazardous-weather datasets."""
from __future__ import annotations

from datetime import datetime, timezone
import re
import xml.etree.ElementTree as ET
from typing import Any


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _children(element: ET.Element, name: str | None = None) -> list[ET.Element]:
    items = [child for child in list(element) if name is None or _strip_ns(child.tag) == name]
    return items


def _first(element: ET.Element | None, path: str) -> ET.Element | None:
    if element is None:
        return None
    current = [element]
    for part in path.split("/"):
        next_items: list[ET.Element] = []
        for item in current:
            next_items.extend(_children(item, part))
        if not next_items:
            return None
        current = next_items
    return current[0]


def _all(element: ET.Element | None, path: str) -> list[ET.Element]:
    if element is None:
        return []
    current = [element]
    for part in path.split("/"):
        next_items: list[ET.Element] = []
        for item in current:
            next_items.extend(_children(item, part))
        current = next_items
        if not current:
            return []
    return current


def _text(element: ET.Element | None, path: str | None = None) -> str | None:
    target = _first(element, path) if path else element
    if target is None or target.text is None:
        return None
    value = target.text.strip()
    return value if value else None


def _float(value: str | None) -> float | None:
    if value in (None, "", "-", "–"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _dt_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _section_text(description: ET.Element | None, title: str) -> str | None:
    if description is None:
        return None
    for section in description.iter():
        if _strip_ns(section.tag) == "section" and section.attrib.get("title") == title:
            return "".join(section.itertext()).strip() or None
    return None


def _position(value: str | None) -> list[float] | None:
    if not value or "," not in value:
        return None
    try:
        lat, lon = [float(part.strip()) for part in value.split(",", 1)]
    except ValueError:
        return None
    return [lat, lon]


def _is_active_typhoon(parsed: dict[str, Any], now: datetime | None) -> bool:
    if (parsed.get("status") or "").lower() != "actual":
        return False
    if (parsed.get("msg_type") or "").lower() == "cancel":
        return False
    if (parsed.get("warning_type") or "").upper() == "END":
        return False
    headline = parsed.get("headline") or ""
    if "解除" in headline or "取消" in headline:
        return False
    expires = _parse_dt(parsed.get("expires"))
    if expires is not None:
        compare_now = now or datetime.now(timezone.utc)
        if compare_now.tzinfo is None:
            compare_now = compare_now.replace(tzinfo=timezone.utc)
        if expires.astimezone(timezone.utc) <= compare_now.astimezone(timezone.utc):
            return False
    return True


def parse_typhoon_warning_cap(xml_text: str | bytes | None, now: datetime | None = None) -> dict[str, Any]:
    """Parse CWA W-C0034-001 CAP XML into stable HA-friendly fields."""
    if not xml_text:
        return {"active": False, "affected_areas": [], "typhoon": {}}
    root = ET.fromstring(xml_text)
    info = _first(root, "info")
    description = _first(info, "description")
    typhoon_info = _first(description, "typhoon-info")
    typhoon_section = None
    if typhoon_info is not None:
        for section in _children(typhoon_info, "section"):
            if section.attrib.get("title") == "颱風資訊":
                typhoon_section = section
                break

    analysis = _first(typhoon_section, "analysis")
    prediction = _first(typhoon_section, "prediction")
    parsed: dict[str, Any] = {
        "active": False,
        "identifier": _text(root, "identifier") or _text(root, "Identifier"),
        "sender": _text(root, "sender"),
        "sent": _text(root, "sent"),
        "status": _text(root, "status"),
        "msg_type": _text(root, "msgType"),
        "scope": _text(root, "scope"),
        "event": _text(info, "event"),
        "effective": _text(info, "effective"),
        "onset": _text(info, "onset"),
        "expires": _text(info, "expires"),
        "headline": _text(info, "headline"),
        "web": _text(info, "web"),
        "report_no": _section_text(description, "警報報數"),
        "warning_type": _section_text(description, "警報類別"),
        "affected_areas": [area for area in (_text(area, "areaDesc") for area in _all(info, "area")) if area],
        "typhoon": {
            "name": _text(typhoon_section, "typhoon_name"),
            "cwa_name": _text(typhoon_section, "cwa_typhoon_name"),
            "analysis_time": _text(analysis, "time"),
            "analysis_position": _position(_text(analysis, "position")),
            "prediction_time": _text(prediction, "time"),
            "prediction_position": _position(_text(prediction, "position")),
        },
    }
    parsed["active"] = _is_active_typhoon(parsed, now)
    return parsed


def _parse_fix(fix: ET.Element) -> dict[str, Any]:
    return {
        "datetime": _text(fix, "DateTime"),
        "longitude": _float(_text(fix, "CoordinateLongitude")),
        "latitude": _float(_text(fix, "CoordinateLatitude")),
        "max_wind_speed": _float(_text(fix, "MaxWindSpeed")),
        "max_gust_speed": _float(_text(fix, "MaxGustSpeed")),
        "pressure": _float(_text(fix, "Pressure")),
        "moving_speed": _float(_text(fix, "MovingSpeed")),
        "moving_direction": _text(fix, "MovingDirection"),
        "circle_15ms": _float(_text(fix, "Circle15ms/Radius")),
        "circle_25ms": _float(_text(fix, "Circle25ms/Radius")),
    }


def parse_tropical_cyclone_track(xml_text: str | bytes | None) -> dict[str, Any]:
    """Parse CWA W-C0034-005 XML tropical cyclone track data."""
    if not xml_text:
        return {"count": 0, "cyclones": []}
    root = ET.fromstring(xml_text)
    cyclones = []
    for cyclone in root.iter():
        if _strip_ns(cyclone.tag) != "TropicalCyclone":
            continue
        analysis_fixes = [_parse_fix(fix) for fix in _all(cyclone, "AnalysisData/Fix")]
        forecast_fixes = [_parse_fix(fix) for fix in _all(cyclone, "ForecastData/Fix")]
        cyclones.append({
            "year": _text(cyclone, "Year"),
            "name": _text(cyclone, "TyphoonName"),
            "cwa_name": _text(cyclone, "CwaTyphoonName"),
            "cwa_td_no": _text(cyclone, "CwaTdNo"),
            "cwa_ty_no": _text(cyclone, "CwaTyNo"),
            "latest_fix": analysis_fixes[-1] if analysis_fixes else None,
            "analysis_fixes": analysis_fixes,
            "forecast_fixes": forecast_fixes,
        })
    return {"count": len(cyclones), "cyclones": cyclones}


SPECIAL_AREA_LOCATIONS = {
    "蘭嶼綠島": ["臺東縣", "台東縣", "蘭嶼鄉", "綠島鄉"],
    "恆春半島": ["屏東縣", "恆春鎮", "車城鄉", "滿州鄉", "枋山鄉", "牡丹鄉"],
    "基隆北海岸": ["基隆市", "新北市", "萬里區", "金山區", "石門區", "三芝區", "淡水區", "瑞芳區", "貢寮區"],
    "大臺北山區": ["臺北市", "台北市", "新北市"],
    "桃園山區": ["桃園市"],
    "新竹山區": ["新竹縣", "新竹市"],
    "苗栗山區": ["苗栗縣"],
    "臺中山區": ["臺中市", "台中市"],
    "南投山區": ["南投縣"],
    "嘉義山區": ["嘉義縣", "嘉義市"],
    "臺南山區": ["臺南市", "台南市"],
    "高雄山區": ["高雄市"],
    "屏東山區": ["屏東縣"],
    "宜蘭山區": ["宜蘭縣"],
    "花蓮山區": ["花蓮縣"],
    "臺東山區": ["臺東縣", "台東縣"],
    "沿海空曠地區": [],
    "山區": [],
}


BEAUFORT_MIN_SPEED_M_S = {
    0: 0.0,
    1: 0.3,
    2: 1.6,
    3: 3.4,
    4: 5.5,
    5: 8.0,
    6: 10.8,
    7: 13.9,
    8: 17.2,
    9: 20.8,
    10: 24.5,
    11: 28.5,
    12: 32.7,
    13: 37.0,
    14: 41.5,
    15: 46.2,
    16: 51.0,
    17: 56.1,
}


WIND_LEVEL_RISK = {
    "yellow": {
        "label": "黃色燈號",
        "danger_level": "注意",
        "crop_risk_level": "中度",
        "crop_impacts": [
            "高稈、莖葉柔軟或已結果作物可能倒伏、折枝、落花落果",
            "葉片可能撕裂或出現風灼，幼苗與新梢較敏感",
            "棚架、支柱、防蟲網、遮陰網與溫室外膜可能鬆脫或破損",
            "盆栽、育苗盤、資材及未固定物可能傾倒或被吹落",
        ],
        "recommended_actions": [
            "加固棚架、支柱、網布與溫室外膜，收妥或綁牢戶外資材",
            "為高稈、結果中及幼苗作物加設支撐，提前採收可採收果實",
            "暫停高處、網室屋頂及迎風面作業，巡查排水與供電安全",
        ],
    },
    "orange": {
        "label": "橙色燈號",
        "danger_level": "警戒",
        "crop_risk_level": "高",
        "crop_impacts": [
            "大面積倒伏、折枝、落花落果及葉片撕裂的機率明顯升高",
            "幼苗、攀藤、高稈及結果負載較重的作物可能遭受嚴重損害",
            "棚架、網布、溫室外膜、門窗與輕型設施可能破損或局部掀起",
            "盆栽、育苗盤及農業資材可能被吹翻、吹落或成為飛散物",
        ],
        "recommended_actions": [
            "立即完成棚架、網布、外膜、門窗與錨定點加固，清空迎風面鬆散物",
            "依設施耐風設計與現場標準作業程序調整通風口、捲簾及電力設備",
            "提前採收成熟果實，停止高處與戶外作業，避免人員進入老舊或輕型設施",
        ],
    },
    "red": {
        "label": "紅色燈號",
        "danger_level": "嚴重警戒",
        "crop_risk_level": "極高",
        "crop_impacts": [
            "作物可能大範圍倒伏、折斷、落果，葉片與新梢可能遭受嚴重損傷",
            "溫室、棚架、防蟲網、遮陰網與外膜有重大破壞甚至整體失效風險",
            "未固定設備、盆栽、資材及構件可能成為危險飛散物",
        ],
        "recommended_actions": [
            "人員安全優先；停止戶外與設施維修作業，撤離老舊、受損或輕型設施",
            "若安全且尚有時間，依耐風設計與既定防災程序完成斷電、固定及封閉作業",
            "避免在強風期間臨時搶修，風勢減弱後再檢查結構、電力與灌溉系統",
        ],
    },
}


def _wind_advisory(content_text: str | None) -> dict[str, Any] | None:
    """Extract official wind thresholds and add clearly labelled farm guidance."""
    if not content_text:
        return None
    level_match = re.search(r"(黃色|橙色|紅色)燈號", content_text)
    if not level_match:
        return None
    level = {"黃色": "yellow", "橙色": "orange", "紅色": "red"}[level_match.group(1)]
    risk = WIND_LEVEL_RISK.get(level)
    if risk is None:
        return None
    average_match = re.search(r"平均風\s*(\d+)\s*級以上", content_text)
    gust_match = re.search(r"陣風\s*(\d+)\s*級以上", content_text)
    average_beaufort = int(average_match.group(1)) if average_match else None
    gust_beaufort = int(gust_match.group(1)) if gust_match else None
    return {
        "warning_level": level,
        "warning_level_label": risk["label"],
        "danger_level": risk["danger_level"],
        "average_wind_beaufort_min": average_beaufort,
        "gust_beaufort_min": gust_beaufort,
        "average_wind_speed_min_m_s": BEAUFORT_MIN_SPEED_M_S.get(average_beaufort),
        "gust_speed_min_m_s": BEAUFORT_MIN_SPEED_M_S.get(gust_beaufort),
        "crop_risk_level": risk["crop_risk_level"],
        "crop_impacts": list(risk["crop_impacts"]),
        "recommended_actions": list(risk["recommended_actions"]),
        "assessment_note": "農業風險為依 CWA 風力門檻整理的提示，並非 CWA 官方農損預測。",
    }


def _location_candidates(location_name: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if not location_name:
        return []
    values = [location_name] if isinstance(location_name, str) else list(location_name)
    candidates = []
    for value in values:
        if not value:
            continue
        value = str(value).strip()
        if not value:
            continue
        candidates.append(value)
        if value.startswith("台"):
            candidates.append("臺" + value[1:])
        elif value.startswith("臺"):
            candidates.append("台" + value[1:])
    return list(dict.fromkeys(candidates))


def _is_special_area(area: str) -> bool:
    if area in SPECIAL_AREA_LOCATIONS:
        return True
    return any(token in area for token in ("半島", "北海岸", "山區", "沿海", "空曠", "蘭嶼", "綠島"))


def _match_area(area: str, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate == area:
            return "direct"
    for candidate in candidates:
        if candidate in area or area in candidate:
            return "direct"
    special_candidates = SPECIAL_AREA_LOCATIONS.get(area, [])
    for candidate in candidates:
        if any(candidate == item or candidate in item or item in candidate for item in special_candidates):
            return "special_area"
    return None


def _location_match_details(
    areas: list[str],
    location_name: str | list[str] | tuple[str, ...] | None,
) -> dict[str, Any]:
    candidates = _location_candidates(location_name)
    if not candidates:
        return {
            "active_for_location": bool(areas),
            "matched_locations": list(areas),
            "unmatched_special_areas": [],
            "match_method": "all" if areas else None,
        }

    matched_locations = []
    matched_methods = []
    unmatched_special_areas = []
    for area in areas:
        method = _match_area(area, candidates)
        if method:
            matched_locations.append(area)
            matched_methods.append(method)
        elif _is_special_area(area):
            unmatched_special_areas.append(area)

    if not matched_locations:
        match_method = None
    elif "direct" in matched_methods:
        match_method = "direct"
    else:
        match_method = matched_methods[0]

    return {
        "active_for_location": bool(matched_locations),
        "matched_locations": list(dict.fromkeys(matched_locations)),
        "unmatched_special_areas": list(dict.fromkeys(unmatched_special_areas)),
        "match_method": match_method,
    }


def parse_weather_alerts(
    xml_text: str | bytes | None,
    location_name: str | list[str] | tuple[str, ...] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Parse CWA W-C0033 weather hazard XML into active alert records."""
    if not xml_text:
        return {
            "count": 0,
            "active_for_location": False,
            "matched_locations": [],
            "unmatched_special_areas": [],
            "match_method": None,
            "alerts": [],
        }
    root = ET.fromstring(xml_text)
    alerts = []
    all_matched_locations = []
    all_unmatched_special_areas = []
    all_match_methods = []
    dataset_elements = [element for element in root.iter() if _strip_ns(element.tag).lower() == "dataset"]
    datasets = [
        element
        for element in dataset_elements
        if not any(
            descendant is not element and _strip_ns(descendant.tag).lower() == "dataset"
            for descendant in element.iter()
        )
    ]
    if not datasets:
        datasets = [root]
    compare_now = now or datetime.now(timezone.utc)
    if compare_now.tzinfo is None:
        compare_now = compare_now.replace(tzinfo=timezone.utc)

    for dataset in datasets:
        issue_time = _text(dataset, "datasetInfo/issueTime") or _text(dataset, "DatasetInfo/IssueTime")
        start_time = _text(dataset, "datasetInfo/validTime/startTime")
        end_time = _text(dataset, "datasetInfo/validTime/endTime")
        content_text = _text(dataset, "contents/content/contentText")
        expires = _parse_dt(end_time)
        if expires is not None and expires.astimezone(timezone.utc) <= compare_now.astimezone(timezone.utc):
            continue

        for hazard in dataset.iter():
            if _strip_ns(hazard.tag) != "hazard":
                continue
            info = _first(hazard, "info")
            areas = [
                area
                for area in (_text(loc, "locationName") for loc in _all(info, "affectedAreas/location"))
                if area
            ]
            match_details = _location_match_details(areas, location_name)
            all_matched_locations.extend(match_details["matched_locations"])
            all_unmatched_special_areas.extend(match_details["unmatched_special_areas"])
            if match_details["match_method"]:
                all_match_methods.append(match_details["match_method"])
            alert = {
                "phenomena": _text(info, "phenomena"),
                "significance": _text(info, "significance"),
                "affected_areas": areas,
                "matched_locations": match_details["matched_locations"],
                "unmatched_special_areas": match_details["unmatched_special_areas"],
                "match_method": match_details["match_method"],
                "content_text": content_text,
                "issue_time": issue_time,
                "start_time": start_time,
                "end_time": end_time,
            }
            if alert["phenomena"] == "陸上強風":
                alert["wind_advisory"] = _wind_advisory(content_text)
            alerts.append(alert)
    if not all_match_methods:
        match_method = None
    elif "direct" in all_match_methods:
        match_method = "direct"
    else:
        match_method = all_match_methods[0]
    return {
        "count": len(alerts),
        "active_for_location": bool(all_matched_locations),
        "matched_locations": list(dict.fromkeys(all_matched_locations)),
        "unmatched_special_areas": list(dict.fromkeys(all_unmatched_special_areas)),
        "match_method": match_method,
        "alerts": alerts,
    }
