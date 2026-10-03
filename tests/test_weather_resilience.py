"""Offline weather timeout and freshness regressions (no warning changes)."""
import asyncio
import ast
from datetime import datetime, timezone
import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "opencwb"


def _module(monkeypatch, name, **attributes):
    module = ModuleType(name)
    module.__dict__.update(attributes)
    monkeypatch.setitem(sys.modules, name, module)
    return module


@pytest.fixture
def components(monkeypatch):
    """Import real weather modules while stubbing only HA boundaries."""
    for name in list(sys.modules):
        if name.startswith("custom_components.opencwb."):
            monkeypatch.delitem(sys.modules, name)
    for name, path in (
        ("custom_components", ROOT.parent),
        ("custom_components.opencwb", ROOT),
        ("custom_components.opencwb.core", ROOT / "core"),
        ("custom_components.opencwb.core.commons", ROOT / "core" / "commons"),
        ("custom_components.opencwb.core.weatherapi12", ROOT / "core" / "weatherapi12"),
    ):
        package = _module(monkeypatch, name)
        package.__path__ = [str(path)]
    ha = _module(monkeypatch, "homeassistant")
    ha.__path__ = []
    helpers = _module(monkeypatch, "homeassistant.helpers")
    helpers.__path__ = []
    weather_pkg = _module(monkeypatch, "homeassistant.components")
    weather_pkg.__path__ = []
    _module(monkeypatch, "homeassistant.components.weather", **{
        **{alias.name: alias.name for node in ast.parse((ROOT / "const.py").read_text(encoding="utf-8")).body
           if isinstance(node, ast.ImportFrom) and node.module == "homeassistant.components.weather"
           for alias in node.names},
        "ATTR_CONDITION_CLEAR_NIGHT": "clear-night", "Forecast": dict,
    })
    _module(monkeypatch, "homeassistant.components.sensor", SensorDeviceClass=SimpleNamespace(TEMPERATURE="temperature", HUMIDITY="humidity", TIMESTAMP="timestamp"), SensorEntity=object)
    _module(monkeypatch, "homeassistant.const", UnitOfSpeed=SimpleNamespace(METERS_PER_SECOND="m/s"), UnitOfTemperature=SimpleNamespace(CELSIUS="C"), UnitOfLength=SimpleNamespace(MILLIMETERS="mm"), UnitOfPressure=SimpleNamespace(HPA="hPa"), DEGREE="degree", PERCENTAGE="%", UV_INDEX="uv")
    _module(monkeypatch, "homeassistant.core", HomeAssistant=object, callback=lambda f: f)
    _module(monkeypatch, "homeassistant.config_entries", ConfigEntry=object)
    _module(monkeypatch, "homeassistant.helpers.device_registry", DeviceEntryType=SimpleNamespace(SERVICE="service"))
    _module(monkeypatch, "homeassistant.helpers.entity", DeviceInfo=dict)
    _module(monkeypatch, "homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
    sys.modules["homeassistant.components.weather"].SingleCoordinatorWeatherEntity = type("SingleCoordinatorWeatherEntity", (object,), {"__class_getitem__": classmethod(lambda cls, item: cls), "__init__": lambda self, coordinator: None})
    sys.modules["homeassistant.components.weather"].WeatherEntityFeature = SimpleNamespace(FORECAST_DAILY=1, FORECAST_HOURLY=2)
    _module(monkeypatch, "homeassistant.helpers.sun", is_up=lambda *_: True)
    _module(monkeypatch, "homeassistant.util", dt=SimpleNamespace(utc_from_timestamp=lambda x: datetime.fromtimestamp(x, timezone.utc)))
    class Coordinator:
        def __class_getitem__(cls, item):
            return cls
        def __init__(self, hass, logger, **kwargs):
            self.hass = hass
            self.data = None
            self.last_update_success = False
    _module(monkeypatch, "homeassistant.helpers.update_coordinator", DataUpdateCoordinator=Coordinator, UpdateFailed=type("UpdateFailed", (Exception,), {}))
    client = importlib.import_module("custom_components.opencwb.core.commons.http_client")
    config = importlib.import_module("custom_components.opencwb.core.config")
    coordinator = importlib.import_module("custom_components.opencwb.weather_update_coordinator")
    return SimpleNamespace(client=client, config=config, coordinator=coordinator)


def _client(components):
    from copy import deepcopy
    return components.client.HttpClient("dummy-key", deepcopy(components.config.DEFAULT_CONFIG), "opendata.cwa.gov.tw", False)


def test_shared_config_preserves_warning_timeout(components, monkeypatch):
    """WarningClient must still receive the baseline timeout from shared config."""
    from copy import deepcopy
    warning_module = importlib.import_module("custom_components.opencwb.core.weatherapi12.warning_client")
    get = Mock(return_value=SimpleNamespace(status_code=200, text="<alert/>"))
    monkeypatch.setattr(warning_module.requests, "Session", lambda: SimpleNamespace(get=get, trust_env=True))
    warning = warning_module.WarningClient("dummy-key", deepcopy(components.config.DEFAULT_CONFIG))
    assert warning._request_text("https://example.invalid/warnings", {}) == "<alert/>"
    assert warning.config["connection"]["timeout_secs"] == 5
    assert get.call_args.kwargs["timeout"] == 5


def test_weather_json_budget_and_retry_are_isolated_from_warning(components, monkeypatch):
    """Weather JSON keeps its longer read budget and bounded retry with shared config."""
    client = _client(components)
    client.config["connection"]["timeout_secs"] = 5  # Baseline shared warning setting.
    get = Mock(side_effect=[
        requests.exceptions.ReadTimeout("temporary"),
        SimpleNamespace(status_code=200, text="{}", json=lambda: {"ok": True}),
    ])
    sleep = Mock()
    monkeypatch.setattr(components.client.requests, "get", get)
    monkeypatch.setattr(components.client.time, "sleep", sleep)
    assert client.get_json("path", {"locationName": "Taipei"})[1] == {"ok": True}
    assert get.call_count == 2
    assert [call.kwargs["timeout"] for call in get.call_args_list] == [(5, 12), (5, 12)]
    sleep.assert_called_once_with(0.5)


def test_weather_read_budget_allows_slow_response(components, monkeypatch):
    client = _client(components)
    def get(*args, **kwargs):
        assert kwargs["timeout"][0] <= 5
        assert kwargs["timeout"][1] > 5
        return SimpleNamespace(status_code=200, text="{}", json=lambda: {"ok": True})
    monkeypatch.setattr(components.client.requests, "get", get)
    assert client.get_json("path", {"locationName": "Taipei"})[1] == {"ok": True}


def test_one_timeout_then_success_retries_with_backoff(components, monkeypatch):
    client = _client(components)
    get = Mock(side_effect=[requests.exceptions.ReadTimeout("dummy-key"), SimpleNamespace(status_code=200, text="{}", json=lambda: {})])
    sleep = Mock()
    monkeypatch.setattr(components.client.requests, "get", get)
    monkeypatch.setattr(components.client.time, "sleep", sleep)
    assert client.get_json("path", {"locationName": "Taipei"})[0] == 200
    assert get.call_count == 2
    sleep.assert_called_once()


@pytest.mark.parametrize("status", [401, 403])
def test_auth_error_is_not_retried_or_logged_with_key(components, monkeypatch, caplog, status):
    client = _client(components)
    get = Mock(return_value=SimpleNamespace(status_code=status, text="dummy-key forbidden"))
    monkeypatch.setattr(components.client.requests, "get", get)
    with pytest.raises(Exception):
        client.get_json("path", {"locationName": "Taipei"})
    assert get.call_count == 1
    assert "dummy-key" not in caplog.text


@pytest.mark.parametrize("status", [429, 502, 503])
def test_temporary_http_error_retries_once(components, monkeypatch, status):
    client = _client(components)
    get = Mock(side_effect=[
        SimpleNamespace(status_code=status, text="busy"),
        SimpleNamespace(status_code=200, text="{}", json=lambda: {}),
    ])
    monkeypatch.setattr(components.client.requests, "get", get)
    monkeypatch.setattr(components.client.time, "sleep", Mock())
    assert client.get_json("path", {"locationName": "Taipei"})[0] == 200
    assert get.call_count == 2


def test_permanent_http_timeout_is_bounded_and_redacted(components, monkeypatch, caplog):
    client = _client(components)
    get = Mock(side_effect=requests.exceptions.ReadTimeout("dummy-key"))
    monkeypatch.setattr(components.client.requests, "get", get)
    monkeypatch.setattr(components.client.time, "sleep", Mock())
    with pytest.raises(components.client.exceptions.TimeoutError) as error:
        client.get_json("path", {"locationName": "Taipei"})
    assert get.call_count == 2
    assert "dummy-key" not in str(error.value) + caplog.text


def test_malformed_json_does_not_retry(components, monkeypatch):
    client = _client(components)
    get = Mock(return_value=SimpleNamespace(status_code=200, text="broken", json=Mock(side_effect=ValueError("invalid"))))
    monkeypatch.setattr(components.client.requests, "get", get)
    with pytest.raises(components.client.exceptions.ParseAPIResponseError):
        client.get_json("path", {"locationName": "Taipei"})
    assert get.call_count == 1


def test_weather_parse_error_is_safe_update_failure(components):
    coordinator = components.coordinator.WeatherUpdateCoordinator(
        SimpleNamespace(), "Taipei", 25, 121, "daily", SimpleNamespace()
    )
    async def failed():
        raise components.client.exceptions.ParseAPIResponseError("https://cwa.invalid/?Authorization=dummy-key")
    coordinator._get_ocwb_weather = failed
    with pytest.raises(components.coordinator.UpdateFailed) as error:
        asyncio.run(coordinator._async_update_data())
    assert "dummy-key" not in str(error.value)
    assert "https://" not in str(error.value)
    assert error.value.__cause__ is None
    assert coordinator.last_successful_update is None


def test_success_records_freshness_then_failure_keeps_snapshot(components):
    coordinator = components.coordinator.WeatherUpdateCoordinator(
        SimpleNamespace(), "Taipei", 25, 121, "daily", SimpleNamespace()
    )
    async def weather():
        return object()
    coordinator._get_ocwb_weather = weather
    coordinator._convert_weather_response = lambda _: {"temperature": 28}
    snapshot = asyncio.run(coordinator._async_update_data())
    coordinator.data = snapshot
    assert coordinator.last_successful_update is not None
    assert coordinator.last_successful_update.tzinfo is not None
    coordinator.last_update_success = False
    assert coordinator.data == snapshot


def test_permanent_timeout_keeps_last_snapshot_unavailable_and_timestamp(components):
    coordinator = components.coordinator.WeatherUpdateCoordinator(
        SimpleNamespace(), "Taipei", 25, 121, "daily", SimpleNamespace()
    )
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    coordinator.data = {"temperature": 28}
    coordinator.last_successful_update = timestamp
    async def failed():
        raise components.coordinator.APIRequestError("dummy-key timed out")
    coordinator._get_ocwb_weather = failed
    with pytest.raises(components.coordinator.UpdateFailed) as error:
        asyncio.run(coordinator._async_update_data())
    assert "dummy-key" not in str(error.value)
    assert coordinator.data == {"temperature": 28}
    assert coordinator.last_successful_update == timestamp
    assert coordinator.last_update_success is False


def test_freshness_diagnostic_remains_available_when_weather_fails(components):
    from custom_components.opencwb import weather as weather_module
    coordinator = components.coordinator.WeatherUpdateCoordinator(
        SimpleNamespace(), "Taipei", 25, 121, "daily", SimpleNamespace()
    )
    diagnostic = weather_module.OpenCWBWeatherFreshness(
        "weather freshness", "entry-weather-freshness-Taipei", coordinator
    )
    assert diagnostic.available is True
    assert diagnostic.native_value == "unknown"
    coordinator.last_successful_update = datetime(2026, 1, 1, tzinfo=timezone.utc)
    coordinator.last_update_success = False
    assert diagnostic.native_value == "stale"
    assert diagnostic.extra_state_attributes["last_successful_update"] == "2026-01-01T00:00:00+00:00"
    coordinator.last_update_success = True
    assert diagnostic.native_value == "fresh"


def test_sensor_platform_registers_freshness_diagnostic():
    source = (ROOT / "sensor.py").read_text(encoding="utf-8")
    assert 'OpenCWBWeatherFreshness(' in source
    assert '-weather-freshness-' in source


def test_weather_entity_unavailable_preserves_snapshot_for_recovery(components):
    from custom_components.opencwb import weather as weather_module
    coordinator = components.coordinator.WeatherUpdateCoordinator(
        SimpleNamespace(), "Taipei", 25, 121, "daily", SimpleNamespace()
    )
    coordinator.data = {"condition": "sunny"}
    entity = weather_module.OpenCWBWeather("weather", "entry-weather-Taipei", coordinator)
    coordinator.last_update_success = False
    assert entity.available is False
    assert entity.condition == "sunny"  # Snapshot remains for recovery.


def test_forecast_callbacks_do_not_serve_stale_data(components):
    from custom_components.opencwb import weather as weather_module
    from custom_components.opencwb.const import ATTR_API_FORECAST_DAILY, ATTR_API_FORECAST_HOURLY
    coordinator = components.coordinator.WeatherUpdateCoordinator(
        SimpleNamespace(), "Taipei", 25, 121, "daily", SimpleNamespace()
    )
    daily, hourly = [{"datetime": "tomorrow"}], [{"datetime": "next hour"}]
    coordinator.data = {ATTR_API_FORECAST_DAILY: daily, ATTR_API_FORECAST_HOURLY: hourly}
    entity = weather_module.OpenCWBWeather("weather", "entry-weather-Taipei", coordinator)
    coordinator.last_update_success = False
    assert entity.available is False
    assert entity._async_forecast_daily() is None
    assert entity._async_forecast_hourly() is None
    coordinator.last_update_success = True
    assert entity._async_forecast_daily() == daily
    assert entity._async_forecast_hourly() == hourly
