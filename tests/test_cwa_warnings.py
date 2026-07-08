from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "opencwb" / "core" / "weatherapi12"))

from warning_parser import (  # noqa: E402
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

CANCEL_TYPHOON_CAP = ACTIVE_TYPHOON_CAP.replace("<msgType>Update</msgType>", "<msgType>Cancel</msgType>").replace("海上陸上颱風警報", "解除颱風警報").replace("<section title=\"警報類別\">海上陸上</section>", "<section title=\"警報類別\">END</section>")

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
    parsed = parse_weather_alerts(ALERTS_XML.replace("苗栗縣", "恆春半島"), location_name=["屏東縣", "恆春鎮"], now=datetime(2026, 7, 8, tzinfo=timezone.utc))

    assert parsed["active_for_location"] is True
    assert parsed["matched_locations"] == ["恆春半島"]
    assert parsed["match_method"] == "special_area"
    assert parsed["alerts"][0]["matched_locations"] == ["恆春半島"]
    assert parsed["alerts"][0]["match_method"] == "special_area"


def test_weather_alerts_collect_unmatched_special_areas():
    parsed = parse_weather_alerts(ALERTS_XML.replace("苗栗縣", "蘭嶼綠島"), location_name=["臺南市", "安平區"], now=datetime(2026, 7, 8, tzinfo=timezone.utc))

    assert parsed["active_for_location"] is False
    assert parsed["matched_locations"] == []
    assert parsed["unmatched_special_areas"] == ["蘭嶼綠島"]
    assert parsed["alerts"][0]["unmatched_special_areas"] == ["蘭嶼綠島"]
