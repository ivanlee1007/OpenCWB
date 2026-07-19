"""Binary sensors for CWA warning states."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    ATTR_AGRICULTURE,
    ATTR_AGRICULTURE_ADVISORY,
    ATTR_AGRICULTURE_SUPPORTED,
    ATTR_AGRICULTURE_WARNING,
    ATTRIBUTION,
    ATTR_TYPHOON_WARNING,
    ATTR_TYPHOON_WARNING_STATUS,
    ATTR_WEATHER_ALERT,
    ATTR_WEATHER_ALERTS,
    CONF_LOCATION_NAME,
    DEFAULT_NAME,
    DOMAIN,
    ENTRY_NAME,
    ENTRY_AGRICULTURE_COORDINATOR,
    ENTRY_WARNING_COORDINATOR,
    MANUFACTURER,
)
from .agriculture_state import agriculture_binary_available


async def async_setup_entry(hass, config_entry, async_add_entities) -> None:
    """Set up OpenCWB binary warning sensors."""
    domain_data = hass.data[DOMAIN][config_entry.entry_id]
    warning_coordinator = domain_data.get(ENTRY_WARNING_COORDINATOR)
    name = domain_data[ENTRY_NAME]
    location_name = domain_data[CONF_LOCATION_NAME]
    entities = []
    if warning_coordinator is not None and warning_coordinator.enable_typhoon_warning:
        entities.append(
            OpenCWBWarningBinarySensor(
                f"{name} {location_name} Typhoon Warning",
                f"{config_entry.unique_id}-typhoon-warning-{location_name}",
                ATTR_TYPHOON_WARNING,
                ATTR_TYPHOON_WARNING_STATUS,
                warning_coordinator,
            )
        )
    if warning_coordinator is not None and warning_coordinator.enable_weather_alerts:
        entities.append(
            OpenCWBWarningBinarySensor(
                f"{name} {location_name} Weather Alert",
                f"{config_entry.unique_id}-weather-alert-{location_name}",
                ATTR_WEATHER_ALERT,
                ATTR_WEATHER_ALERTS,
                warning_coordinator,
            )
        )
    agriculture_coordinator = domain_data.get(ENTRY_AGRICULTURE_COORDINATOR)
    if entities:
        async_add_entities(entities)
    if agriculture_coordinator is not None:
        for profile_id, profile in agriculture_coordinator.crop_profiles.items():
            crop_name = profile["crop_name"]
            device_id = f"{config_entry.unique_id}-agriculture-{profile_id}"
            async_add_entities(
                [
                    OpenCWBWarningBinarySensor(
                        f"{name} {location_name} {crop_name} Crop Warning",
                        f"{config_entry.unique_id}-agriculture-{profile_id}-crop-warning",
                        ATTR_AGRICULTURE_WARNING,
                        ATTR_AGRICULTURE,
                        agriculture_coordinator,
                        agriculture=True,
                        profile_id=profile_id,
                        crop_name=crop_name,
                        device_id=device_id,
                    ),
                    OpenCWBWarningBinarySensor(
                        f"{name} {location_name} {crop_name} Crop Advisory",
                        f"{config_entry.unique_id}-agriculture-{profile_id}-crop-advisory",
                        ATTR_AGRICULTURE_ADVISORY,
                        ATTR_AGRICULTURE,
                        agriculture_coordinator,
                        agriculture=True,
                        profile_id=profile_id,
                        crop_name=crop_name,
                        device_id=device_id,
                    ),
                    OpenCWBWarningBinarySensor(
                        f"{name} {location_name} {crop_name} Crop Data Supported",
                        f"{config_entry.unique_id}-agriculture-{profile_id}-crop-supported",
                        ATTR_AGRICULTURE_SUPPORTED,
                        ATTR_AGRICULTURE,
                        agriculture_coordinator,
                        agriculture=True,
                        profile_id=profile_id,
                        crop_name=crop_name,
                        device_id=device_id,
                    ),
                ],
                config_subentry_id=profile_id,
            )


class OpenCWBWarningBinarySensor(BinarySensorEntity):
    """Binary sensor for active warning states."""

    _attr_attribution = ATTRIBUTION
    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(
        self,
        name,
        unique_id,
        state_key,
        attrs_key,
        coordinator,
        *,
        agriculture=False,
        profile_id=None,
        crop_name=None,
        device_id=None,
    ):
        self._attr_name = name.replace("_", " ")
        self._attr_unique_id = unique_id
        self._state_key = state_key
        self._attrs_key = attrs_key
        self._coordinator = coordinator
        self._agriculture = agriculture
        self._profile_id = profile_id
        if profile_id is not None:
            self._attr_config_subentry_id = profile_id
        self._source_attribution = (
            "Agricultural guidance provided by 高雄農來訊"
            if agriculture
            else ATTRIBUTION
        )
        self._attr_attribution = self._source_attribution
        split_unique_id = unique_id.split("-")
        base_device_id = f"{split_unique_id[0]}-{split_unique_id[1]}"
        resolved_device_id = device_id or (
            f"{base_device_id}-agriculture" if agriculture else base_device_id
        )
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, resolved_device_id)},
            manufacturer="OpenCWA with 高雄農來訊" if agriculture else MANUFACTURER,
            name=(
                f"OpenCWA 農業氣象補充 - {crop_name}"
                if agriculture and crop_name
                else "OpenCWA 農業氣象補充"
                if agriculture
                else DEFAULT_NAME
            ),
        )

    @property
    def should_poll(self):
        """Return False; coordinator drives updates."""
        return False

    def _coordinator_data(self):
        data = self._coordinator.data or {}
        if self._agriculture and self._profile_id is not None:
            return data.get(self._profile_id) or {}
        return data

    @property
    def available(self):
        """Return availability without treating stale agriculture as a safe off."""
        if not self._coordinator.last_update_success:
            return False
        if self._agriculture:
            snapshot = self._coordinator_data().get(ATTR_AGRICULTURE)
            return agriculture_binary_available(snapshot, self._state_key)
        return True

    @property
    def is_on(self):
        """Return true when the corresponding warning is active."""
        return bool(self._coordinator_data().get(self._state_key, False))

    @property
    def extra_state_attributes(self):
        """Expose warning metadata on the binary sensor too."""
        attrs = {ATTR_ATTRIBUTION: self._source_attribution}
        if self._profile_id is not None:
            attrs["crop_profile_id"] = self._profile_id
        data = self._coordinator_data().get(self._attrs_key)
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
