<a href="https://www.buymeacoffee.com/tsunglung" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="30" width="120"></a>

中央氣象署-開放資料平臺 [Opendata CWA](https://opendata.cwb.gov.tw/index)(前身 中央氣象局) 支援 Home Assistant


這個整合是基於 [OpenWeatherMap](https://openweathermap.org) ([@csparpa](https://pypi.org/user/csparpa), [pyowm](https://github.com/csparpa/pyowm)) 所做的開發。

# 安裝

你可以用 [HACS](https://hacs.xyz/) 來安裝這個整合。 步驟如下 custom repo: HACS > Integrations > 3 dots (upper top corner) > Custom repositories > URL: `tsunglung/OpenCWB` > Category: Integration

或是手動複製 `opencwb` 資料夾到你的 config 資料夾的  `custom_components` 目錄下。

然後重新啟動 Home Assistant.

## 最新更新

### v1.3.38
- 強化重大氣象警特報的地區比對，支援 `恆春半島`、`蘭嶼綠島`、`基隆北海岸` 與各縣市山區等 CWA 特殊區域名稱。
- 在警特報實體屬性新增 `matched_locations`、`unmatched_special_areas`、`match_method`，方便判斷為什麼有/沒有命中目前地點。
- 補上 parser regression tests：過期颱風警報、多個熱帶氣旋、缺漏路徑欄位、特殊區域警特報比對。
- 補上官方警報與災害資訊 entities 的使用文件與 automation 範例。

### v1.3.37
- 當使用者在整合選項關閉任一 warning 大項時，自動移除對應的舊 Home Assistant entities，避免關閉後實體仍殘留。

### v1.3.36
- 新增選用的 CWA 官方颱風警報、熱帶氣旋路徑、重大氣象警特報 entities。
- 整合設定頁新增三個開關：官方颱風警報、熱帶氣旋路徑、重大氣象警特報。

### v1.3.34
- 修正 `onecall_daily` 啟動失敗問題。
- 根因是 current / UV one-call 查詢誤打到 `F-D0047-093`，CWA 會回 `404 Resource not found`。
- 改回固定使用 `F-D0047-091` 取得 one-call current / UV；daily forecast 仍由既有 legacy 區級預報路徑提供。
- 這樣 `onecall_daily` 可正常 setup，同時保留區級 forecast 粒度。

### v1.3.13
- 修正 `onecall_*` 模式下，鄉鎮 / 區級地名（例如 `新店區`）拿不到 UV index 的問題。
- Home Assistant 中的設定名稱不需要改成縣市，仍可維持原本的區級名稱。
- 程式內部只在 onecall current / UV 查詢時，自動把區級地名升成上層縣市去查。
- forecast sensors 仍維持原本區級來源，不會因為修 UV 而失去區級預報粒度。
- 已做現場驗證：UV index 恢復，forecast sensors 也維持正常。

### v1.3.11 - v1.3.12
- 修正預報感測器在 forecast model 重構後大量變成 `unknown` 的問題。
- forecast sensor 取值邏輯同時相容 native 欄位名與序列化後欄位名。
- 移除 hourly 模式下不合理的 `templow` 處理。

### v1.3.6
- 修正「更新天氣」按鈕不再依賴 coordinator 中不存在的欄位。
- 按鈕會自行在實體屬性中記錄：
  - `update_status`
  - `last_update_time`
  - `previous_update_time`
  - `last_error`（只有失敗時出現）
- 按鈕會與 weather / sensor 實體掛在同一個 HA 裝置下。
- 已做現場閉環驗證：按鈕可正常觸發更新且不再報錯。

### v1.3.1 - v1.3.5
- 改善 Home Assistant Weather Entity 規格相容性。
- 預報改回傳正確的 `Forecast` 物件。
- 補上 UV index、precipitation 等 native weather 屬性。
- 新增可手動立即更新氣象資料的按鈕實體。
- 修正舊版 Home Assistant 的 import 相容性問題。

## 選用：CWA 官方警報與災害資訊

OpenCWA 可以選擇性建立 CWA 官方警報與災害資訊實體。為了避免既有使用者升級後多出額外 API 呼叫，這些功能預設為關閉。

可從 **設定 > 裝置與服務 > OpenCWA > 設定** 啟用：

- **啟用官方颱風警報** (`enable_typhoon_warning`)：使用 CWA `W-C0034-001` CAP 資料判斷目前是否有官方颱風警報。熱帶氣旋路徑資料本身不會被當成官方警報。
- **啟用熱帶氣旋路徑** (`enable_tropical_cyclone_track`)：使用 CWA `W-C0034-005` 顯示目前活動中熱帶氣旋與路徑/定位資訊。
- **啟用重大氣象警特報** (`enable_weather_alerts`)：使用 CWA 災害性天氣警特報資料，並以設定地點及可推得的上層縣市進行影響區域比對。

以 `安平區` 為例，會建立以下 entities：

| Entity | 說明 |
| --- | --- |
| `binary_sensor.opencwa_an_ping_qu_typhoon_warning` | 只有目前真的有官方颱風警報時才會是 `on`。`Cancel`、`END`、已過期 CAP、解除警報訊息都會是 `off`。 |
| `sensor.opencwa_an_ping_qu_typhoon_warning_status` | 颱風警報狀態與 CAP 屬性，例如 headline、報數、警報類別、影響區域、生效/解除時間、颱風位置。 |
| `sensor.opencwa_an_ping_qu_tropical_cyclone` | 目前活動中熱帶氣旋數量；屬性包含最新定位、分析路徑、預測路徑、風速、氣壓、暴風半徑等。 |
| `binary_sensor.opencwa_an_ping_qu_weather_alert` | 重大氣象警特報是否命中目前設定地點。 |
| `sensor.opencwa_an_ping_qu_weather_alerts` | 重大氣象警特報數量與詳細資料。屬性包含 `matched_locations`、`unmatched_special_areas`、`match_method`。 |

特殊區域比對目前涵蓋 CWA 常見區域名稱，例如 `恆春半島`、`蘭嶼綠島`、`基隆北海岸`，以及 `高雄山區` 這類縣市山區名稱。若遇到 `山區`、`沿海空曠地區` 這種無法安全判定所屬地點的泛用名稱，會放在 `unmatched_special_areas` 供使用者判讀。

Automation 範例：

```yaml
alias: CWA 颱風警報通知
trigger:
  - platform: state
    entity_id: binary_sensor.opencwa_an_ping_qu_typhoon_warning
    to: "on"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: CWA 颱風警報
      message: >-
        {{ state_attr('binary_sensor.opencwa_an_ping_qu_typhoon_warning', 'headline') }}
```

# 設置

**在 Opendata CWA 申請 API 授權碼**
1. 打開 [Opendata CWA](https://opendata.cwa.gov.tw/devManual/insrtuction) 的網站
2. 註冊/登入您的帳號
3. 取得您個人的 API 授權碼

# 設定

**請使用 Home Assistant 整合設定**


1. 從 GUI. 設定 > 整合 > 新增 整合 > OpneCWA
   1. 如果 OpenCWA 沒有出現在清單裡，請 重新整理 (REFRESH) 網頁。
   2. 如果 OpenCWA 還是沒有出現在清單裡，請清除瀏覽器的快取 (Cache)。
2. 輸入 API 授權碼.
3. 輸入台灣的鄉鎮市區名稱。請參考 [文件](https://opendata.cwa.gov.tw/opendatadoc/Opendata_City.pdf)。
   1. 一般可直接填區級 / 鄉鎮市名稱，例如：`新店區`、`板橋區`、`三民區`。
   2. 如果名稱可能重複，則需要包含城市名，例如：`嘉義市東區`、`臺中市東區`。
   3. 常見需要補城市名的名稱包括：`北區`、`西區`、`東區`、`中區`、`南區`、`信義區`、`中正區`、`中山區`、`大安區`。
   4. 在 `onecall_*` 模式下，Home Assistant 內仍可維持你原本輸入的區級 / 鄉鎮市名稱；整合只會在 current / UV 查詢時，內部自動升級成上層縣市去命中 CWA onecall 資料集。
   5. 預報資料仍維持原本區級 / 鄉鎮市來源，不會因為 onecall current / UV 的查詢需求而失去在地化 forecast 粒度。

## 注意事項

如果是鄉鎮區，`onecall_daily`（一週預報）仍可能受資料集限制；若該地點無法直接命中 onecall 位置，整合會自動在 current / UV 查詢時改用上層縣市，但 forecast 仍維持原本地點來源。若你只需要最穩定的區級預報，也可以直接使用 `daily` 模式。

打賞

|  LINE Pay | LINE Bank | JKao Pay |
| :------------: | :------------: | :------------: |
| <img src="https://github.com/tsunglung/OpenCWB/blob/master/linepay.jpg" alt="Line Pay" height="200" width="200">  | <img src="https://github.com/tsunglung/OpenCWB/blob/master/linebank.jpg" alt="Line Bank" height="200" width="200">  | <img src="https://github.com/tsunglung/OpenCWB/blob/master/jkopay.jpg" alt="JKo Pay" height="200" width="200">  |