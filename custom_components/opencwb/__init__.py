"""The OpenCWB component."""
import asyncio
import logging
from types import MappingProxyType
import uuid

from .core.ocwb import OCWB
from .core.utils.config import get_default_config

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MODE,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .agriculture_profiles import (
    SUBENTRY_TYPE_CROP,
    crop_profiles_from_subentries,
    find_equivalent_crop_profile,
    legacy_agriculture_unique_id,
    legacy_crop_profile_with_recovery,
    without_legacy_crop_fields,
)
from .const import (
    CONF_AGRICULTURE_TOKEN,
    CONF_CROP_NAME,
    CONF_ENABLE_AGRICULTURE_ADVISORIES,
    CONF_ENABLE_TROPICAL_CYCLONE_TRACK,
    CONF_ENABLE_TYPHOON_WARNING,
    CONF_ENABLE_WEATHER_ALERTS,
    CONF_LANGUAGE,
    CONF_LOCATION_NAME,
    # CONFIG_FLOW_VERSION,
    DEFAULT_ENABLE_AGRICULTURE_ADVISORIES,
    DEFAULT_ENABLE_TROPICAL_CYCLONE_TRACK,
    DEFAULT_ENABLE_TYPHOON_WARNING,
    DEFAULT_ENABLE_WEATHER_ALERTS,
    DEFAULT_FORECAST_MODE,
    DEFAULT_LANGUAGE,
    DOMAIN,
    ENTRY_NAME,
    ENTRY_AGRICULTURE_COORDINATOR,
    ENTRY_WARNING_COORDINATOR,
    ENTRY_WEATHER_COORDINATOR,
    # FORECAST_MODE_FREE_DAILY,
    # FORECAST_MODE_ONECALL_DAILY,
    PLATFORMS,
    UPDATE_LISTENER,
)
from .weather_update_coordinator import WeatherUpdateCoordinator
from .warning_update_coordinator import WarningUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the OpenCWB component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate one legacy crop without allowing optional data to block CWA."""
    if config_entry.version >= 2:
        return True
    if config_entry.version != 1:
        _LOGGER.error("Unsupported OpenCWA config entry version %s", config_entry.version)
        return False

    profile, recovered = legacy_crop_profile_with_recovery(
        config_entry.data, config_entry.options
    )

    target_subentry = None
    created_subentry = False
    if profile is not None:
        equivalent_id = find_equivalent_crop_profile(
            config_entry.subentries, profile
        )
        if equivalent_id is not None:
            target_subentry = config_entry.subentries[equivalent_id]

        if target_subentry is None:
            target_subentry = ConfigSubentry(
                data=MappingProxyType(profile),
                subentry_type=SUBENTRY_TYPE_CROP,
                title=(
                    f"⚠ {profile[CONF_CROP_NAME]}"
                    if recovered
                    else profile[CONF_CROP_NAME]
                ),
                unique_id=uuid.uuid4().hex,
            )
            hass.config_entries.async_add_subentry(config_entry, target_subentry)
            created_subentry = True

        if not _migrate_legacy_agriculture_registry_entries(
            hass, config_entry, target_subentry.subentry_id, profile[CONF_CROP_NAME]
        ):
            if created_subentry:
                hass.config_entries.async_remove_subentry(
                    config_entry, target_subentry.subentry_id
                )
            _LOGGER.error(
                "Legacy agriculture registry migration was rolled back; retrying later"
            )
            return False
    else:
        _remove_unmapped_legacy_agriculture_registry_entries(hass, config_entry)

    hass.config_entries.async_update_entry(
        config_entry,
        data=without_legacy_crop_fields(config_entry.data),
        options=without_legacy_crop_fields(config_entry.options),
        version=2,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Set up OpenCWB as config entry."""
    name = config_entry.data[CONF_NAME]
    api_key = config_entry.data[CONF_API_KEY]
    location_name = config_entry.data.get(CONF_LOCATION_NAME, None)
    latitude = config_entry.data.get(CONF_LATITUDE, hass.config.latitude)
    longitude = config_entry.data.get(CONF_LONGITUDE, hass.config.longitude)
    forecast_mode = _get_config_value(
        config_entry, CONF_MODE, DEFAULT_FORECAST_MODE)
    language = _get_config_value(config_entry, CONF_LANGUAGE, DEFAULT_LANGUAGE)
    enable_typhoon_warning = _get_config_value(
        config_entry, CONF_ENABLE_TYPHOON_WARNING, DEFAULT_ENABLE_TYPHOON_WARNING)
    enable_tropical_cyclone_track = _get_config_value(
        config_entry,
        CONF_ENABLE_TROPICAL_CYCLONE_TRACK,
        DEFAULT_ENABLE_TROPICAL_CYCLONE_TRACK,
    )
    enable_weather_alerts = _get_config_value(
        config_entry, CONF_ENABLE_WEATHER_ALERTS, DEFAULT_ENABLE_WEATHER_ALERTS)
    enable_agriculture_advisories = _get_config_value(
        config_entry,
        CONF_ENABLE_AGRICULTURE_ADVISORIES,
        DEFAULT_ENABLE_AGRICULTURE_ADVISORIES,
    )
    agriculture_token = _get_config_value(config_entry, CONF_AGRICULTURE_TOKEN, "")
    crop_profiles = crop_profiles_from_subentries(config_entry.subentries)
    _remove_invalid_crop_registry_entries(
        hass, config_entry, set(crop_profiles)
    )

    config_dict = _get_ocwb_config(language)

    ocwb = OCWB(api_key, config_dict).weather_manager()
    weather_coordinator = WeatherUpdateCoordinator(
        ocwb, location_name, latitude, longitude, forecast_mode, hass
    )

    await weather_coordinator.async_config_entry_first_refresh()

    warning_coordinator = WarningUpdateCoordinator(
        ocwb,
        location_name,
        latitude,
        longitude,
        hass,
        enable_typhoon_warning=enable_typhoon_warning,
        enable_tropical_cyclone_track=enable_tropical_cyclone_track,
        enable_weather_alerts=enable_weather_alerts,
    )
    if warning_coordinator.any_enabled:
        await warning_coordinator.async_config_entry_first_refresh()

    agriculture_coordinator = None
    if enable_agriculture_advisories and crop_profiles:
        try:
            # Keep the optional provider outside the core OpenCWA import path.
            from .agriculture_update_coordinator import AgricultureUpdateCoordinator

            agriculture_coordinator = AgricultureUpdateCoordinator(
                ocwb,
                location_name,
                latitude,
                longitude,
                hass,
                token=agriculture_token,
                crop_profiles=crop_profiles,
            )
        except Exception as error:
            # Optional agriculture must never prevent CWA weather setup.
            agriculture_coordinator = None
            _LOGGER.error(
                "Optional agricultural provider could not be initialized (%s); "
                "OpenCWA weather will continue without it",
                type(error).__name__,
            )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = {
        ENTRY_NAME: name,
        ENTRY_WEATHER_COORDINATOR: weather_coordinator,
        ENTRY_WARNING_COORDINATOR: warning_coordinator,
        ENTRY_AGRICULTURE_COORDINATOR: agriculture_coordinator,
        CONF_LOCATION_NAME: location_name
    }

    _remove_disabled_warning_entities(
        hass,
        config_entry,
        enable_typhoon_warning=enable_typhoon_warning,
        enable_tropical_cyclone_track=enable_tropical_cyclone_track,
        enable_weather_alerts=enable_weather_alerts,
        enable_agriculture_advisories=enable_agriculture_advisories,
    )

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    if agriculture_coordinator is not None:
        _create_optional_background_task(
            hass,
            config_entry,
            _async_refresh_optional_agriculture(agriculture_coordinator),
            "OpenCWA optional agriculture initial refresh",
        )

    update_listener = config_entry.add_update_listener(async_update_options)
    hass.data[DOMAIN][config_entry.entry_id][UPDATE_LISTENER] = update_listener

    return True


