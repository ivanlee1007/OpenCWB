"""The OpenCWB component."""
import asyncio
import logging

from .core.ocwb import OCWB
from .core.utils.config import get_default_config

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MODE,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_AGRICULTURE_TOKEN,
    CONF_AREA_HECTARES,
    CONF_CROP_NAME,
    CONF_ENABLE_AGRICULTURE_ADVISORIES,
    CONF_ENABLE_TROPICAL_CYCLONE_TRACK,
    CONF_ENABLE_TYPHOON_WARNING,
    CONF_ENABLE_WEATHER_ALERTS,
    CONF_GROWTH_STAGE,
    CONF_LANGUAGE,
    CONF_LOCATION_NAME,
    CONF_PLANTING_DATE,
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
    crop_name = _get_config_value(config_entry, CONF_CROP_NAME, "")
    growth_stage = _get_config_value(config_entry, CONF_GROWTH_STAGE, "")
    planting_date = _get_config_value(config_entry, CONF_PLANTING_DATE, "")
    area_hectares = _get_config_value(config_entry, CONF_AREA_HECTARES, 0.0)
    area_hectares = area_hectares if area_hectares and area_hectares > 0 else None

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
    if enable_agriculture_advisories:
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
                crop=crop_name,
                growth_stage=growth_stage,
                planting_date=planting_date,
                area_hectares=area_hectares,
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
            await hass.async_add_executor_job(agriculture_coordinator.client.close)
        update_listener = hass.data[
            DOMAIN][config_entry.entry_id][UPDATE_LISTENER]
        update_listener()
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok


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


def _get_ocwb_config(language):
    """Get OpenWeatherMap configuration and add language to it."""
    config_dict = get_default_config()
    config_dict["language"] = language
    return config_dict
