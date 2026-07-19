from pathlib import Path
import asyncio
from datetime import datetime, timezone
import importlib.util
import sys
import types

import pytest


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "opencwb"
PROFILE_PATH = COMPONENT / "agriculture_profiles.py"


def _source(name):
    return (COMPONENT / name).read_text(encoding="utf-8")


def _profile_namespace():
    namespace = {}
    exec(PROFILE_PATH.read_text(encoding="utf-8"), namespace)
    return namespace


def test_crop_profile_model_is_stable_and_allows_duplicate_crop_names():
    assert PROFILE_PATH.exists()
    ns = _profile_namespace()
    profiles = ns["crop_profiles_from_subentries"](
        {
            "crop-a": {
                "subentry_type": "crop",
                "data": {
                    "crop_name": "香蕉",
                    "growth_stage": "幼苗期",
                    "planting_date": "2026-07-01",
                    "area_hectares": 1.5,
                },
            },
            "crop-b": {
                "subentry_type": "crop",
                "data": {
                    "crop_name": "香蕉",
                    "growth_stage": "開花期",
                    "planting_date": "2026-05-01",
                    "area_hectares": 0.8,
                },
            },
            "other": {"subentry_type": "not-a-crop", "data": {}},
        }
    )

    assert list(profiles) == ["crop-a", "crop-b"]
    assert profiles["crop-a"]["crop_name"] == "香蕉"
    assert profiles["crop-b"]["growth_stage"] == "開花期"
    assert profiles["crop-a"]["area_hectares"] == 1.5


def test_crop_profile_validation_rejects_blank_crop_and_negative_area():
    ns = _profile_namespace()
    normalize = ns["normalize_crop_profile"]

    with pytest.raises(ValueError, match="crop_name"):
        normalize({"crop_name": "  ", "area_hectares": 1})
    with pytest.raises(ValueError, match="area_hectares"):
        normalize({"crop_name": "香蕉", "area_hectares": -0.1})

    assert normalize({"crop_name": " 香蕉 ", "area_hectares": 0}) == {
        "crop_name": "香蕉",
        "growth_stage": "",
        "planting_date": "",
        "area_hectares": None,
    }


def test_legacy_single_crop_migration_is_idempotent_and_lossless():
    ns = _profile_namespace()
    legacy = ns["legacy_crop_profile"]
    strip_legacy = ns["without_legacy_crop_fields"]

    data = {"api_key": "not-a-secret", "crop_name": "甘藍"}
    options = {
        "enable_agriculture_advisories": True,
        "crop_name": "香蕉",
        "growth_stage": "採收期",
        "planting_date": "2026-06-01",
        "area_hectares": 2.25,
    }
    assert legacy(data, options) == {
        "crop_name": "香蕉",
        "growth_stage": "採收期",
        "planting_date": "2026-06-01",
        "area_hectares": 2.25,
    }
    assert legacy(data, {"enable_agriculture_advisories": True})["crop_name"] == "甘藍"
    assert legacy({}, {}) is None
    assert strip_legacy(options) == {"enable_agriculture_advisories": True}


def test_config_flow_exposes_native_crop_subentry_add_and_reconfigure():
    source = _source("config_flow.py")
    assert "ConfigSubentryFlow" in source
    assert "async_get_supported_subentry_types" in source
    assert 'SUBENTRY_TYPE_CROP: CropSubentryFlowHandler' in source
    assert "class CropSubentryFlowHandler" in source
    assert "async_step_user" in source
    assert "async_step_reconfigure" in source
    assert "async_update_and_abort" in source
    assert "async_update_reload_and_abort" not in source
    assert "unique_id=" in source
    assert source.count("normalize_crop_profile(user_input)") == 2
    assert source.count('errors["base"] = "invalid_crop_profile"') == 2


def test_config_entry_v2_migrates_legacy_crop_to_subentry():
    config_source = _source("config_flow.py")
    init_source = _source("__init__.py")
    const_source = _source("const.py")

    assert "CONFIG_FLOW_VERSION = 2" in const_source
    assert "VERSION = CONFIG_FLOW_VERSION" in config_source
    assert "async_migrate_entry" in init_source
    assert "async_add_subentry" in init_source
    assert "ConfigSubentry" in init_source
    assert "SUBENTRY_TYPE_CROP" in init_source


