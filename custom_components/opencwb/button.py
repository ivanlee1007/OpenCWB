"""Update button for OpenCWB."""
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
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
    """Set up the OpenCWB update button based on a config entry."""
    domain_data = hass.data[DOMAIN][config_entry.entry_id]
    name = domain_data[ENTRY_NAME]
    weather_coordinator = domain_data[ENTRY_WEATHER_COORDINATOR]
    location_name = domain_data[CONF_LOCATION_NAME]

    unique_id = f"{config_entry.unique_id}-{location_name}-update"
    async_add_entities(
        [OCWBUpdateButton(name, unique_id, weather_coordinator, location_name)],
        False,
    )


class OCWBUpdateButton(CoordinatorEntity[WeatherUpdateCoordinator], ButtonEntity):
    """Update button for OpenCWB weather data.

    Pressing this button triggers an immediate refresh of weather data
    from the CWB OpenData API and records the result (success/failure,
    last execution time, error message) in the entity attributes.
    """

    def __init__(
        self,
        name: str,
        unique_id: str,
        weather_coordinator: WeatherUpdateCoordinator,
        location_name: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(weather_coordinator)
        self._attr_name = f"{name} 更新天氣"
        self._attr_unique_id = unique_id
        self._weather_coordinator = weather_coordinator
        self._location_name = location_name

        # Extract entry_id from unique_id (format: {entry_unique_id}-{location_name}-update)
        parts = unique_id.rsplit("-", 2)
        self._entry_id = parts[0] if len(parts) >= 3 else unique_id

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}-{location_name}")},
            manufacturer=MANUFACTURER,
            name=f"{DEFAULT_NAME} {location_name}",
        )
        self._attr_attribution = ATTRIBUTION

        # Pre-initialise attributes so the entity is not "unavailable" before first press
        self._attr_extra_state_attributes = {
            "update_status": "待更新",
            "last_update_time": None,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates to keep attributes in sync."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._weather_coordinator.async_add_listener(self._async_update_attrs)
        )

    @callback
    def _async_update_attrs(self) -> None:
        """Sync current coordinator state to button attributes on every refresh."""
        coordinator = self._weather_coordinator
        last_ts = coordinator.last_update_success_time

        self._attr_extra_state_attributes = {
            "update_status": "成功" if coordinator.last_update_success else "失敗",
            "last_update_time": (
                dt_util.as_local(last_ts).isoformat() if last_ts else None
            ),
        }
        self.async_write_ha_state()

    async def async_press(self) -> None:
        """Handle button press: trigger immediate weather data refresh."""
        coordinator = self._weather_coordinator
        _LOGGER.debug("OpenCWB update button pressed for %s", self._location_name)

        # Capture current success time before refresh (for comparison)
        ts_before = coordinator.last_update_success_time

        # Trigger immediate refresh; any exception propagates to HA
        await coordinator.async_refresh()

        # Determine outcome
        success = coordinator.last_update_success
        now_ts = coordinator.last_update_success_time

        if success:
            status_text = "成功"
            error_text = None
        else:
            status_text = "失敗"
            # Try to capture the stored error from the coordinator
            error_text = getattr(coordinator, "_update_error", None)
            if error_text:
                error_text = str(error_text)

        self._attr_extra_state_attributes = {
            "update_status": status_text,
            "last_update_time": (
                dt_util.as_local(now_ts).isoformat() if now_ts else None
            ),
            "previous_update_time": (
                dt_util.as_local(ts_before).isoformat() if ts_before else None
            ),
        }
        if error_text:
            self._attr_extra_state_attributes["last_error"] = error_text

        self.async_write_ha_state()
