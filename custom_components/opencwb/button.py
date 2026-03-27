"""Update button for OpenCWB."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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

    # Keep the exact same device identifier formula as weather.py / sensors,
    # so the button groups under the same HA device card.
    split_unique_id = config_entry.unique_id.split("-")
    device_id = f"{split_unique_id[0]}-{split_unique_id[1]}"

    unique_id = f"{config_entry.unique_id}-{location_name}-update"
    async_add_entities(
        [
            OCWBUpdateButton(
                name=name,
                unique_id=unique_id,
                coordinator=weather_coordinator,
                device_id=device_id,
            )
        ],
        update_before_add=False,
    )


class OCWBUpdateButton(ButtonEntity):
    """Button that forces an immediate weather-data refresh."""

    def __init__(
        self,
        name: str,
        unique_id: str,
        coordinator: WeatherUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the button."""
        self._coordinator = coordinator
        self._last_update_time: str | None = None
        self._previous_update_time: str | None = None
        self._last_error: str | None = None
        self._update_status = "待更新"

        self._attr_name = f"{name} 更新天氣"
        self._attr_unique_id = unique_id
        self._attr_attribution = ATTRIBUTION
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, device_id)},
            manufacturer=MANUFACTURER,
            name=DEFAULT_NAME,
        )

    @property
    def available(self) -> bool:
        """Return True if the coordinator is available."""
        return self._coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return button execution status attributes."""
        attrs: dict[str, str | None] = {
            "update_status": self._update_status,
            "last_update_time": self._last_update_time,
            "previous_update_time": self._previous_update_time,
        }
        if self._last_error:
            attrs["last_error"] = self._last_error
        return attrs

    async def async_press(self) -> None:
        """Handle button press: trigger immediate refresh and record result."""
        _LOGGER.debug("OpenCWB update button pressed for %s", self._attr_name)

        self._previous_update_time = self._last_update_time
        self._last_error = None

        try:
            await self._coordinator.async_refresh()
            if self._coordinator.last_update_success:
                self._update_status = "成功"
                self._last_update_time = dt_util.now().isoformat()
            else:
                self._update_status = "失敗"
                self._last_error = "refresh finished but coordinator reported failure"
        except Exception as ex:  # noqa: BLE001
            self._update_status = "失敗"
            self._last_error = str(ex)
            _LOGGER.exception("OpenCWB update button failed")

        self.async_write_ha_state()