def test_v2_migration_preserves_legacy_registry_identity_in_place():
    init_source = _source("__init__.py")
    start = init_source.index("def _migrate_legacy_agriculture_registry_entries")
    end = init_source.index("def _remove_unmapped_legacy_agriculture_registry_entries")
    migration_helper = init_source[start:end]
    assert "entity_registry.async_update_entity(" in migration_helper
    assert "new_unique_id=new_unique_id" in migration_helper
    assert "config_subentry_id=subentry_id" in migration_helper
    assert "device_registry.async_update_device(" in migration_helper
    assert "new_identifiers=" in migration_helper
    assert "async_remove_device(device.id)" not in migration_helper
    assert "add_config_subentry_id=subentry_id" in migration_helper
    assert "remove_config_subentry_id=None" in migration_helper
    assert "add_config_subentry_id=None" in migration_helper
    assert "remove_config_subentry_id=subentry_id" in migration_helper


def test_mixed_v1_profile_and_legacy_unique_id_mapping_are_deterministic():
    ns = _profile_namespace()
    find_equivalent = ns["find_equivalent_crop_profile"]
    map_unique_id = ns["legacy_agriculture_unique_id"]
    subentries = {
        "existing-a": {
            "subentry_type": "crop",
            "data": {"crop_name": "香蕉", "growth_stage": "開花期"},
        },
        "existing-b": {
            "subentry_type": "crop",
            "data": {"crop_name": "甘藍", "area_hectares": 1.0},
        },
    }
    assert find_equivalent(
        subentries, {"crop_name": "甘藍", "area_hectares": 1}
    ) == "existing-b"
    assert find_equivalent(
        subentries, {"crop_name": "番石榴", "area_hectares": 1}
    ) is None
    assert map_unique_id(
        "farm-agriculture-agriculture_notification-town", "farm", "crop-a"
    ) == "farm-agriculture-crop-a-agriculture_notification"
    assert map_unique_id(
        "farm-crop-warning-town", "farm", "crop-a"
    ) == "farm-agriculture-crop-a-crop-warning"
    recover = ns["legacy_crop_profile_with_recovery"]
    recovered_profile, recovered = recover(
        {"crop_name": "香蕉", "area_hectares": "CORRUPT"}, {}
    )
    assert recovered is True
    assert find_equivalent(
        {
            "existing-clean": {
                "subentry_type": "crop",
                "data": {"crop_name": "香蕉", "area_hectares": None},
            }
        },
        recovered_profile,
    ) is None
    assert find_equivalent(
        {
            "existing-recovery": {
                "subentry_type": "crop",
                "data": dict(recovered_profile),
            }
        },
        recovered_profile,
    ) == "existing-recovery"


def test_malformed_legacy_area_becomes_visible_repairable_crop_subentry():
    ns = _profile_namespace()
    recover = ns["legacy_crop_profile_with_recovery"]
    profile, recovered = recover(
        {"crop_name": "香蕉", "area_hectares": "corrupt"}, {}
    )
    assert recovered is True
    assert profile["crop_name"] == "香蕉"
    assert profile["area_hectares"] is None
    assert profile["migration_warning"] == "invalid_legacy_area"
    assert profile["legacy_area_hectares"] == "corrupt"

    init_source = _source("__init__.py")
    assert "legacy_crop_profile_with_recovery" in init_source
    assert 'f"⚠ {profile[CONF_CROP_NAME]}"' in init_source
    assert "return False" in init_source
    assert "rolling back" in init_source


def test_registry_migration_preflights_collisions_and_rolls_back_before_v2_commit():
    init_source = _source("__init__.py")
    helper_start = init_source.index("def _migrate_legacy_agriculture_registry_entries")
    helper_end = init_source.index("def _remove_unmapped_legacy_agriculture_registry_entries")
    helper = init_source[helper_start:helper_end]
    migration_start = init_source.index("async def async_migrate_entry")
    migration_end = init_source.index("async def async_setup_entry")
    migration = init_source[migration_start:migration_end]
    assert "async_get_entity_id" in helper
    assert "async_get_device" in helper
    assert "updated_entities" in helper
    assert "reversed(updated_entities)" in helper
    assert "return False" in helper
    assert migration.index("if not _migrate_legacy") < migration.index(
        "data=without_legacy_crop_fields"
    )


def test_disabling_agriculture_removes_per_crop_entities_and_devices():
    init_source = _source("__init__.py")
    cleanup_start = init_source.index("def _remove_disabled_warning_entities")
    cleanup_source = init_source[cleanup_start:]
    assert '"-agriculture-"' in cleanup_source
    assert "if not enable_agriculture_advisories:" in cleanup_source
    assert "device_registry.async_remove_device(device.id)" in cleanup_source