def _create_optional_background_task(hass, config_entry, target, name) -> None:
    """Create a lifecycle task while retaining compatibility with older HA."""
    if hasattr(config_entry, "async_create_background_task"):
        config_entry.async_create_background_task(hass, target, name)
        return
    hass.async_create_task(target)


async def _async_refresh_optional_agriculture(coordinator) -> None:
    """Refresh agriculture only after core OpenCWA platforms are loaded."""
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as error:
        _LOGGER.error(
            "Optional agricultural provider background refresh failed (%s); "
            "OpenCWA weather remains available",
            type(error).__name__,
        )


async def async_update_options(hass: HomeAssistant, config_entry: ConfigEntry):
    """Update options."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Unload a config entry."""
    agriculture_coordinator = hass.data[DOMAIN][config_entry.entry_id].get(
        ENTRY_AGRICULTURE_COORDINATOR
    )
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(
                    config_entry, platform)
                for platform in PLATFORMS
            ]
        )
    )
    if unload_ok:
        if agriculture_coordinator is not None:
            try:
                await hass.async_add_executor_job(agriculture_coordinator.client.close)
            except Exception as error:
                _LOGGER.warning(
                    "Optional agriculture client close failed (%s)",
                    type(error).__name__,
                )
        update_listener = hass.data[
            DOMAIN][config_entry.entry_id][UPDATE_LISTENER]
        update_listener()
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok


