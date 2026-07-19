from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INIT_SOURCE = (ROOT / "custom_components" / "opencwb" / "__init__.py").read_text(
    encoding="utf-8"
)
COORDINATOR_SOURCE = (
    ROOT / "custom_components" / "opencwb" / "agriculture_update_coordinator.py"
).read_text(encoding="utf-8")
CONST_SOURCE = (ROOT / "custom_components" / "opencwb" / "const.py").read_text(
    encoding="utf-8"
)
CONFIG_FLOW_SOURCE = (
    ROOT / "custom_components" / "opencwb" / "config_flow.py"
).read_text(encoding="utf-8")
CROP_OPTIONS_PATH = (
    ROOT / "custom_components" / "opencwb" / "agriculture_options.py"
)
SENSOR_SOURCE = (ROOT / "custom_components" / "opencwb" / "sensor.py").read_text(
    encoding="utf-8"
)
BINARY_SENSOR_SOURCE = (
    ROOT / "custom_components" / "opencwb" / "binary_sensor.py"
).read_text(encoding="utf-8")


def test_optional_agriculture_first_refresh_does_not_block_platform_forwarding():
    blocking_refresh = "await agriculture_coordinator.async_config_entry_first_refresh()"
    assert blocking_refresh not in INIT_SOURCE

    forward_index = INIT_SOURCE.index("async_forward_entry_setups")
    background_index = INIT_SOURCE.index("_create_optional_background_task")
    assert forward_index < background_index
    assert "await coordinator.async_config_entry_first_refresh()" in INIT_SOURCE


def test_agriculture_coordinator_has_initial_unavailable_data_before_background_refresh():
    assert "self.data =" in COORDINATOR_SOURCE
    assert "self._fallback()" in COORDINATOR_SOURCE


def test_agriculture_provider_import_remains_inside_enabled_branch():
    enabled_index = INIT_SOURCE.index("if enable_agriculture_advisories:")
    import_index = INIT_SOURCE.index(
        "from .agriculture_update_coordinator import AgricultureUpdateCoordinator"
    )
    assert enabled_index < import_index
    assert ".core.agriculture" not in SENSOR_SOURCE
    assert ".core.agriculture" not in BINARY_SENSOR_SOURCE


def test_agriculture_coordinator_does_not_log_raw_provider_exception_text():
    assert 'agricultural update failed: %s", error' not in COORDINATOR_SOURCE
    assert 'irrigation reference failed: %s", error' not in COORDINATOR_SOURCE
    assert "_LOGGER.exception" not in INIT_SOURCE


def test_config_entry_owns_background_refresh_and_closes_provider_session():
    assert "config_entry.async_create_background_task" in INIT_SOURCE
    assert "hass.async_create_task" in INIT_SOURCE
    assert "hasattr(config_entry, \"async_create_background_task\")" in INIT_SOURCE
    assert "agriculture_coordinator.client.close" in INIT_SOURCE
    assert 'entity_snapshot.pop("_notification_item", None)' in COORDINATOR_SOURCE


def test_agriculture_stays_default_off_and_token_uses_password_selector():
    assert "DEFAULT_ENABLE_AGRICULTURE_ADVISORIES = False" in CONST_SOURCE
    assert "selector.TextSelectorType.PASSWORD" in CONFIG_FLOW_SOURCE
    assert CONFIG_FLOW_SOURCE.count("vol.Range(min=0)") == 2


def test_crop_name_uses_searchable_custom_value_dropdown_without_provider_import():
    assert CROP_OPTIONS_PATH.exists()
    namespace = {}
    exec(CROP_OPTIONS_PATH.read_text(encoding="utf-8"), namespace)
    crop_names = namespace["CROP_NAME_OPTIONS"]
    aliases = namespace["CROP_NAME_ALIASES"]
    select_options = namespace["crop_select_options"]()

    assert "香蕉" in crop_names
    assert "番石榴" in crop_names
    assert len(crop_names) == 127
    assert tuple(sorted(set(crop_names))) == crop_names
    assert aliases["甘藍"] == "高麗菜"
    assert aliases["番石榴"] == "芭樂"
    assert len(select_options) == 127
    assert all(set(option) == {"value", "label"} for option in select_options)
    assert len({option["value"] for option in select_options}) == 127
    assert {option["value"] for option in select_options} == set(crop_names)
    assert next(
        option for option in select_options if option["value"] == "甘藍"
    )["label"] == "甘藍（高麗菜）"
    assert "高麗菜" not in {option["value"] for option in select_options}
    assert "selector.SelectSelector(" in CONFIG_FLOW_SOURCE
    assert "selector.SelectSelectorMode.DROPDOWN" in CONFIG_FLOW_SOURCE
    assert "custom_value=True" in CONFIG_FLOW_SOURCE
    assert ".core.agriculture" not in CONFIG_FLOW_SOURCE
