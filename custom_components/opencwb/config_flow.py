"""Config flow for OpenCWB."""
import logging
import urllib.parse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MODE,
    CONF_NAME,
    MAJOR_VERSION,
    MINOR_VERSION,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .agriculture_options import crop_select_options
from .const import (
    CONF_AGRICULTURE_TOKEN,
    CONF_AREA_HECTARES,
    CONF_CROP_NAME,
    CONF_ENABLE_AGRICULTURE_ADVISORIES,
    CONF_ENABLE_TROPICAL_CYCLONE_TRACK,
    CONF_ENABLE_TYPHOON_WARNING,
    CONF_ENABLE_WEATHER_ALERTS,
    CONF_GROWTH_STAGE,
    CONF_LOCATION_NAME,
    CONF_PLANTING_DATE,
    CONFIG_FLOW_VERSION,
    DEFAULT_ENABLE_AGRICULTURE_ADVISORIES,
    DEFAULT_ENABLE_TROPICAL_CYCLONE_TRACK,
    DEFAULT_ENABLE_TYPHOON_WARNING,
    DEFAULT_ENABLE_WEATHER_ALERTS,
    DEFAULT_FORECAST_MODE,
    DEFAULT_NAME,
    DOMAIN,
    FORECAST_MODES,
)
from .core.commons.exceptions import APIRequestError, APIResponseError, UnauthorizedError
from .core.ocwb import OCWB

_LOGGER = logging.getLogger(__name__)


def _crop_name_selector():
    """Return a searchable provider crop list with a manual-entry fallback."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=list(crop_select_options()),
            mode=selector.SelectSelectorMode.DROPDOWN,
            custom_value=True,
            sort=True,
        )
    )


class OpenCWBConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for OpenCWB."""

    VERSION = CONFIG_FLOW_VERSION
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OpenCWBOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is not None:
            latitude = user_input.get(
                CONF_LATITUDE, self.hass.config.latitude)
            longitude = user_input.get(
                CONF_LONGITUDE, self.hass.config.longitude)
            location_name = user_input.get(CONF_LOCATION_NAME, None)
            location_id = _is_supported_city(
                user_input[CONF_API_KEY], location_name)

            if location_name and location_id is None:
                errors["base"] = "invalid_location_name"
            else:
                await self.async_set_unique_id(
                    urllib.parse.quote_plus(
                        location_name) + "-" + user_input[CONF_MODE])
                self._abort_if_unique_id_configured()

                try:
                    api_online = await _is_ocwb_api_online(
                        self.hass,
                        user_input[CONF_API_KEY],
                        latitude,
                        longitude,
                        location_name
                    )
                    if not api_online:
                        errors["base"] = "invalid_api_key"
                except UnauthorizedError:
                    errors["base"] = "invalid_api_key"
                except APIResponseError:
                    errors["base"] = "cannot_connect"
                except APIRequestError:
                    errors["base"] = "cannot_connect"
                except Exception as e:
                    _LOGGER.exception("Unexpected error in config flow: %s", e)
                    errors["base"] = "unknown_error"

                if not errors:
                    return self.async_create_entry(
                        title=user_input[CONF_NAME], data=user_input
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_LOCATION_NAME): str,
                # vol.Optional(
                #    CONF_LATITUDE, default=self.hass.config.latitude
                # ): cv.latitude,
                # vol.Optional(
                #    CONF_LONGITUDE, default=self.hass.config.longitude
                # ): cv.longitude,
                vol.Optional(CONF_MODE, default=DEFAULT_FORECAST_MODE): vol.In(
                    FORECAST_MODES
                ),
                vol.Optional(
                    CONF_ENABLE_TYPHOON_WARNING,
                    default=DEFAULT_ENABLE_TYPHOON_WARNING,
                ): bool,
                vol.Optional(
                    CONF_ENABLE_TROPICAL_CYCLONE_TRACK,
                    default=DEFAULT_ENABLE_TROPICAL_CYCLONE_TRACK,
                ): bool,
                vol.Optional(
                    CONF_ENABLE_WEATHER_ALERTS,
                    default=DEFAULT_ENABLE_WEATHER_ALERTS,
                ): bool,
                vol.Optional(
                    CONF_ENABLE_AGRICULTURE_ADVISORIES,
                    default=DEFAULT_ENABLE_AGRICULTURE_ADVISORIES,
                ): bool,
                vol.Optional(CONF_AGRICULTURE_TOKEN, default=""): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Optional(CONF_CROP_NAME, default=""): _crop_name_selector(),
                vol.Optional(CONF_GROWTH_STAGE, default=""): str,
                vol.Optional(CONF_PLANTING_DATE, default=""): str,
                vol.Optional(CONF_AREA_HECTARES): vol.All(
                    vol.Coerce(float), vol.Range(min=0)
                ),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors)


