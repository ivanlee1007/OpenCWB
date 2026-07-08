"""Binary sensors for CWA warning states."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    ATTRIBUTION,
    ATTR_TYPHOON_WARNING,
    ATTR_TYPHOON_WARNING_STATUS,
    ATTR_WEATHER_ALERT,
    ATTR_WEATHER_ALERTS,
    CONF_LOCATION_NAME,
    DEFAULT_NAME,
    DOMAIN,
    ENTRY_NAME,
    ENTRY_WARNING_COORDINATOR,
    MANUFACTURER,
)


async def async_setup_entry(hass, config_entry, async_add_entities) -> None:
    """Set up OpenCWB binary warning sensors."""
    domain_data = hass.data[DOMAIN][config_entry.entry_id]
    warning_coordinator = domain_data.get(ENTRY_WARNING_COORDINATOR)
    if warning_coordinator is None or not warning_coordinator.any_enabled:
        return

    name = domain_data[ENTRY_NAME]
    location_name = domain_data[CONF_LOCATION_NAME]
    entities = []
    if warning_coordinator.enable_typhoon_warning:
        entities.append(
            OpenCWBWarningBinarySensor(
                f"{name} {location_name} Typhoon Warning",
                f"{config_entry.unique_id}-typhoon-warning-{location_name}",
                ATTR_TYPHOON_WARNING,
                ATTR_TYPHOON_WARNING_STATUS,
                warning_coordinator,
            )
        )
    if warning_coordinator.enable_weather_alerts:
        entities.append(
            OpenCWBWarningBinarySensor(
                f"{name} {location_name} Weather Alert",
                f"{config_entry.unique_id}-weather-alert-{location_name}",
                ATTR_WEATHER_ALERT,
                ATTR_WEATHER_ALERTS,
                warning_coordinator,
            )
        )
    async_add_entities(entities)


class OpenCWBWarningBinarySensor(BinarySensorEntity):
    """Binary sensor for active warning states."""

    _attr_attribution = ATTRIBUTION
    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(self, name, unique_id, state_key, attrs_key, coordinator):
        self._attr_name = name.replace("_", " ")
        self._attr_unique_id = unique_id
        self._state_key = state_key
        self._attrs_key = attrs_key
        self._coordinator = coordinator
        split_unique_id = unique_id.split("-")
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, f"{split_unique_id[0]}-{split_unique_id[1]}")},
            manufacturer=MANUFACTURER,
            name=DEFAULT_NAME,
        )

    @property
    def should_poll(self):
        """Return False; coordinator drives updates."""
        return False

    @property
    def available(self):
        """Return availability."""
        return self._coordinator.last_update_success

    @property
    def is_on(self):
        """Return true when the corresponding warning is active."""
        return bool(self._coordinator.data.get(self._state_key, False))

    @property
    def extra_state_attributes(self):
        """Expose warning metadata on the binary sensor too."""
        attrs = {ATTR_ATTRIBUTION: ATTRIBUTION}
        data = self._coordinator.data.get(self._attrs_key)
        if isinstance(data, dict):
            attrs.update(data)
        return attrs

    async def async_added_to_hass(self):
        """Subscribe to coordinator updates."""
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """Request refresh."""
        await self._coordinator.async_request_refresh()
