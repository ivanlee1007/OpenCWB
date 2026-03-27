"""Update button for OpenCWB.

Attaches as a button entity under the same device as the weather and sensor
entities. Pressing the button triggers an immediate weather-data refresh and
records the outcome (success / failure, timestamps, error message) in the
entity attributes.
"""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    ATTRIBUTION,
    CONF_LOCATION_NAME,
    DEFAULT_NAME,
    DOMAIN,
    ENTRY_NAME,
    ENTRY_WEATHER_COORDINATOR,
    MANUFACTURER,
)
from .weather_update_coordinator import WeatherUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the OpenCWB update button for one location."""
    domain_data = hass.data[DOMAIN][config_entry.entry_id]
    name = domain_data[ENTRY_NAME]
    weather_coordinator: WeatherUpdateCoordinator = domain_data[ENTRY_WEATHER_COORDINATOR]
    location_name = domain_data[CONF_LOCATION_NAME]

    # Derive the device identifier using the SAME formula as weather.py
    # and abstract_ocwb_sensor.py:
    #   split unique_id "-" → first two parts = "{lat}-{lon}"
    split_unique_id = config_entry.unique_id.split("-")
    device_id = f"{split_unique_id[0]}-{split_unique_id[1]}"

    unique_id = f"{config_entry.unique_id}-{location_name}-update"
    async_add_entities(
        [
            OCWBUpdateButton(
                name=name,
                unique_id=unique_id,
                coordinator=weather_coordinator,
                location_name=location_name,
                device_id=device_id,
            )
        ],
        update_before_add=False,
    )


class OCWBUpdateButton(ButtonEntity):
    """Button that forces an immediate weather-data refresh.

    Grouped under the same device as the weather and sensor entities.
    After each press the entity attributes show:
      - update_status  : "成功" / "失敗"
      - last_update_time: ISO datetime of the latest successful refresh
      - last_error      : error message if the last refresh failed (absent on success)
    """

    def __init__(
        self,
        name: str,
        unique_id: str,
        coordinator: WeatherUpdateCoordinator,
        location_name: str,
        device_id: str,
    ) -> None:
        """Initialize the button."""
        # Base entity attributes
        self._attr_name = f"{name} 更新天氣"
        self._attr_unique_id = unique_id
        self._attr_attribution = ATTRIBUTION

        # Device info — same identifier as weather.py / sensors, so HA groups them
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, device_id)},
            manufacturer=MANUFACTURER,
            name=DEFAULT_NAME,
        )

        # Coordinator reference (direct composition, no mixin to avoid MRO issues)
        self._coordinator = coordinator

        # Pre-initialise attributes so the entity is not "unavailable" before first press
        self._attr_extra_state_attributes = {
            "update_status": "待更新",
            "last_update_time": None,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates so attributes stay in sync."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._coordinator.async_add_listener(self._sync_attrs)
        )

    @callback
    def _sync_attrs(self) -> None:
        """Sync coordinator state → entity attributes on every refresh."""
        last_ts = self._coordinator.last_update_success_time
        self._attr_extra_state_attributes = {
            "update_status": "成功" if self._coordinator.last_update_success else "失敗",
            "last_update_time": (
                dt_util.as_local(last_ts).isoformat() if last_ts else None
            ),
        }
        self.async_write_ha_state()

    async def async_press(self) -> None:
        """Handle button press: trigger immediate refresh and record result."""
        _LOGGER.debug("OpenCWB update button pressed for %s", self._attr_name)

        ts_before = self._coordinator.last_update_success_time

        # Refresh and capture any error
        error_msg: str | None = None
        try:
            await self._coordinator.async_refresh()
        except Exception as ex:  # noqa: BLE001
            error_msg = str(ex)
            _LOGGER.warning("OpenCWB update failed: %s", ex)

        # Determine final state after refresh attempt
        success = self._coordinator.last_update_success
        now_ts = self._coordinator.last_update_success_time

        attrs = {
            "update_status": "成功" if success else "失敗",
            "last_update_time": (
                dt_util.as_local(now_ts).isoformat() if now_ts else None
            ),
            "previous_update_time": (
                dt_util.as_local(ts_before).isoformat() if ts_before else None
            ),
        }
        if error_msg:
            attrs["last_error"] = error_msg
        elif not success:
            # No exception but update still failed (e.g. API error stored in coordinator)
            coordinator_error = getattr(self._coordinator, "_update_error", None)
            if coordinator_error:
                attrs["last_error"] = str(coordinator_error)

        self._attr_extra_state_attributes = attrs
        self.async_write_ha_state()
