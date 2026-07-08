#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Parsers for CWA warning, typhoon, and hazardous-weather datasets."""
from __future__ import annotations

from datetime import datetime, timezone
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
    issue_time = _text(root, "dataset/datasetInfo/issueTime") or _text(root, "Dataset/DatasetInfo/IssueTime")
    start_time = _text(root, "dataset/datasetInfo/validTime/startTime")
    end_time = _text(root, "dataset/datasetInfo/validTime/endTime")
    content_text = _text(root, "dataset/contents/content/contentText")
    expires = _parse_dt(end_time)
    if expires is not None:
        compare_now = now or datetime.now(timezone.utc)
        if compare_now.tzinfo is None:
            compare_now = compare_now.replace(tzinfo=timezone.utc)
        if expires.astimezone(timezone.utc) <= compare_now.astimezone(timezone.utc):
            return {
                "count": 0,
                "active_for_location": False,
                "matched_locations": [],
                "unmatched_special_areas": [],
                "match_method": None,
                "alerts": [],
            }

    alerts = []
    all_matched_locations = []
    all_unmatched_special_areas = []
    all_match_methods = []
    for hazard in root.iter():
        if _strip_ns(hazard.tag) != "hazard":
            continue
        info = _first(hazard, "info")
        areas = [area for area in (_text(loc, "locationName") for loc in _all(info, "affectedAreas/location")) if area]
        match_details = _location_match_details(areas, location_name)
        all_matched_locations.extend(match_details["matched_locations"])
        all_unmatched_special_areas.extend(match_details["unmatched_special_areas"])
        if match_details["match_method"]:
            all_match_methods.append(match_details["match_method"])
        alerts.append({
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
        })
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
