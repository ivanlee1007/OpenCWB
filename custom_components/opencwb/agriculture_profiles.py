"""Dependency-free crop profile helpers for optional agriculture."""
from __future__ import annotations

from typing import Any, Mapping

SUBENTRY_TYPE_CROP = "crop"
CONF_CROP_NAME = "crop_name"
CONF_GROWTH_STAGE = "growth_stage"
CONF_PLANTING_DATE = "planting_date"
CONF_AREA_HECTARES = "area_hectares"
CONF_MIGRATION_WARNING = "migration_warning"
CONF_LEGACY_AREA_HECTARES = "legacy_area_hectares"
LEGACY_CROP_FIELDS = (
    CONF_CROP_NAME,
    CONF_GROWTH_STAGE,
    CONF_PLANTING_DATE,
    CONF_AREA_HECTARES,
)


def normalize_crop_profile(data: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize and validate one persistent crop profile."""
    crop_name = str(data.get(CONF_CROP_NAME) or "").strip()
    if not crop_name:
        raise ValueError("crop_name is required")

    growth_stage = str(data.get(CONF_GROWTH_STAGE) or "").strip()
    planting_date = str(data.get(CONF_PLANTING_DATE) or "").strip()
    raw_area = data.get(CONF_AREA_HECTARES)
    try:
        area = float(raw_area) if raw_area not in (None, "") else None
    except (TypeError, ValueError) as error:
        raise ValueError("area_hectares must be a number") from error
    if area is not None and area < 0:
        raise ValueError("area_hectares must not be negative")
    if area == 0:
        area = None

    return {
        CONF_CROP_NAME: crop_name,
        CONF_GROWTH_STAGE: growth_stage,
        CONF_PLANTING_DATE: planting_date,
        CONF_AREA_HECTARES: area,
    }


def _subentry_value(subentry: Any, key: str, default: Any = None) -> Any:
    if isinstance(subentry, Mapping):
        return subentry.get(key, default)
    return getattr(subentry, key, default)


def crop_profiles_from_subentries(subentries: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return stable profile-id to crop-profile mapping from HA subentries."""
    profiles: dict[str, dict[str, Any]] = {}
    for profile_id, subentry in subentries.items():
        if _subentry_value(subentry, "subentry_type") != SUBENTRY_TYPE_CROP:
            continue
        raw_data = _subentry_value(subentry, "data", {})
        try:
            profiles[str(profile_id)] = normalize_crop_profile(raw_data)
        except ValueError:
            # Invalid persisted records stay isolated and cannot break CWA setup.
            continue
    return profiles


def legacy_crop_profile(
    data: Mapping[str, Any], options: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Read the effective legacy single-crop fields before v2 migration."""
    crop_name = options.get(CONF_CROP_NAME, data.get(CONF_CROP_NAME, ""))
    if not str(crop_name or "").strip():
        return None
    raw = {
        key: options[key] if key in options else data.get(key)
        for key in LEGACY_CROP_FIELDS
    }
    return normalize_crop_profile(raw)


def legacy_crop_profile_with_recovery(
    data: Mapping[str, Any], options: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, bool]:
    """Build a valid legacy profile and preserve malformed area for UI repair."""
    raw = {
        key: options[key] if key in options else data.get(key)
        for key in LEGACY_CROP_FIELDS
    }
    if not str(raw.get(CONF_CROP_NAME) or "").strip():
        return None, False
    try:
        return normalize_crop_profile(raw), False
    except ValueError:
        recovered = normalize_crop_profile(
            {
                **raw,
                CONF_AREA_HECTARES: None,
            }
        )
        recovered[CONF_MIGRATION_WARNING] = "invalid_legacy_area"
        recovered[CONF_LEGACY_AREA_HECTARES] = raw.get(CONF_AREA_HECTARES)
        return recovered, True


def without_legacy_crop_fields(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return parent config values without migrated crop-specific fields."""
    return {key: value for key, value in values.items() if key not in LEGACY_CROP_FIELDS}


def find_equivalent_crop_profile(
    subentries: Mapping[str, Any], profile: Mapping[str, Any]
) -> str | None:
    """Return the stable ID of a crop subentry with equivalent normalized data."""
    normalized_target = normalize_crop_profile(profile)
    target_warning = profile.get(CONF_MIGRATION_WARNING)
    target_legacy_area = profile.get(CONF_LEGACY_AREA_HECTARES)
    for subentry_id, subentry in subentries.items():
        if _subentry_value(subentry, "subentry_type") != SUBENTRY_TYPE_CROP:
            continue
        raw_existing = _subentry_value(subentry, "data", {})
        try:
            existing = normalize_crop_profile(raw_existing)
        except ValueError:
            continue
        if existing != normalized_target:
            continue
        if target_warning is not None and (
            raw_existing.get(CONF_MIGRATION_WARNING) != target_warning
            or raw_existing.get(CONF_LEGACY_AREA_HECTARES) != target_legacy_area
        ):
            continue
        if target_warning is None and raw_existing.get(CONF_MIGRATION_WARNING) is not None:
            continue
        return str(subentry_id)
    return None


def legacy_agriculture_unique_id(
    unique_id: str, base_id: str, subentry_id: str
) -> str | None:
    """Map a pre-v2 agriculture unique ID to its stable crop subentry ID."""
    sensor_types = (
        "agriculture_notification",
        "agriculture_water_requirement",
        "agriculture_supported",
        "agriculture_advisory",
        "agriculture_warning",
        "agriculture_et0",
        "agriculture_etc",
        "agriculture_kc",
        "agriculture",
    )
    for sensor_type in sensor_types:
        if f"-agriculture-{sensor_type}-" in unique_id:
            return f"{base_id}-agriculture-{subentry_id}-{sensor_type}"
    binary_types = {
        "-crop-warning-": "crop-warning",
        "-crop-advisory-": "crop-advisory",
        "-crop-supported-": "crop-supported",
    }
    for marker, entity_type in binary_types.items():
        if marker in unique_id:
            return f"{base_id}-agriculture-{subentry_id}-{entity_type}"
    return None