def _migrate_legacy_agriculture_registry_entries(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    subentry_id: str,
    crop_name: str,
) -> bool:
    """Move registry rows in place with collision preflight and rollback."""
    base_id = config_entry.unique_id or config_entry.entry_id
    entity_registry = er.async_get(hass)
    planned_entities = []
    for entity in list(
        er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    ):
        new_unique_id = legacy_agriculture_unique_id(
            entity.unique_id or "", base_id, subentry_id
        )
        if new_unique_id is None:
            continue
        existing_entity_id = entity_registry.async_get_entity_id(
            entity.domain, entity.platform, new_unique_id
        )
        if existing_entity_id not in (None, entity.entity_id):
            _LOGGER.error("Legacy agriculture entity registry collision")
            return False
        planned_entities.append(
            (
                entity.entity_id,
                entity.unique_id,
                entity.config_subentry_id,
                new_unique_id,
            )
        )

    device_registry = dr.async_get(hass)
    old_device = None
    new_identifier = (DOMAIN, f"{base_id}-agriculture-{subentry_id}")
    for device in list(
        dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)
    ):
        if any(
            domain == DOMAIN and str(identifier).endswith("-agriculture")
            for domain, identifier in device.identifiers
        ):
            old_device = device
            break
    collision = device_registry.async_get_device(identifiers={new_identifier})
    if collision is not None and (old_device is None or collision.id != old_device.id):
        _LOGGER.error("Legacy agriculture device registry collision")
        return False

    updated_entities = []
    device_updated = False
    try:
        for entity_id, old_unique_id, old_subentry_id, new_unique_id in planned_entities:
            entity_registry.async_update_entity(
                entity_id,
                new_unique_id=new_unique_id,
                config_subentry_id=subentry_id,
            )
            updated_entities.append((entity_id, old_unique_id, old_subentry_id))
        if old_device is not None:
            device_registry.async_update_device(
                old_device.id,
                add_config_entry_id=config_entry.entry_id,
                add_config_subentry_id=subentry_id,
                remove_config_entry_id=config_entry.entry_id,
                remove_config_subentry_id=None,
                new_identifiers={new_identifier},
                name=f"OpenCWA 農業氣象補充 - {crop_name}",
            )
            device_updated = True
    except ValueError as error:
        _LOGGER.error(
            "Legacy agriculture registry migration failed (%s); rolling back",
            type(error).__name__,
        )
        for entity_id, old_unique_id, old_subentry_id in reversed(updated_entities):
            entity_registry.async_update_entity(
                entity_id,
                new_unique_id=old_unique_id,
                config_subentry_id=old_subentry_id,
            )
        if device_updated and old_device is not None:
            device_registry.async_update_device(
                old_device.id,
                add_config_entry_id=config_entry.entry_id,
                add_config_subentry_id=None,
                remove_config_entry_id=config_entry.entry_id,
                remove_config_subentry_id=subentry_id,
                new_identifiers=set(old_device.identifiers),
                name=old_device.name,
            )
        return False
    return True


def _is_agriculture_device_identifier(domain: str, identifier: str) -> bool:
    """Return whether a device-registry identifier belongs to agriculture."""
    value = str(identifier)
    return domain == DOMAIN and (
        value.endswith("-agriculture") or "-agriculture-" in value
    )


