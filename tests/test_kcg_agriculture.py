from datetime import datetime, timezone
import json
from pathlib import Path
import sys

AGRI_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "opencwb" / "core" / "agriculture"
COMPONENT_PATH = AGRI_PATH.parents[1]
sys.path.insert(0, str(COMPONENT_PATH))
sys.path.insert(0, str(AGRI_PATH))

from agriculture_state import (  # noqa: E402
    agriculture_binary_available,
    agriculture_sensor_available,
)
import kcg_client  # noqa: E402
from kcg_client import KCGOpenDataClient  # noqa: E402
from kcg_parser import (  # noqa: E402
    KCGDataError,
    build_agriculture_notification,
    build_agriculture_snapshot,
    parse_business_payload,
    parse_irrigation_reference,
    is_successful_agriculture_cache,
)


ALERT_ROWS = [
    {
        "CITY_NAME": "臺中市",
        "TOWN_NAME": "新社區",
        "C_NAME": "香蕉",
        "Disaster": "高溫",
        "GROWTH": "結果期",
        "STAGE": "果實發育",
        "DURATION": "連續3日",
        "THRESHOLD": "36",
        "MEASURES": "°C",
        "REAL_VALUE": "37.2",
        "EFFECT": "果實可能受高溫影響",
        "PREVENTION": "加強灌溉與遮陰",
        "RECOVERY": "巡查受害植株",
        "TIMESTAMP": "2026-07-18T23:05:01",
        "Note": 4,
    },
    {
        "CITY_NAME": "臺中市",
        "TOWN_NAME": "新社區",
        "C_NAME": "香蕉",
        "Disaster": "注意霪雨",
        "GROWTH": "結果期",
        "TIMESTAMP": "2026-07-18T18:10:00",
        "PREVENTION": "清理排水溝",
        "Note": "6",
    },
    {
        "CITY_NAME": "臺中市",
        "TOWN_NAME": "和平區",
        "C_NAME": "香蕉",
        "Disaster": "注意降溫",
        "TIMESTAMP": "2026-07-18T18:10:00",
        "Note": 10,
    },
    {
        "CITY_NAME": "臺中市",
        "TOWN_NAME": "新社區",
        "C_NAME": "甘藍",
        "Disaster": "注意高溫",
        "TIMESTAMP": "2026-07-18T18:10:00",
        "Note": 7,
    },
]


def test_business_payload_rejects_http_200_business_error_without_secret_echo():
    secret = "very-secret-token-value"
    try:
        parse_business_payload({"Status": 400, "Message": f"Token {secret} 驗證失敗"})
    except KCGDataError as error:
        assert str(error) == "Agricultural provider rejected the request"
        assert secret not in str(error)
    else:
        raise AssertionError("Expected KCGDataError")


def test_business_payload_accepts_lowercase_success_and_text_json():
    payload = parse_business_payload('{"status":200,"message":"獲取作物","crops":[]}')
    assert payload["crops"] == []
    double_encoded = json.dumps('{"status":200,"message":"獲取作物","crops":[]}')
    assert parse_business_payload(double_encoded)["crops"] == []


def test_business_payload_rejects_mapping_without_business_status():
    try:
        parse_business_payload({"crops": []})
    except KCGDataError as error:
        assert error.code == "malformed_response"
    else:
        raise AssertionError("Expected KCGDataError")


def test_business_payload_rejects_bool_float_and_non_200_status_types():
    for status in (True, False, 1, 200.0, None, [200], {"value": 200}):
        try:
            parse_business_payload({"status": status, "crops": []})
        except KCGDataError as error:
            assert error.code == "business_error"
        else:
            raise AssertionError(f"Expected KCGDataError for status {status!r}")


