from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "opencwb" / "core" / "weatherapi12"))

from warning_parser import (  # noqa: E402
    _wind_advisory,
    parse_tropical_cyclone_track,
    parse_typhoon_warning_cap,
    parse_weather_alerts,
)


ACTIVE_TYPHOON_CAP = """<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>CWA-Weather_typhoon-warning_1</identifier>
  <sender>weather@cwa.gov.tw</sender>
  <sent>2026-07-08T08:00:00+08:00</sent>
  <status>Actual</status>
  <msgType>Update</msgType>
  <scope>Public</scope>
  <info>
    <language>zh-TW</language>
    <event>颱風</event>
    <effective>2026-07-08T08:00:00+08:00</effective>
    <expires>2099-07-08T14:00:00+08:00</expires>
    <headline>海上陸上颱風警報</headline>
    <description>
      <typhoon-info>
        <section title="警報報數">3</section>
        <section title="警報類別">海上陸上</section>
        <section title="颱風資訊">
          <typhoon_name>BAVI</typhoon_name>
          <cwa_typhoon_name>巴威</cwa_typhoon_name>
          <analysis>
            <time>2026-07-08T00:00:00+00:00</time>
            <position>22.00,120.80</position>
          </analysis>
        </section>
      </typhoon-info>
    </description>
    <web>https://www.cwa.gov.tw/V8/C/P/Warning/FIFOWS.html</web>
    <area><areaDesc>臺北市</areaDesc></area>
    <area><areaDesc>新北市</areaDesc></area>
  </info>
</alert>
"""

CANCEL_TYPHOON_CAP = (
    ACTIVE_TYPHOON_CAP
    .replace("<msgType>Update</msgType>", "<msgType>Cancel</msgType>")
    .replace("海上陸上颱風警報", "解除颱風警報")
    .replace("<section title=\"警報類別\">海上陸上</section>", "<section title=\"警報類別\">END</section>")
)

TRACK_XML = """<?xml version="1.0" encoding="utf-8"?>
<cwaopendata xmlns="urn:cwa:gov:tw:cwacommon:0.1">
  <Identifier>CWA-TropicalCyclone_20260708205722</Identifier>
  <Dataset>
    <TropicalCyclones>
      <TropicalCyclone>
        <Year>2026</Year>
        <TyphoonName>BAVI</TyphoonName>
        <CwaTyphoonName>巴威</CwaTyphoonName>
        <CwaTyNo>09</CwaTyNo>
        <AnalysisData>
          <Fix>
            <DateTime>2026-07-08T08:00:00+08:00</DateTime>
            <CoordinateLongitude>123.4</CoordinateLongitude>
            <CoordinateLatitude>21.5</CoordinateLatitude>
            <MaxWindSpeed>33</MaxWindSpeed>
            <MaxGustSpeed>43</MaxGustSpeed>
            <Pressure>970</Pressure>
            <MovingSpeed>20</MovingSpeed>
            <MovingDirection>NW</MovingDirection>
            <Circle15ms><Radius>150</Radius></Circle15ms>
            <Circle25ms><Radius>50</Radius></Circle25ms>
          </Fix>
        </AnalysisData>
        <ForecastData>
          <Fix>
            <DateTime>2026-07-08T14:00:00+08:00</DateTime>
            <CoordinateLongitude>122.9</CoordinateLongitude>
            <CoordinateLatitude>22.1</CoordinateLatitude>
            <MaxWindSpeed>35</MaxWindSpeed>
            <Pressure>965</Pressure>
          </Fix>
        </ForecastData>
      </TropicalCyclone>
    </TropicalCyclones>
  </Dataset>
</cwaopendata>
"""

