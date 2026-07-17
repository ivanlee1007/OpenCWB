<a href="https://www.buymeacoffee.com/tsunglung" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="30" width="120"></a>

Home assistant support for [Opendata CWA](https://opendata.cwa.gov.tw/index) (prvious Opendata CWB). [The readme in Traditional Chinese](https://github.com/tsunglung/OpenCWB/blob/master/README_zh-tw.md).


This integration is based on [OpenWeatherMap](https://openweathermap.org) ([@csparpa](https://pypi.org/user/csparpa), [pyowm](https://github.com/csparpa/pyowm)) to develop.

## Install

You can install component with [HACS](https://hacs.xyz/) custom repo: HACS > Integrations > 3 dots (upper top corner) > Custom repositories > URL: `tsunglung/OpenCWB` > Category: Integration

Or manually copy `opencwb` folder to `custom_components` folder in your config folder.

Then restart HA.

## Latest changes

### v1.3.42
- Preserve each CWA hazardous-weather dataset's own issue time, validity window, and official description instead of mixing metadata across simultaneous alerts.
- For land strong-wind advisories, show the official yellow/orange/red level, average-wind and gust Beaufort thresholds, equivalent lower-bound speeds, validity period, danger explanation, and actionable crop/greenhouse risk guidance.
- Agricultural impacts are explicitly labelled as threshold-based guidance, not an official CWA crop-loss forecast.

### v1.3.41
- Alert only when the CWA track approaches Taiwan, may affect the configured coordinates, and an official CWA typhoon warning is active; otherwise expose `monitoring` without recommending a push notification.
- Expose closest-distance, closest-approach-time, and risk-decision attributes for explainable dashboards and automations.
- Display unnamed systems using their CWA tropical-depression number, such as `Unnamed tropical depression TD12`, instead of `Unknown ()`.

### v1.3.40
- Fix hazardous-weather notifications mixing the title and affected areas of an unmatched alert with aggregate location matches from other alerts.
- When multiple alerts match the configured location, include every matched alert in the notification and omit unrelated alerts.

### v1.3.39
- Add three ready-to-use notification sensors for official typhoon warnings, tropical cyclone pre-alerts, and hazardous weather alerts.
- Notification sensor attributes expose `title`, `message`, `severity`, `summary`, and `source_dataset` so automations can call `notify.*` without complex templates.

### v1.3.38
- Improve hazardous-weather alert location matching for CWA special areas such as `恆春半島`, `蘭嶼綠島`, `基隆北海岸`, and county mountain-area labels.
- Add `matched_locations`, `unmatched_special_areas`, and `match_method` attributes to weather alert sensors.
- Add parser regression tests for expired typhoon warnings, multiple tropical cyclones, missing track values, and special-area alert matching.
- Document optional CWA warning entities and automation examples.

### v1.3.37
- When an optional warning group is disabled in the integration options, remove its stale Home Assistant entities from the entity registry and current states.

### v1.3.36
- Add optional CWA official typhoon warning, tropical cyclone track, and hazardous weather alert entities.
- New integration options: official typhoon warning, tropical cyclone track, and hazardous weather alerts.

### v1.3.34
- Fix `onecall_daily` startup failure.
- Root cause: the current / UV one-call request was incorrectly sent to `F-D0047-093`, which returns `404 Resource not found` for the lon/lat/locationName/interval request shape.
- Switch back to `F-D0047-091` for one-call current / UV; daily forecast still comes from the existing legacy district-level forecast path.
- This keeps `onecall_daily` working without losing district-level forecast granularity.

### v1.3.13
- Fix `onecall_*` UV index lookup for township / district locations such as `新店區`.
- Keep the configured location name unchanged in Home Assistant.
- Internally upgrade district names to their parent city only for onecall current / UV requests.
- Keep forecast sensors on the original district-level forecast source, so UV works without sacrificing local forecast granularity.
- Verified live: UV index restored while forecast sensors remain normal.

### v1.3.11 - v1.3.12
- Restore forecast sensors that were stuck at `unknown` after the forecast model refactor.
- Make forecast sensor extraction compatible with both native and serialized Forecast field names.
- Remove invalid hourly `templow` handling.

### v1.3.6
- Fix the update button so it no longer depends on a non-existent coordinator attribute.
- The button now records its own status fields in attributes:
  - `update_status`
  - `last_update_time`
  - `previous_update_time`
  - `last_error` (only when refresh fails)
- Keep the button grouped under the same device as the weather/sensor entities.

### v1.3.1 - v1.3.5
- Improve Home Assistant Weather Entity compatibility.
- Return proper `Forecast` objects for daily / hourly forecast.
- Add native weather properties such as UV index and precipitation.
- Add an update button entity for immediate weather refresh.
- Fix older Home Assistant import compatibility issues.

## Optional CWA warning entities

OpenCWA can optionally create dedicated CWA warning entities. They are disabled by default to avoid extra API calls for existing users.

Enable them from **Settings > Devices & services > OpenCWA > Configure**:

- **Enable official typhoon warning** (`enable_typhoon_warning`): uses CWA `W-C0034-001` CAP data to identify an official Taiwan typhoon warning. Tropical-cyclone track data alone is not treated as an official warning.
- **Enable tropical cyclone track** (`enable_tropical_cyclone_track`): uses CWA `W-C0034-005` for active tropical cyclone track/fix data.
- **Enable hazardous weather alerts** (`enable_weather_alerts`): uses CWA hazardous-weather warnings and matches affected areas against the configured location and its parent city when available.

Created entities, using `安平區` as an example location:

| Entity | Meaning |
| --- | --- |
| `binary_sensor.opencwa_an_ping_qu_typhoon_warning` | `on` only when an official typhoon warning is currently active. `Cancel`, `END`, expired CAP messages, and解除 notices are `off`. |
| `sensor.opencwa_an_ping_qu_typhoon_warning_status` | Typhoon warning status and CAP attributes such as headline, report number, warning type, affected areas, effective/expires, and typhoon position. |
| `sensor.opencwa_an_ping_qu_typhoon_warning_notification` | Ready-to-use official typhoon warning notification payload. Attributes include `title`, `message`, `severity`, and `summary`. |
| `sensor.opencwa_an_ping_qu_tropical_cyclone` | Number of active tropical cyclones; attributes include latest fix, analysis fixes, forecast fixes, wind speed, pressure, and storm radius data. |
| `sensor.opencwa_an_ping_qu_tropical_cyclone_notification` | Ready-to-use tropical cyclone pre-alert payload. State becomes `suppressed` when an official typhoon warning is already active. |
| `binary_sensor.opencwa_an_ping_qu_weather_alert` | `on` when a hazardous-weather alert matches the configured location. |
| `sensor.opencwa_an_ping_qu_weather_alerts` | Count and details for hazardous-weather alerts. Attributes include `matched_locations`, `unmatched_special_areas`, and `match_method`. |
| `sensor.opencwa_an_ping_qu_weather_alert_notification` | Ready-to-use hazardous-weather alert notification payload with matched locations, special areas, and CWA text. Land strong-wind advisories also expose official warning level/thresholds plus clearly labelled crop and greenhouse risk guidance. |

Special-area matching covers common CWA area labels such as `恆春半島`, `蘭嶼綠島`, `基隆北海岸`, and county mountain-area labels such as `高雄山區`. Generic labels such as `山區` or `沿海空曠地區` may be reported in `unmatched_special_areas` when they cannot be safely mapped to the configured location.

Example automation:

```yaml
alias: Notify when CWA typhoon warning starts
trigger:
  - platform: state
    entity_id: binary_sensor.opencwa_an_ping_qu_typhoon_warning
    to: "on"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: CWA Typhoon Warning
      message: >-
        {{ state_attr('binary_sensor.opencwa_an_ping_qu_typhoon_warning', 'headline') }}
```

# Setup

**Apply a API key in Opendata CWA**
1. Open the [Opendata CWA](https://opendata.cwa.gov.tw/devManual/insrtuction) Web Site
2. Register your account
3. Get your personal API Key.

# Config

**Please use the config flow of Home Assistant**


1. With GUI. Configuration > Integration > Add Integration > OpneCWA
   1. If the integration didn't show up in the list please REFRESH the page
   2. If the integration is still not in the list, you need to clear the browser cache.
2. Enter API key.
3. Enter the location name of Taiwan. Please reference to the name in the [doc](https://opendata.cwa.gov.tw/opendatadoc/Opendata_City.pdf).
   1. Some location names need to include the city name.
   2. Township / district names are allowed, for example `新店區`, `板橋區`, `大安區`.
   3. For ambiguous names such as `東區`, `北區`, `中山區`, include the city name, for example `嘉義市東區` or `臺中市東區`.
   4. In `onecall_*` modes, the integration keeps your configured township / district name in Home Assistant, but internally upgrades it to the parent city only for current / UV lookup when required by the CWA onecall dataset.
   5. Forecast data still stays on the original township / district source, so using `onecall_*` does not force you to give up local forecast granularity.

Buy Me A Coffee

|  LINE Pay | LINE Bank | JKao Pay |
| :------------: | :------------: | :------------: |
| <img src="https://github.com/tsunglung/OpenCWB/blob/master/linepay.jpg" alt="Line Pay" height="200" width="200">  | <img src="https://github.com/tsunglung/OpenCWB/blob/master/linebank.jpg" alt="Line Bank" height="200" width="200">  | <img src="https://github.com/tsunglung/OpenCWB/blob/master/jkopay.jpg" alt="JKo Pay" height="200" width="200">  |