def test_snapshot_filters_exact_crop_town_and_classifies_note():
    snapshot = build_agriculture_snapshot(
        ALERT_ROWS,
        city="臺中市",
        town="新社區",
        crop="香蕉",
        growth_stage="結果期",
        now=datetime(2026, 7, 19, tzinfo=timezone.utc),
    )

    assert snapshot["supported"] is True
    assert snapshot["warning_count"] == 1
    assert snapshot["advisory_count"] == 1
    assert snapshot["warning_active"] is True
    assert snapshot["advisory_active"] is True
    assert {item["classification"] for item in snapshot["items"]} == {"warning", "advisory"}
    assert all(item["crop"] == "香蕉" for item in snapshot["items"])
    assert all(item["town"] == "新社區" for item in snapshot["items"])
    assert snapshot["source_timestamp"] == "2026-07-18T23:05:01"
    assert snapshot["stale"] is False


def test_snapshot_reports_unsupported_instead_of_safe_or_zero():
    snapshot = build_agriculture_snapshot(
        ALERT_ROWS,
        city="臺中市",
        town="新社區",
        crop="藍莓",
        supported_crops={"香蕉", "甘藍"},
        now=datetime(2026, 7, 19, tzinfo=timezone.utc),
    )

    assert snapshot["supported"] is False
    assert snapshot["status"] == "unsupported"
    assert snapshot["warning_active"] is False
    assert snapshot["advisory_active"] is False
    assert snapshot["items"] == []


def test_snapshot_marks_old_source_data_stale():
    snapshot = build_agriculture_snapshot(
        ALERT_ROWS,
        city="臺中市",
        town="新社區",
        crop="香蕉",
        now=datetime(2026, 7, 21, tzinfo=timezone.utc),
        stale_after_hours=30,
    )
    assert snapshot["stale"] is True
    assert snapshot["status"] == "stale"


def test_snapshot_rejects_future_source_timestamp_as_unknown():
    rows = [dict(ALERT_ROWS[0], TIMESTAMP="2026-07-21T00:00:00")]
    snapshot = build_agriculture_snapshot(
        rows,
        city="臺中市",
        town="新社區",
        crop="香蕉",
        now=datetime(2026, 7, 19, tzinfo=timezone.utc),
    )
    assert snapshot["status"] == "unknown"
    assert snapshot["warning_active"] is False
    assert snapshot["advisory_active"] is False
    assert snapshot["timestamp_invalid"] is True


def test_snapshot_rejects_timestamp_even_one_second_in_future():
    rows = [dict(ALERT_ROWS[0], TIMESTAMP="2026-07-19T08:00:01+08:00")]
    snapshot = build_agriculture_snapshot(
        rows,
        city="臺中市",
        town="新社區",
        crop="香蕉",
        now=datetime(2026, 7, 19, tzinfo=timezone.utc),
    )
    assert snapshot["status"] == "unknown"
    assert snapshot["warning_active"] is False
    assert snapshot["timestamp_invalid"] is True


def test_snapshot_does_not_reactivate_old_warning_with_newer_advisory():
    rows = [
        dict(ALERT_ROWS[0], TIMESTAMP="2026-07-17T00:00:00"),
        dict(ALERT_ROWS[1], TIMESTAMP="2026-07-18T23:00:00"),
    ]
    snapshot = build_agriculture_snapshot(
        rows,
        city="臺中市",
        town="新社區",
        crop="香蕉",
        now=datetime(2026, 7, 19, tzinfo=timezone.utc),
        stale_after_hours=30,
    )
    assert snapshot["warning_count"] == 1
    assert snapshot["advisory_count"] == 1
    assert snapshot["warning_active"] is False
    assert snapshot["advisory_active"] is True
    assert snapshot["status"] == "advisory"
    warning = next(item for item in snapshot["items"] if item["classification"] == "warning")
    assert warning["stale"] is True

    notification = build_agriculture_notification(snapshot)
    assert notification["severity"] == "advisory"
    assert "注意霪雨" in notification["title"]