ALERTS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<cwaopendata xmlns="urn:cwa:gov:tw:cwacommon:0.1">
  <identifier>CWA-Weather_hazards_1</identifier>
  <dataset>
    <datasetInfo>
      <datasetDescription>陸上強風特報</datasetDescription>
      <issueTime>2026-07-08T22:25:00+08:00</issueTime>
      <validTime><startTime>2026-07-09T14:00:00+08:00</startTime><endTime>2099-07-09T23:00:00+08:00</endTime></validTime>
    </datasetInfo>
    <contents><content><contentText>請注意強風。</contentText></content></contents>
    <hazardConditions>
      <hazards><hazard><info>
        <phenomena>陸上強風</phenomena>
        <significance>特報</significance>
        <affectedAreas>
          <location><locationName>苗栗縣</locationName></location>
          <location><locationName>高雄市</locationName></location>
        </affectedAreas>
      </info></hazard></hazards>
    </hazardConditions>
  </dataset>
</cwaopendata>
"""


def test_active_typhoon_warning_cap_is_on_and_extracts_core_fields():
    parsed = parse_typhoon_warning_cap(ACTIVE_TYPHOON_CAP, now=datetime(2026, 7, 8, tzinfo=timezone.utc))

    assert parsed["active"] is True
    assert parsed["headline"] == "海上陸上颱風警報"
    assert parsed["msg_type"] == "Update"
    assert parsed["warning_type"] == "海上陸上"
    assert parsed["report_no"] == "3"
    assert parsed["affected_areas"] == ["臺北市", "新北市"]
    assert parsed["typhoon"]["name"] == "BAVI"
    assert parsed["typhoon"]["cwa_name"] == "巴威"
    assert parsed["typhoon"]["analysis_position"] == [22.0, 120.8]


def test_cancel_or_end_typhoon_warning_cap_is_not_active():
    parsed = parse_typhoon_warning_cap(CANCEL_TYPHOON_CAP, now=datetime(2026, 7, 8, tzinfo=timezone.utc))

    assert parsed["active"] is False
    assert parsed["msg_type"] == "Cancel"
    assert parsed["warning_type"] == "END"


def test_tropical_cyclone_track_counts_cyclones_and_latest_fix():
    parsed = parse_tropical_cyclone_track(TRACK_XML)

    assert parsed["count"] == 1
    cyclone = parsed["cyclones"][0]
    assert cyclone["name"] == "BAVI"
    assert cyclone["cwa_name"] == "巴威"
    assert cyclone["cwa_ty_no"] == "09"
    assert cyclone["latest_fix"]["latitude"] == 21.5
    assert cyclone["latest_fix"]["longitude"] == 123.4
    assert cyclone["latest_fix"]["circle_15ms"] == 150.0
    assert cyclone["forecast_fixes"][0]["pressure"] == 965.0


def test_weather_alerts_extracts_active_alerts_and_location_match():
    parsed = parse_weather_alerts(ALERTS_XML, location_name="高雄市", now=datetime(2026, 7, 8, tzinfo=timezone.utc))

    assert parsed["count"] == 1
    assert parsed["active_for_location"] is True
    assert parsed["matched_locations"] == ["高雄市"]
    assert parsed["match_method"] == "direct"
    alert = parsed["alerts"][0]
    assert alert["phenomena"] == "陸上強風"
    assert alert["significance"] == "特報"
    assert alert["affected_areas"] == ["苗栗縣", "高雄市"]
    assert alert["matched_locations"] == ["高雄市"]
    assert alert["match_method"] == "direct"
    assert "強風" in alert["content_text"]


def test_weather_alerts_keep_metadata_per_dataset_and_extract_wind_advisory():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <cwaopendata>
      <dataset>
        <datasetInfo>
          <datasetDescription>大雨特報</datasetDescription>
          <issueTime>2026-07-17T20:55:00+08:00</issueTime>
          <validTime>
            <startTime>2026-07-17T20:58:00+08:00</startTime>
            <endTime>2026-07-18T10:00:00+08:00</endTime>
          </validTime>
        </datasetInfo>
        <contents><content><contentText>南部地區有局部大雨。</contentText></content></contents>
        <hazardConditions><hazards><hazard><info>
          <phenomena>大雨</phenomena><significance>特報</significance>
          <affectedAreas><location><locationName>臺南市</locationName></location></affectedAreas>
        </info></hazard></hazards></hazardConditions>
      </dataset>
      <dataset>
        <datasetInfo>
          <datasetDescription>陸上強風特報</datasetDescription>
          <issueTime>2026-07-17T16:22:00+08:00</issueTime>
          <validTime>
            <startTime>2026-07-17T16:22:00+08:00</startTime>
            <endTime>2026-07-18T23:00:00+08:00</endTime>
          </validTime>
        </datasetInfo>
        <contents><content><contentText>
          西南風偏強，臺中市局部地區有平均風6級以上或陣風8級以上發生的機率(黃色燈號)，請注意。
          黃色燈號：注意戶外掉落物並加強牢固戶外物品。
        </contentText></content></contents>
        <hazardConditions><hazards><hazard><info>
          <phenomena>陸上強風</phenomena><significance>特報</significance>
          <affectedAreas><location><locationName>臺中市</locationName></location></affectedAreas>
        </info></hazard></hazards></hazardConditions>
      </dataset>
    </cwaopendata>"""

    parsed = parse_weather_alerts(
        xml,
        location_name="臺中市",
        now=datetime(2026, 7, 17, 13, tzinfo=timezone.utc),
    )

    assert parsed["count"] == 2
    assert parsed["alerts"][0]["content_text"] == "南部地區有局部大雨。"
    wind = parsed["alerts"][1]
    assert wind["issue_time"] == "2026-07-17T16:22:00+08:00"
    assert wind["start_time"] == "2026-07-17T16:22:00+08:00"
    assert wind["end_time"] == "2026-07-18T23:00:00+08:00"
    assert "平均風6級以上" in wind["content_text"]
    assert wind["wind_advisory"] == {
        "warning_level": "yellow",
        "warning_level_label": "黃色燈號",
        "danger_level": "注意",
        "average_wind_beaufort_min": 6,
        "gust_beaufort_min": 8,
        "average_wind_speed_min_m_s": 10.8,
        "gust_speed_min_m_s": 17.2,
        "crop_risk_level": "中度",
        "crop_impacts": [
            "高稈、莖葉柔軟或已結果作物可能倒伏、折枝、落花落果",
            "葉片可能撕裂或出現風灼，幼苗與新梢較敏感",
            "棚架、支柱、防蟲網、遮陰網與溫室外膜可能鬆脫或破損",
            "盆栽、育苗盤、資材及未固定物可能傾倒或被吹落",
        ],
        "recommended_actions": [
            "加固棚架、支柱、網布與溫室外膜，收妥或綁牢戶外資材",
            "為高稈、結果中及幼苗作物加設支撐，提前採收可採收果實",
            "暫停高處、網室屋頂及迎風面作業，巡查排水與供電安全",
        ],
        "assessment_note": "農業風險為依 CWA 風力門檻整理的提示，並非 CWA 官方農損預測。",
    }