def test_malformed_persisted_crop_keeps_record_but_removes_stale_runtime_rows():
    source = _source("__init__.py")
    assert "_remove_invalid_crop_registry_entries(" in source
    start = source.index("def _remove_invalid_crop_registry_entries")
    end = source.index("def _filter_domain_configs", start)
    helper = source[start:end]
    assert "entity.config_subentry_id in invalid_profile_ids" in helper
    assert "registry.async_remove(entity.entity_id)" in helper
    assert "device_registry.async_remove_device(device.id)" in helper
    assert "async_remove_subentry" not in helper


def test_options_flow_does_not_return_stored_token_to_frontend_schema():
    source = _source("config_flow.py")
    schema_start = source.index("def _get_options_schema")
    schema = source[schema_start:source.index("def _crop_profile_schema", schema_start)]
    token_field = schema[schema.index("CONF_AGRICULTURE_TOKEN"):]
    assert 'default=""' in token_field
    assert "CONF_CLEAR_AGRICULTURE_TOKEN" in schema
    submit_start = source.index("async def async_step_init")
    submit = source[submit_start:schema_start]
    assert "current_token" in submit
    assert "clear_token" in submit


def test_runtime_uses_one_farm_coordinator_with_per_crop_snapshots():
    init_source = _source("__init__.py")
    coordinator_source = _source("agriculture_update_coordinator.py")

    assert "crop_profiles_from_subentries" in init_source
    assert "crop_profiles=" in init_source
    assert "ENTRY_AGRICULTURE_COORDINATOR" in init_source
    assert "self.crop_profiles" in coordinator_source
    assert "for profile_id, profile in self.crop_profiles.items()" in coordinator_source
    assert "previous.get(profile_id)" in coordinator_source
    # Shared city data is fetched once before profile-specific processing.
    assert coordinator_source.index("self.client.crop_weather") < coordinator_source.index(
        "for profile_id, profile in self.crop_profiles.items()"
    )


def test_crop_entities_have_stable_subentry_ids_and_separate_devices():
    sensor_source = _source("sensor.py")
    binary_source = _source("binary_sensor.py")

    assert "config_subentry_id=profile_id" in sensor_source
    assert "config_subentry_id=profile_id" in binary_source
    assert "profile_id" in sensor_source
    assert "profile_id" in binary_source
    assert "crop_name" in sensor_source
    assert "crop_name" in binary_source
    assert "-agriculture-{profile_id}-" in sensor_source
    assert "-agriculture-{profile_id}-" in binary_source


class _FakeDataUpdateCoordinator:
    @classmethod
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, logger, *, name, update_interval):
        self.hass = hass
        self.last_update_success = True
        self.data = None


class _FakeHass:
    async def async_add_executor_job(self, target, *args):
        return target(*args)


class _FakeWeatherManager:
    def one_call_city_name(self, location_name):
        return "臺中市"


class _FakeAgricultureClient:
    def __init__(self):
        self.calls = {"weather": 0, "catalog": 0, "rules": 0, "irrigation": []}
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        self.rows = [
            {
                "CITY_NAME": "臺中市",
                "TOWN_NAME": "新社區",
                "C_NAME": crop,
                "Disaster": "注意高溫",
                "TIMESTAMP": timestamp,
                "Note": 7,
            }
            for crop in ("香蕉", "甘藍")
        ]

    def crop_weather(self, city):
        self.calls["weather"] += 1
        return self.rows

    def crop_catalog(self):
        self.calls["catalog"] += 1
        return [{"C_NAME": "香蕉"}, {"C_NAME": "甘藍"}]

    def warning_rules(self):
        self.calls["rules"] += 1
        return []

    def irrigation_reference(self, **kwargs):
        self.calls["irrigation"].append(kwargs["crop"])
        return {
            "available": True,
            "et0": 4.0,
            "kc": 0.8,
            "etc": 3.2,
            "water_requirement": 10.0,
            "crop_water_supported": True,
        }


