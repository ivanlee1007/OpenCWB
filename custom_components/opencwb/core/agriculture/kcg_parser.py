"""Parsers for optional 高雄農來訊 agricultural data."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any, Iterable

KCG_TIMEZONE = timezone(timedelta(hours=8))


class KCGDataError(ValueError):
    """Raised when the provider returns an application-level error."""

    def __init__(self, message: str, *, code: str = "invalid_response") -> None:
        super().__init__(message)
        self.code = code


def is_successful_agriculture_cache(snapshot: dict[str, Any] | None) -> bool:
    """Return true only for snapshots produced by a completed provider update."""
    return bool(isinstance(snapshot, dict) and snapshot.get("last_success_at"))


def parse_business_payload(payload: str | dict[str, Any]) -> dict[str, Any]:
    """Decode a KCG payload and enforce its HTTP-200 business status."""
    for _ in range(2):
        if not isinstance(payload, str):
            break
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as error:
            raise KCGDataError(
                "Invalid agricultural provider response", code="malformed_response"
            ) from error
    if not isinstance(payload, dict):
        raise KCGDataError(
            "Invalid agricultural provider response", code="malformed_response"
        )

    if "Status" not in payload and "status" not in payload:
        raise KCGDataError(
            "Invalid agricultural provider response", code="malformed_response"
        )
    status = payload.get("Status", payload.get("status"))
    valid_status = (
        type(status) is int and status == 200
    ) or (
        type(status) is str and status == "200"
    )
    if not valid_status:
        provider_message = str(payload.get("Message", payload.get("message", "")))
        code = "unauthorized" if "token" in provider_message.lower() else "business_error"
        raise KCGDataError("Agricultural provider rejected the request", code=code)
    return payload


def _text(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _place_name(value: Any) -> str | None:
    """Normalize Taiwan place-name variants without broad fuzzy matching."""
    if value is None:
        return None
    normalized = str(value).strip().replace("台", "臺")
    return normalized or None


def _parse_source_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KCG_TIMEZONE)
    return parsed.astimezone(timezone.utc)


def _note(row: dict[str, Any]) -> int | None:
    try:
        return int(row.get("Note"))
    except (TypeError, ValueError):
        return None


def _normalize_item(row: dict[str, Any]) -> dict[str, Any]:
    note = _note(row)
    if note is None:
        classification = "unknown"
    elif note <= 5:
        classification = "warning"
    else:
        classification = "advisory"
    return {
        "classification": classification,
        "note": note,
        "city": _text(row, "CITY_NAME"),
        "town": _text(row, "TOWN_NAME"),
        "crop": _text(row, "C_NAME"),
        "disaster": _text(row, "Disaster"),
        "growth": _text(row, "GROWTH"),
        "stage": _text(row, "STAGE"),
        "duration": _text(row, "DURATION"),
        "threshold": _text(row, "THRESHOLD"),
        "measures": _text(row, "MEASURES"),
        "real_value": _text(row, "REAL_VALUE"),
        "effect": _text(row, "EFFECT"),
        "prevention": _text(row, "PREVENTION"),
        "recovery": _text(row, "RECOVERY"),
        "timestamp": _text(row, "TIMESTAMP"),
    }


def build_agriculture_snapshot(
    rows: Iterable[dict[str, Any]],
    *,
    city: str,
    town: str | None = None,
    crop: str | None = None,
    growth_stage: str | None = None,
    supported_crops: set[str] | None = None,
    now: datetime | None = None,
    stale_after_hours: int = 30,
) -> dict[str, Any]:
    """Filter provider rows and return a concise HA-safe agricultural snapshot."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    supported = not crop or supported_crops is None or crop in supported_crops
    if not supported:
        return {
            "status": "unsupported",
            "supported": False,
            "warning_active": False,
            "advisory_active": False,
            "warning_count": 0,
            "advisory_count": 0,
            "matched_total": 0,
            "items": [],
            "items_truncated": False,
            "source_timestamp": None,
            "stale": False,
            "timestamp_invalid": False,
        }

    matched: list[dict[str, Any]] = []
    for row in rows:
        if _place_name(row.get("CITY_NAME")) != _place_name(city):
            continue
        if town and _place_name(row.get("TOWN_NAME")) != _place_name(town):
            continue
        if crop and _text(row, "C_NAME") != crop:
            continue
        if growth_stage:
            stages = {_text(row, "GROWTH"), _text(row, "STAGE")}
            if growth_stage not in stages:
                continue
        matched.append(_normalize_item(row))

    now_utc = now.astimezone(timezone.utc)
    source_times = []
    for item in matched:
        parsed = _parse_source_time(item.get("timestamp"))
        future = bool(parsed and parsed > now_utc)
        source_age = now_utc - parsed if parsed is not None and not future else None
        item["timestamp_invalid"] = parsed is None or future
        item["stale"] = (
            source_age is not None and source_age > timedelta(hours=stale_after_hours)
        )
        item["fresh"] = bool(
            parsed is not None and not future and not item["stale"]
        )
        if parsed is not None and not future:
            source_times.append((item.get("timestamp"), parsed))
    latest_raw = max(source_times, key=lambda item: item[1])[0] if source_times else None
    warning_count = sum(item["classification"] == "warning" for item in matched)
    advisory_count = sum(item["classification"] == "advisory" for item in matched)
    fresh_warnings = [
        item for item in matched
        if item["classification"] == "warning" and item["fresh"]
    ]
    fresh_advisories = [
        item for item in matched
        if item["classification"] == "advisory" and item["fresh"]
    ]
    fresh_warning_count = len(fresh_warnings)
    fresh_advisory_count = len(fresh_advisories)
    notification_item = (
        fresh_warnings[0]
        if fresh_warnings
        else fresh_advisories[0] if fresh_advisories else None
    )
    timestamp_invalid = any(item["timestamp_invalid"] for item in matched)
    stale = bool(matched) and all(item["stale"] for item in matched)

    if not matched:
        status = "no_data"
    elif fresh_warning_count:
        status = "warning"
    elif fresh_advisory_count:
        status = "advisory"
    elif timestamp_invalid:
        status = "unknown"
    elif stale:
        status = "stale"
    else:
        status = "unknown"

    return {
        "status": status,
        "supported": True,
        "warning_active": fresh_warning_count > 0,
        "advisory_active": fresh_advisory_count > 0,
        "warning_count": warning_count,
        "advisory_count": advisory_count,
        "matched_total": len(matched),
        "items": matched[:25],
        "items_truncated": len(matched) > 25,
        "_notification_item": notification_item,
        "source_timestamp": latest_raw,
        "stale": stale,
        "timestamp_invalid": timestamp_invalid,
    }