class OpenCWBOptionsFlow(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self._config_entry = config_entry
        if (MAJOR_VERSION, MINOR_VERSION) < (2024, 11):
            self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self._get_options_schema(),
        )

    def _get_options_schema(self):
        return vol.Schema(
            {
                vol.Optional(
                    CONF_MODE,
                    default=self._config_entry.options.get(
                        CONF_MODE,
                        self._config_entry.data.get(CONF_MODE, DEFAULT_FORECAST_MODE)
                    ),
                ): vol.In(FORECAST_MODES),
                vol.Optional(
                    CONF_ENABLE_TYPHOON_WARNING,
                    default=self._config_entry.options.get(
                        CONF_ENABLE_TYPHOON_WARNING,
                        self._config_entry.data.get(
                            CONF_ENABLE_TYPHOON_WARNING,
                            DEFAULT_ENABLE_TYPHOON_WARNING,
                        ),
                    ),
                ): bool,
                vol.Optional(
                    CONF_ENABLE_TROPICAL_CYCLONE_TRACK,
                    default=self._config_entry.options.get(
                        CONF_ENABLE_TROPICAL_CYCLONE_TRACK,
                        self._config_entry.data.get(
                            CONF_ENABLE_TROPICAL_CYCLONE_TRACK,
                            DEFAULT_ENABLE_TROPICAL_CYCLONE_TRACK,
                        ),
                    ),
                ): bool,
                vol.Optional(
                    CONF_ENABLE_WEATHER_ALERTS,
                    default=self._config_entry.options.get(
                        CONF_ENABLE_WEATHER_ALERTS,
                        self._config_entry.data.get(
                            CONF_ENABLE_WEATHER_ALERTS,
                            DEFAULT_ENABLE_WEATHER_ALERTS,
                        ),
                    ),
                ): bool,
                vol.Optional(
                    CONF_ENABLE_AGRICULTURE_ADVISORIES,
                    default=self._config_entry.options.get(
                        CONF_ENABLE_AGRICULTURE_ADVISORIES,
                        self._config_entry.data.get(
                            CONF_ENABLE_AGRICULTURE_ADVISORIES,
                            DEFAULT_ENABLE_AGRICULTURE_ADVISORIES,
                        ),
                    ),
                ): bool,
                vol.Optional(
                    CONF_AGRICULTURE_TOKEN,
                    default=self._config_entry.options.get(
                        CONF_AGRICULTURE_TOKEN,
                        self._config_entry.data.get(CONF_AGRICULTURE_TOKEN, ""),
                    ),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Optional(
                    CONF_CROP_NAME,
                    default=self._config_entry.options.get(
                        CONF_CROP_NAME,
                        self._config_entry.data.get(CONF_CROP_NAME, ""),
                    ),
                ): _crop_name_selector(),
                vol.Optional(
                    CONF_GROWTH_STAGE,
                    default=self._config_entry.options.get(
                        CONF_GROWTH_STAGE,
                        self._config_entry.data.get(CONF_GROWTH_STAGE, ""),
                    ),
                ): str,
                vol.Optional(
                    CONF_PLANTING_DATE,
                    default=self._config_entry.options.get(
                        CONF_PLANTING_DATE,
                        self._config_entry.data.get(CONF_PLANTING_DATE, ""),
                    ),
                ): str,
                vol.Optional(
                    CONF_AREA_HECTARES,
                    default=self._config_entry.options.get(
                        CONF_AREA_HECTARES,
                        self._config_entry.data.get(CONF_AREA_HECTARES, 0.0),
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=0)),
                # vol.Optional(
                #     CONF_LANGUAGE,
                #     default=self.config_entry.options.get(
                #         ONF_LANGUAGE, DEFAULT_LANGUAGE
                #     ),
                # ): vol.In(LANGUAGES),
            }
        )


async def _is_ocwb_api_online(hass, api_key, lat, lon, loc):
    ocwb = OCWB(api_key).weather_manager()
    return await hass.async_add_executor_job(ocwb.one_call, lat, lon, loc, "daily")


def _is_supported_city(api_key, loc):
    ocwb = OCWB(api_key).weather_manager()
    return ocwb.supported_city(loc)