def test_weather_alerts_ignore_outer_dataset_wrapper_and_expired_nested_dataset():
    xml = """<cwaopendata xmlns="urn:cwa:gov:tw:cwacommon:0.1">
      <Dataset>
        <dataset>
          <datasetInfo>
            <issueTime>2026-07-16T08:00:00+08:00</issueTime>
            <validTime><endTime>2026-07-16T12:00:00+08:00</endTime></validTime>
          </datasetInfo>
          <contents><content><contentText>已過期的大雨資料。</contentText></content></contents>
          <hazardConditions><hazards><hazard><info>
            <phenomena>大雨</phenomena><significance>特報</significance>
            <affectedAreas><location><locationName>臺中市</locationName></location></affectedAreas>
          </info></hazard></hazards></hazardConditions>
        </dataset>
        <dataset>
          <datasetInfo>
            <issueTime>2026-07-17T16:22:00+08:00</issueTime>
            <validTime><endTime>2026-07-18T23:00:00+08:00</endTime></validTime>
          </datasetInfo>
          <contents><content><contentText>
            平均風6級以上或陣風8級以上發生的機率（黃色燈號）。
          </contentText></content></contents>
          <hazardConditions><hazards><hazard><info>
            <phenomena>陸上強風</phenomena><significance>特報</significance>
            <affectedAreas><location><locationName>臺中市</locationName></location></affectedAreas>
          </info></hazard></hazards></hazardConditions>
        </dataset>
      </Dataset>
    </cwaopendata>"""

    parsed = parse_weather_alerts(
        xml,
        location_name="臺中市",
        now=datetime(2026, 7, 17, 13, tzinfo=timezone.utc),
    )

    assert parsed["count"] == 1
    assert parsed["alerts"][0]["phenomena"] == "陸上強風"
    assert parsed["alerts"][0]["issue_time"] == "2026-07-17T16:22:00+08:00"
    assert parsed["alerts"][0]["wind_advisory"]["warning_level"] == "yellow"