def _load_coordinator_module(monkeypatch):
    update_module = types.ModuleType("homeassistant.helpers.update_coordinator")
    update_module.DataUpdateCoordinator = _FakeDataUpdateCoordinator
    helpers_module = types.ModuleType("homeassistant.helpers")
    homeassistant_module = types.ModuleType("homeassistant")
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant_module)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers_module)
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.update_coordinator", update_module
    )

    for package, path in (
        ("custom_components", COMPONENT.parent),
        ("custom_components.opencwb", COMPONENT),
        ("custom_components.opencwb.core", COMPONENT / "core"),
        ("custom_components.opencwb.core.agriculture", COMPONENT / "core" / "agriculture"),
    ):
        module = types.ModuleType(package)
        module.__path__ = [str(path)]
        monkeypatch.setitem(sys.modules, package, module)

    const_module = types.ModuleType("custom_components.opencwb.const")
    for name, value in {
        "ATTR_AGRICULTURE": "agriculture",
        "ATTR_AGRICULTURE_ADVISORY": "agriculture_advisory",
        "ATTR_AGRICULTURE_ET0": "agriculture_et0",
        "ATTR_AGRICULTURE_ETC": "agriculture_etc",
        "ATTR_AGRICULTURE_KC": "agriculture_kc",
        "ATTR_AGRICULTURE_NOTIFICATION": "agriculture_notification",
        "ATTR_AGRICULTURE_SUPPORTED": "agriculture_supported",
        "ATTR_AGRICULTURE_WARNING": "agriculture_warning",
        "ATTR_AGRICULTURE_WATER_REQUIREMENT": "agriculture_water_requirement",
        "CONF_AREA_HECTARES": "area_hectares",
        "CONF_CROP_NAME": "crop_name",
        "CONF_GROWTH_STAGE": "growth_stage",
        "CONF_PLANTING_DATE": "planting_date",
    }.items():
        setattr(const_module, name, value)
    monkeypatch.setitem(sys.modules, "custom_components.opencwb.const", const_module)

    module_name = "custom_components.opencwb.agriculture_update_coordinator"
    spec = importlib.util.spec_from_file_location(
        module_name, COMPONENT / "agriculture_update_coordinator.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def test_shared_coordinator_fetches_city_data_once_for_two_crops(monkeypatch):
    module = _load_coordinator_module(monkeypatch)
    client = _FakeAgricultureClient()
    coordinator = module.AgricultureUpdateCoordinator(
        _FakeWeatherManager(),
        "新社區",
        24.2,
        120.8,
        _FakeHass(),
        crop_profiles={
            "crop-a": {"crop_name": "香蕉", "area_hectares": 1.0},
            "crop-b": {"crop_name": "甘藍", "area_hectares": 2.0},
        },
        client=client,
    )

    result = asyncio.run(coordinator._async_update_data())

    assert client.calls["weather"] == 1
    assert client.calls["catalog"] == 1
    assert client.calls["rules"] == 1
    assert client.calls["irrigation"] == ["香蕉", "甘藍"]
    assert set(result) == {"crop-a", "crop-b"}
    assert result["crop-a"]["agriculture"]["crop_name"] == "香蕉"
    assert result["crop-b"]["agriculture"]["crop_name"] == "甘藍"
    assert result["crop-a"]["agriculture"]["provider_available"] is True
    assert result["crop-b"]["agriculture"]["provider_available"] is True


def test_one_crop_parser_failure_does_not_replace_other_crop(monkeypatch):
    module = _load_coordinator_module(monkeypatch)
    client = _FakeAgricultureClient()
    real_builder = module.build_agriculture_snapshot

    def selective_builder(rows, **kwargs):
        if kwargs["crop"] == "甘藍":
            raise ValueError("malformed crop fixture")
        return real_builder(rows, **kwargs)

    monkeypatch.setattr(module, "build_agriculture_snapshot", selective_builder)
    coordinator = module.AgricultureUpdateCoordinator(
        _FakeWeatherManager(),
        "新社區",
        24.2,
        120.8,
        _FakeHass(),
        crop_profiles={
            "crop-a": {"crop_name": "香蕉"},
            "crop-b": {"crop_name": "甘藍"},
        },
        client=client,
    )

    result = asyncio.run(coordinator._async_update_data())

    assert result["crop-a"]["agriculture"]["provider_available"] is True
    assert result["crop-b"]["agriculture"]["status"] == "unavailable"
    assert result["crop-b"]["agriculture"]["provider_available"] is False
    assert client.calls["irrigation"] == ["香蕉"]


def test_notification_compose_failure_is_contained_for_every_crop(monkeypatch):
    module = _load_coordinator_module(monkeypatch)
    client = _FakeAgricultureClient()
    coordinator = module.AgricultureUpdateCoordinator(
        _FakeWeatherManager(),
        "臺中市",
        24.1,
        120.6,
        _FakeHass(),
        crop_profiles={
            "crop-a": {"crop_name": "香蕉", "area_hectares": 1.0},
            "crop-b": {"crop_name": "甘藍", "area_hectares": 2.0},
        },
        client=client,
    )

    def broken_notification(snapshot):
        raise RuntimeError("notification failed")

    module.build_agriculture_notification = broken_notification
    result = asyncio.run(coordinator._async_update_data())
    assert set(result) == {"crop-a", "crop-b"}
    assert all(
        row["agriculture_notification"]
        == "農業通知目前無法產生；請直接檢查各作物狀態。"
        for row in result.values()
    )
