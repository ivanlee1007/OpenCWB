<a href="https://www.buymeacoffee.com/tsunglung" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="30" width="120"></a>

Home assistant support for [Opendata CWA](https://opendata.cwa.gov.tw/index) (prvious Opendata CWB). [The readme in Traditional Chinese](https://github.com/tsunglung/OpenCWB/blob/master/README_zh-tw.md).


This integration is based on [OpenWeatherMap](https://openweathermap.org) ([@csparpa](https://pypi.org/user/csparpa), [pyowm](https://github.com/csparpa/pyowm)) to develop.

## Install

You can install component with [HACS](https://hacs.xyz/) custom repo: HACS > Integrations > 3 dots (upper top corner) > Custom repositories > URL: `tsunglung/OpenCWB` > Category: Integration

Or manually copy `opencwb` folder to `custom_components` folder in your config folder.

Then restart HA.

## Latest changes

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