def test_notification_finds_fresh_warning_beyond_truncated_items():
    rows = [
        dict(ALERT_ROWS[1], Disaster=f"注意事件{i}", TIMESTAMP="2026-07-18T23:00:00")
        for i in range(25)
    ]
    rows.append(
        dict(ALERT_ROWS[0], Disaster="第26筆高溫", TIMESTAMP="2026-07-18T23:05:00")
    )
    snapshot = build_agriculture_snapshot(
        rows,
        city="臺中市",
        town="新社區",
        crop="香蕉",
        now=datetime(2026, 7, 19, tzinfo=timezone.utc),
    )
    assert snapshot["items_truncated"] is True
    assert all(item["classification"] == "advisory" for item in snapshot["items"])

    notification = build_agriculture_notification(snapshot)
    assert notification["severity"] == "warning"
    assert "第26筆高溫" in notification["title"]


def test_irrigation_reference_keeps_missing_crop_values_none():
    result = parse_irrigation_reference(
        et0_payload={
            "Status": 200,
            "Message": "成功",
            "Lon": 120.65,
            "Lat": 24.17,
            "Data": [{"Date": "2026-07-18", "Et0": 6.0125}],
        },
        kc_payload={"Status": 400, "Message": "找不到對應的作物係數資料"},
        etc_payload={"Status": 400, "Message": "找不到對應的作物資料"},
    )

    assert result["et0"] == 6.0125
    assert result["source_longitude"] == 120.65
    assert result["source_latitude"] == 24.17
    assert result["kc"] is None
    assert result["etc"] is None
    assert result["water_requirement"] is None
    assert result["crop_water_supported"] is False


def test_partial_irrigation_response_keeps_each_valid_numeric_sensor_available():
    result = parse_irrigation_reference(
        et0_payload={"Status": 400, "Message": "no ET0"},
        kc_payload={"Status": 200, "Data": [{"Kc": 0.85}]},
        etc_payload={
            "Status": 200,
            "Data": [{"Etc": 3.4, "WaterRequirement": 34.0}],
        },
    )

    assert result["available"] is True
    assert result["et0"] is None
    snapshot = {"provider_available": True, "stale": False, "status": "advisory"}
    assert agriculture_sensor_available(
        snapshot, "agriculture_et0", result["et0"], irrigation=result
    ) is False
    assert agriculture_sensor_available(
        snapshot, "agriculture_kc", result["kc"], irrigation=result
    ) is True
    assert agriculture_sensor_available(
        snapshot, "agriculture_etc", result["etc"], irrigation=result
    ) is True
    assert agriculture_sensor_available(
        snapshot,
        "agriculture_water_requirement",
        result["water_requirement"],
        irrigation=result,
    ) is True


def test_client_keeps_partial_irrigation_values_when_et0_has_business_error(
    monkeypatch,
):
    client = KCGOpenDataClient(token="test-token", session=_FakeSession([]))

    def fail_et0(*args, **kwargs):
        raise KCGDataError("provider rejected ET0", code="business_error")

    monkeypatch.setattr(client, "daily_et0", fail_et0)
    monkeypatch.setattr(
        client,
        "crop_coefficient",
        lambda crop: {"Status": 200, "Data": [{"Kc": 0.85}]},
    )
    monkeypatch.setattr(
        client,
        "crop_etc",
        lambda **kwargs: {
            "Status": 200,
            "Data": [{"Etc": 3.4, "WaterRequirement": 34.0}],
        },
    )

    result = client.irrigation_reference(
        latitude=24.1,
        longitude=120.6,
        crop="香蕉",
        planting_date="2026-07-01",
        area_hectares=1.0,
    )

    assert result["available"] is True
    assert result["et0"] is None
    assert result["kc"] == 0.85
    assert result["etc"] == 3.4
    assert result["water_requirement"] == 34.0


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self.text = payload
        self.status_code = status_code
        self.headers = {}
        self.encoding = "utf-8"
        self.closed = False

    def iter_content(self, chunk_size=65536):
        encoded = self.text.encode(self.encoding)
        for start in range(0, len(encoded), chunk_size):
            yield encoded[start:start + chunk_size]

    def close(self):
        self.closed = True