def _remove_unmapped_legacy_agriculture_registry_entries(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Remove legacy no-crop rows when there is no profile to attach them to."""
    markers = (
        "-agriculture-",
        "-crop-warning-",
        "-crop-advisory-",
        "-crop-supported-",
    )
    registry = er.async_get(hass)
    for entity in list(
        er.async_entries_for_config_entry(registry, config_entry.entry_id)
    ):
        if any(marker in (entity.unique_id or "") for marker in markers):
            registry.async_remove(entity.entity_id)
            hass.states.async_remove(entity.entity_id)

    device_registry = dr.async_get(hass)
    for device in list(
        dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)
    ):
        if any(
            _is_agriculture_device_identifier(domain, identifier)
            for domain, identifier in device.identifiers
        ):
            device_registry.async_remove_device(device.id)


def _remove_invalid_crop_registry_entries(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    valid_profile_ids: set[str],
) -> None:
    """Remove stale runtime rows for malformed crop subentries, not the records."""
    invalid_profile_ids = {
        str(subentry_id)
        for subentry_id, subentry in config_entry.subentries.items()
        if subentry.subentry_type == SUBENTRY_TYPE_CROP and str(subentry_id)
        not in valid_profile_ids
    }
    if not invalid_profile_ids:
        return

    registry = er.async_get(hass)
    for entity in list(
        er.async_entries_for_config_entry(registry, config_entry.entry_id)
    ):
        if entity.config_subentry_id in invalid_profile_ids:
            registry.async_remove(entity.entity_id)
            hass.states.async_remove(entity.entity_id)

    device_registry = dr.async_get(hass)
    for device in list(
        dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)
    ):
        if any(
            domain == DOMAIN and any(
                f"-agriculture-{profile_id}" in str(identifier)
                for profile_id in invalid_profile_ids
            )
            for domain, identifier in device.identifiers
        ):
            device_registry.async_remove_device(device.id)


def _filter_domain_configs(elements, domain):
    return list(filter(lambda elem: elem["platform"] == domain, elements))


def _get_config_value(config_entry, key, default):
    if config_entry.options and key in config_entry.options:
        return config_entry.options.get(key, default)
    return config_entry.data.get(key, default)


def _remove_disabled_warning_entities(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    *,
    enable_typhoon_warning: bool,
    enable_tropical_cyclone_track: bool,
    enable_weather_alerts: bool,
    enable_agriculture_advisories: bool,
) -> None:
    """Remove warning entities whose option group is currently disabled.

    Home Assistant keeps entity registry entries around after an integration
    stops adding an entity. For option-controlled entity groups, remove stale
    registry entries and state rows so disabling a group actually hides it.
    """
    disabled_suffixes: list[str] = []
    if not enable_typhoon_warning:
        disabled_suffixes.extend([
            "-typhoon-warning-",
            "-typhoon-warning-status-",
            "-typhoon-warning-notification-",
        ])
    if not enable_tropical_cyclone_track:
        disabled_suffixes.append("-tropical-cyclone-")
    if not enable_weather_alerts:
        disabled_suffixes.extend([
            "-weather-alert-",
            "-weather-alerts-",
        ])
    if not enable_agriculture_advisories:
        disabled_suffixes.extend([
            "-agriculture-",
            "-crop-warning-",
            "-crop-advisory-",
            "-crop-supported-",
        ])
    if not disabled_suffixes:
        return

    registry = er.async_get(hass)
    for entry in list(er.async_entries_for_config_entry(registry, config_entry.entry_id)):
        unique_id = entry.unique_id or ""
        if any(suffix in unique_id for suffix in disabled_suffixes):
            _LOGGER.debug(
                "Removing disabled OpenCWB warning entity %s (%s)",
                entry.entity_id,
                unique_id,
            )
            registry.async_remove(entry.entity_id)
            hass.states.async_remove(entry.entity_id)

    if not enable_agriculture_advisories:
        device_registry = dr.async_get(hass)
        for device in list(
            dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)
        ):
            if any(
                _is_agriculture_device_identifier(domain, identifier)
                for domain, identifier in device.identifiers
            ):
                device_registry.async_remove_device(device.id)


def _get_ocwb_config(language):
    """Get OpenWeatherMap configuration and add language to it."""
    config_dict = get_default_config()
    config_dict["language"] = language
    return config_dict
