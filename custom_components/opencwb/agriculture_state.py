"""Pure Home Assistant entity-state semantics for optional agriculture data."""
from __future__ import annotations

from typing import Any

CONFIRMED_AGRICULTURE_STATUSES = {"warning", "advisory", "clear"}
TEXTUAL_AGRICULTURE_STATUSES = CONFIRMED_AGRICULTURE_STATUSES | {
    "unsupported",
    "no_data",
    "unknown",
    "not_configured",
    "unavailable",
    "stale",
}
IRRIGATION_SENSOR_TYPES = {
    "agriculture_et0",
    "agriculture_kc",
    "agriculture_etc",
    "agriculture_water_requirement",
}


def agriculture_binary_available(
    snapshot: dict[str, Any] | None,
    state_key: str,
) -> bool:
    """Return whether a binary state is confirmed rather than merely false."""
    if not isinstance(snapshot, dict):
        return False
    if snapshot.get("provider_available") is not True or snapshot.get("stale"):
        return False
    status = snapshot.get("status")
    if state_key == "agriculture_supported":
        return type(snapshot.get("supported")) is bool
    return status in CONFIRMED_AGRICULTURE_STATUSES


def agriculture_sensor_available(
    snapshot: dict[str, Any] | None,
    sensor_type: str,
    value: Any,
    *,
    irrigation: dict[str, Any] | None = None,
) -> bool:
    """Expose explicit textual states while keeping numeric values fail-safe."""
    if not isinstance(snapshot, dict):
        return False
    status = snapshot.get("status")
    if sensor_type not in IRRIGATION_SENSOR_TYPES:
        return status in TEXTUAL_AGRICULTURE_STATUSES
    if snapshot.get("provider_available") is not True or snapshot.get("stale"):
        return False
    irrigation_available = (
        isinstance(irrigation, dict) and irrigation.get("available") is True
    )
    return irrigation_available and value is not None