class _FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.trust_env = True

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_client_queries_only_configured_city_and_redacts_token_from_errors():
    session = _FakeSession([
        _FakeResponse('{"status":200,"message":"獲取作物","crops":[]}'),
        _FakeResponse('{"Status":400,"Message":"Token 驗證失敗"}'),
    ])
    client = KCGOpenDataClient(token="secret-token", session=session)

    assert client.crop_weather("臺中市") == []
    first_url, first_kwargs = session.calls[0]
    assert first_url.endswith("/cropweatherTaiwan")
    assert first_kwargs["params"]["CITY_NAME"] == "臺中市"
    assert "TOKEN" not in first_kwargs["params"]

    try:
        client.daily_et0(24.1, 120.6, "2026-07-18", "2026-07-18")
    except KCGDataError as error:
        assert "secret-token" not in str(error)
    else:
        raise AssertionError("Expected KCGDataError")
    assert session.calls[1][1]["params"]["TOKEN"] == "secret-token"


def test_client_skips_token_gated_irrigation_calls_without_token():
    client = KCGOpenDataClient(token=None, session=_FakeSession([]))
    assert client.irrigation_reference(
        latitude=24.1,
        longitude=120.6,
        crop="香蕉",
        planting_date="2026-01-01",
        area_hectares=0.1,
    )["available"] is False
    assert client.session.calls == []


def test_client_rejects_missing_or_non_list_collection_fields():
    for payload in (
        '{"status":200,"message":"ok"}',
        '{"status":200,"message":"ok","crops":{}}',
    ):
        client = KCGOpenDataClient(session=_FakeSession([_FakeResponse(payload)]))
        try:
            client.crop_weather("臺中市")
        except KCGDataError as error:
            assert error.code == "malformed_response"
        else:
            raise AssertionError("Expected KCGDataError")


def test_client_streams_and_closes_response_when_size_limit_is_exceeded(monkeypatch):
    monkeypatch.setattr(kcg_client, "MAX_RESPONSE_BYTES", 16)
    response = _FakeResponse('{"status":200,"crops":[]}')
    client = KCGOpenDataClient(session=_FakeSession([response]))
    try:
        client.crop_weather("臺中市")
    except KCGDataError as error:
        assert error.code == "response_too_large"
    else:
        raise AssertionError("Expected KCGDataError")
    assert response.closed is True
    assert client.session.calls[0][1]["stream"] is True


def test_notification_prioritizes_warning_and_contains_agricultural_actions():
    snapshot = build_agriculture_snapshot(
        ALERT_ROWS,
        city="臺中市",
        town="新社區",
        crop="香蕉",
        now=datetime(2026, 7, 19, tzinfo=timezone.utc),
    )
    notification = build_agriculture_notification(snapshot)

    assert notification["status"] == "active"
    assert notification["severity"] == "warning"
    assert notification["title"] == "⚠️ 香蕉－高溫農業警戒"
    assert "可能影響：果實可能受高溫影響" in notification["message"]
    assert "防範建議：加強灌溉與遮陰" in notification["message"]
    assert "復耕建議：巡查受害植株" in notification["message"]
    assert notification["source_dataset"] == "kcg_agri_cropweather_taiwan"
    assert notification["official_cwa_alert"] is False


def test_notification_never_marks_stale_or_unsupported_data_active():
    unsupported = build_agriculture_snapshot(
        ALERT_ROWS,
        city="臺中市",
        crop="藍莓",
        supported_crops={"香蕉"},
    )
    notification = build_agriculture_notification(unsupported)
    assert notification["status"] == "unsupported"
    assert notification["active"] is False