def test_wind_advisory_supports_official_orange_and_red_thresholds():
    orange = _wind_advisory("平均風9級以上或陣風11級以上（橙色燈號）")
    red = _wind_advisory("平均風12級以上或陣風14級以上（紅色燈號）")

    assert orange["warning_level"] == "orange"
    assert orange["danger_level"] == "警戒"
    assert orange["average_wind_beaufort_min"] == 9
    assert orange["gust_beaufort_min"] == 11
    assert orange["average_wind_speed_min_m_s"] == 20.8
    assert orange["gust_speed_min_m_s"] == 28.5
    assert orange["crop_risk_level"] == "高"

    assert red["warning_level"] == "red"
    assert red["danger_level"] == "嚴重警戒"
    assert red["average_wind_beaufort_min"] == 12
    assert red["gust_beaufort_min"] == 14
    assert red["average_wind_speed_min_m_s"] == 32.7
    assert red["gust_speed_min_m_s"] == 41.5
    assert red["crop_risk_level"] == "極高"


def test_expired_typhoon_warning_cap_is_not_active():
    parsed = parse_typhoon_warning_cap(
        ACTIVE_TYPHOON_CAP.replace("2099-07-08T14:00:00+08:00", "2026-07-08T07:00:00+08:00"),
        now=datetime(2026, 7, 8, tzinfo=timezone.utc),
    )

    assert parsed["active"] is False
    assert parsed["warning_type"] == "海上陸上"


def test_tropical_cyclone_track_handles_multiple_cyclones_and_missing_values():
    second_cyclone = """
      <TropicalCyclone>
        <Year>2026</Year>
        <TyphoonName>NOFIX</TyphoonName>
        <CwaTyphoonName>無定位</CwaTyphoonName>
        <AnalysisData></AnalysisData>
      </TropicalCyclone>
    """
    xml = TRACK_XML.replace("    </TropicalCyclones>", second_cyclone + "\n    </TropicalCyclones>")

    parsed = parse_tropical_cyclone_track(xml)

    assert parsed["count"] == 2
    assert parsed["cyclones"][1]["name"] == "NOFIX"
    assert parsed["cyclones"][1]["latest_fix"] is None
    assert parsed["cyclones"][1]["analysis_fixes"] == []


def test_weather_alerts_match_special_area_to_district_and_report_method():
    parsed = parse_weather_alerts(
        ALERTS_XML.replace("苗栗縣", "恆春半島"),
        location_name=["屏東縣", "恆春鎮"],
        now=datetime(2026, 7, 8, tzinfo=timezone.utc),
    )

    assert parsed["active_for_location"] is True
    assert parsed["matched_locations"] == ["恆春半島"]
    assert parsed["match_method"] == "special_area"
    assert parsed["alerts"][0]["matched_locations"] == ["恆春半島"]
    assert parsed["alerts"][0]["match_method"] == "special_area"


def test_weather_alerts_collect_unmatched_special_areas():
    parsed = parse_weather_alerts(
        ALERTS_XML.replace("苗栗縣", "蘭嶼綠島"),
        location_name=["臺南市", "安平區"],
        now=datetime(2026, 7, 8, tzinfo=timezone.utc),
    )

    assert parsed["active_for_location"] is False
    assert parsed["matched_locations"] == []
    assert parsed["unmatched_special_areas"] == ["蘭嶼綠島"]
    assert parsed["alerts"][0]["unmatched_special_areas"] == ["蘭嶼綠島"]
