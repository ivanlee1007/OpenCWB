"""Config flow for OpenCWB."""
import logging
import urllib.parse
import uuid

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
from .agriculture_profiles import SUBENTRY_TYPE_CROP, normalize_crop_profile
from .const import (
    CONF_AGRICULTURE_TOKEN,
    CONF_AREA_HECTARES,
    CONF_CROP_NAME,
    CONF_CLEAR_AGRICULTURE_TOKEN,
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

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry
    ) -> dict[str, type[config_entries.ConfigSubentryFlow]]:
        """Return the crop records users may repeatedly add to a farm."""
        return {SUBENTRY_TYPE_CROP: CropSubentryFlowHandler}

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
            options = dict(user_input)
            replacement_token = str(options.pop(CONF_AGRICULTURE_TOKEN, "") or "").strip()
            clear_token = bool(options.pop(CONF_CLEAR_AGRICULTURE_TOKEN, False))
            current_token = self._config_entry.options.get(
                CONF_AGRICULTURE_TOKEN,
                self._config_entry.data.get(CONF_AGRICULTURE_TOKEN, ""),
            )
            options[CONF_AGRICULTURE_TOKEN] = (
                replacement_token
                if replacement_token
                else "" if clear_token else current_token
            )
            return self.async_create_entry(title="", data=options)

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
                    default="",
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Optional(
                    CONF_CLEAR_AGRICULTURE_TOKEN,
                    default=False,
                ): bool,
            }
        )


def _crop_profile_schema(defaults=None):
    """Build the reusable crop add/reconfigure form."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_CROP_NAME, default=defaults.get(CONF_CROP_NAME, "")
            ): _crop_name_selector(),
            vol.Optional(
                CONF_GROWTH_STAGE, default=defaults.get(CONF_GROWTH_STAGE, "")
            ): str,
            vol.Optional(
                CONF_PLANTING_DATE, default=defaults.get(CONF_PLANTING_DATE, "")
            ): str,
            vol.Optional(
                CONF_AREA_HECTARES,
                default=defaults.get(CONF_AREA_HECTARES) or 0.0,
            ): vol.All(vol.Coerce(float), vol.Range(min=0)),
        }
    )


class CropSubentryFlowHandler(config_entries.ConfigSubentryFlow):
    """Add and reconfigure independently identified crop records."""

    async def async_step_user(self, user_input=None):
        """Add one crop to the farm."""
        errors = {}
        defaults = user_input or {}
        if user_input is not None:
            try:
                profile = normalize_crop_profile(user_input)
            except ValueError:
                errors["base"] = "invalid_crop_profile"
            else:
                return self.async_create_entry(
                    title=profile[CONF_CROP_NAME],
                    data=profile,
                    unique_id=uuid.uuid4().hex,
                )
        return self.async_show_form(
            step_id="user",
            data_schema=_crop_profile_schema(defaults),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Edit one crop without changing its stable subentry identity."""
        subentry = self._get_reconfigure_subentry()
        errors = {}
        defaults = user_input or subentry.data
        if user_input is not None:
            try:
                profile = normalize_crop_profile(user_input)
            except ValueError:
                errors["base"] = "invalid_crop_profile"
            else:
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    data=profile,
                    title=profile[CONF_CROP_NAME],
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_crop_profile_schema(defaults),
            errors=errors,
        )


async def _is_ocwb_api_online(hass, api_key, lat, lon, loc):
    ocwb = OCWB(api_key).weather_manager()
    return await hass.async_add_executor_job(ocwb.one_call, lat, lon, loc, "daily")


def _is_supported_city(api_key, loc):
    ocwb = OCWB(api_key).weather_manager()
    return ocwb.supported_city(loc)