def test_snapshot_caps_entity_attribute_items_but_preserves_counts():
    rows = [dict(ALERT_ROWS[1], Disaster=f"注意事件{i}") for i in range(30)]
    snapshot = build_agriculture_snapshot(
        rows,
        city="臺中市",
        town="新社區",
        crop="香蕉",
        now=datetime(2026, 7, 19, tzinfo=timezone.utc),
    )
    assert snapshot["advisory_count"] == 30
    assert snapshot["matched_total"] == 30
    assert len(snapshot["items"]) == 25
    assert snapshot["items_truncated"] is True


def test_snapshot_uses_no_data_instead_of_claiming_safe_when_filter_has_no_rows():
    snapshot = build_agriculture_snapshot(
        ALERT_ROWS,
        city="臺中市",
        town="新社區",
        crop="不存在的作物",
        supported_crops=None,
    )
    assert snapshot["status"] == "no_data"
    assert snapshot["warning_active"] is False
    assert snapshot["advisory_active"] is False


def test_snapshot_with_unknown_note_or_timestamp_is_unknown_not_clear_or_advisory():
    snapshot = build_agriculture_snapshot(
        [{
            "CITY_NAME": "臺中市",
            "TOWN_NAME": "新社區",
            "C_NAME": "香蕉",
            "Disaster": "格式未知",
            "Note": None,
            "TIMESTAMP": "",
        }],
        city="臺中市",
        town="新社區",
        crop="香蕉",
    )
    assert snapshot["status"] == "unknown"
    assert snapshot["warning_count"] == 0
    assert snapshot["advisory_count"] == 0
    assert snapshot["items"][0]["classification"] == "unknown"


def test_snapshot_normalizes_tai_taiwan_place_name_variant():
    snapshot = build_agriculture_snapshot(
        ALERT_ROWS,
        city="台中市",
        town="新社區",
        crop="香蕉",
        now=datetime(2026, 7, 19, tzinfo=timezone.utc),
    )
    assert snapshot["matched_total"] == 2


def test_agriculture_entity_availability_does_not_present_unknown_as_safe():
    valid = {"provider_available": True, "stale": False, "status": "warning"}
    assert agriculture_binary_available(valid, "agriculture_warning") is True
    assert agriculture_sensor_available(valid, "agriculture", valid) is True

    for status in ("unavailable", "stale", "unknown", "no_data"):
        snapshot = {
            "provider_available": status not in ("unavailable", "stale"),
            "stale": status == "stale",
            "status": status,
        }
        assert agriculture_binary_available(snapshot, "agriculture_warning") is False
        assert agriculture_binary_available(snapshot, "agriculture_advisory") is False
        assert agriculture_sensor_available(snapshot, "agriculture", snapshot) is True

    not_configured = {
        "provider_available": None,
        "stale": False,
        "status": "not_configured",
    }
    assert agriculture_sensor_available(
        not_configured, "agriculture", not_configured
    ) is True


def test_supported_binary_distinguishes_unsupported_from_unknown():
    unsupported = {
        "provider_available": True,
        "stale": False,
        "status": "unsupported",
    }
    unknown = {"provider_available": True, "stale": False, "status": "unknown"}
    assert agriculture_binary_available(unsupported, "agriculture_supported") is True
    assert agriculture_binary_available(unknown, "agriculture_supported") is False


def test_irrigation_sensor_requires_available_value():
    snapshot = {"provider_available": True, "stale": False, "status": "advisory"}
    assert agriculture_sensor_available(
        snapshot,
        "agriculture_et0",
        4.2,
        irrigation={"available": True},
    ) is True
    assert agriculture_sensor_available(
        snapshot,
        "agriculture_et0",
        None,
        irrigation={"available": False},
    ) is False


def test_only_a_prior_success_can_be_reused_as_stale_cache():
    assert is_successful_agriculture_cache({"status": "unavailable"}) is False
    assert is_successful_agriculture_cache({"status": "not_configured"}) is False
    assert is_successful_agriculture_cache({
        "status": "advisory",
        "last_success_at": "2026-07-19T00:00:00+00:00",
    }) is True