def _first_number(data: Any, names: tuple[str, ...]) -> float | None:
    rows = data if isinstance(data, list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for name in names:
            value = row.get(name)
            try:
                if value not in (None, ""):
                    return float(value)
            except (TypeError, ValueError):
                continue
    return None


def _optional_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    try:
        return parse_business_payload(payload)
    except KCGDataError:
        return None


def build_agriculture_notification(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build a stable notification payload without claiming CWA authorship."""
    status = snapshot.get("status") or "unavailable"
    base = {
        "active": False,
        "status": status,
        "severity": "info",
        "title": "🌱 農業氣象補充資訊",
        "summary": "沒有有效的作物告警",
        "message": "目前沒有可用的作物專屬農業告警。",
        "source_provider": "高雄農來訊",
        "source_dataset": "kcg_agri_cropweather_taiwan",
        "official_cwa_alert": False,
        "derived_by_opencwa": False,
    }
    if status in (
        "unsupported", "stale", "unavailable", "no_data", "unknown", "not_configured"
    ):
        labels = {
            "unsupported": "設定作物沒有平台專屬資料",
            "stale": "農業補充資料已過期",
            "unavailable": "農業補充資料目前無法取得",
            "no_data": "目前沒有相符的作物專屬資料；不代表沒有農業風險",
            "unknown": "農業補充資料格式或時間無法確認",
            "not_configured": "尚未設定作物，未查詢農業補充資料",
        }
        base.update({"summary": labels[status], "message": labels[status]})
        return base

    selected = snapshot.get("_notification_item")
    if selected is None:
        base["status"] = "inactive"
        return base

    is_warning = selected.get("classification") == "warning"
    crop = selected.get("crop") or "作物"
    disaster = selected.get("disaster") or "氣象風險"
    level = "農業警戒" if is_warning else "生產注意"
    lines = [
        f"地點：{selected.get('city') or '-'} {selected.get('town') or ''}".rstrip(),
        f"作物：{crop}",
    ]
    if selected.get("growth") or selected.get("stage"):
        lines.append(f"生育期：{selected.get('growth') or selected.get('stage')}")
    if selected.get("effect"):
        lines.append(f"可能影響：{selected['effect']}")
    if selected.get("prevention"):
        lines.append(f"防範建議：{selected['prevention']}")
    if selected.get("recovery"):
        lines.append(f"復耕建議：{selected['recovery']}")
    if selected.get("timestamp"):
        lines.append(f"資料時間：{selected['timestamp']}")
    base.update({
        "active": True,
        "status": "active",
        "severity": "warning" if is_warning else "advisory",
        "title": f"⚠️ {crop}－{disaster}{level}" if is_warning else f"🌱 {crop}－{disaster}{level}",
        "summary": f"{crop}－{disaster}{level}",
        "message": "\n".join(lines),
        "warning_count": snapshot.get("warning_count", 0),
        "advisory_count": snapshot.get("advisory_count", 0),
        "source_timestamp": snapshot.get("source_timestamp"),
    })
    return base


def parse_irrigation_reference(
    *,
    et0_payload: dict[str, Any] | None,
    kc_payload: dict[str, Any] | None = None,
    etc_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize optional ET0/Kc/ETc values without converting missing data to zero."""
    et0_data = _optional_payload(et0_payload)
    kc_data = _optional_payload(kc_payload)
    etc_data = _optional_payload(etc_payload)
    et0 = _first_number((et0_data or {}).get("Data"), ("Et0", "ET0", "et0"))
    kc = _first_number((kc_data or {}).get("Data"), ("Kc", "KC", "kc"))
    etc = _first_number((etc_data or {}).get("Data"), ("Etc", "ETC", "etc"))
    water = _first_number(
        (etc_data or {}).get("Data"),
        ("WaterRequirement", "WATER_REQUIREMENT", "waterRequirement"),
    )
    return {
        "available": any(
            value is not None for value in (et0, kc, etc, water)
        ),
        "et0": et0,
        "kc": kc,
        "etc": etc,
        "water_requirement": water,
        "source_longitude": (et0_data or {}).get("Lon"),
        "source_latitude": (et0_data or {}).get("Lat"),
        "crop_water_supported": kc is not None or etc is not None or water is not None,
    }
