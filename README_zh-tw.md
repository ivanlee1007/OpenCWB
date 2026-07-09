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

### 新增 attributes 詳細說明

以下 attributes 會出現在對應的 warning / typhoon / alert entities 中。所有時間字串皆盡量保留 CWA 原始 ISO 8601 時間格式，方便在 Home Assistant template、automation 或 dashboard card 中直接使用。

#### 通用 attribute

| Attribute | 出現位置 | 意義 | 用途 |
| --- | --- | --- | --- |
| `attribution` | 所有新增 warning entities | 資料來源標示，固定表示資料由 Opendata CWA 提供。 | 顯示資料來源、符合 Home Assistant entity attribution 慣例。 |
| `error` | optional feed 抓取失敗時 | 若某一個選用資料集暫時抓取失敗，會記錄錯誤訊息；正常情況通常不存在或為 `null`。 | 方便排查 CWA API、網路或資料格式問題；也可在 dashboard 上提醒該 feed 暫時不可用。 |

#### 官方颱風警報 attributes

出現於：

- `binary_sensor.*_typhoon_warning`
- `sensor.*_typhoon_warning_status`

| Attribute | 型別 / 範例 | 意義 | 用途 |
| --- | --- | --- | --- |
| `active` | boolean，例如 `true` / `false` | 整合判斷後的「目前是否有有效官方颱風警報」。會排除 `Cancel`、`END`、已過期、headline 含「解除」或「取消」的 CAP。 | 最適合給 automation 判斷是否要通知；binary sensor 的 `on/off` 也是根據此欄位。 |
| `identifier` | string | CWA CAP 訊息識別碼。 | 追蹤此次警報訊息是否更新；進階 automation 可用來避免同一報重複通知。 |
| `sender` | string，例如 `weather@cwa.gov.tw` | CAP 訊息發送者。 | 確認訊息來源。 |
| `sent` | datetime string | CWA 發送此 CAP 訊息的時間。 | 顯示警報發布時間，或用於判斷訊息新舊。 |
| `status` | string，例如 `Actual` | CAP 狀態。`Actual` 代表正式實際警報。 | 排除測試或非正式訊息；整合只把 `Actual` 視為可能有效。 |
| `msg_type` | string，例如 `Update`、`Cancel` | CAP 訊息類型。`Cancel` 代表取消 / 解除。 | automation 可用來分辨新警報、更新或解除警報；`Cancel` 不會讓 binary sensor 變成 `on`。 |
| `scope` | string，例如 `Public` | CAP 適用範圍。 | 顯示訊息公開程度；通常為公開警報。 |
| `event` | string，例如 `颱風` | CAP 事件類型。 | 確認此 CAP 對應颱風事件。 |
| `effective` | datetime string | 警報開始生效時間。 | dashboard 顯示警報有效起始時間；automation 可用於延遲或時間窗判斷。 |
| `onset` | datetime string | 事件預期開始影響時間。 | 若 CWA 有提供，可用來判斷警報影響開始時間。 |
| `expires` | datetime string | 警報到期時間。 | 整合會用它判斷過期警報；也可在 UI 顯示警報預計有效到何時。 |
| `headline` | string，例如 `海上陸上颱風警報`、`解除颱風警報` | CWA 警報標題。 | 通知訊息最常用欄位，例如手機推播標題或卡片主文字。 |
| `web` | URL string | CWA 官方警報網頁連結。 | dashboard 可做成可點擊連結，讓使用者開啟 CWA 官方頁面。 |
| `report_no` | string，例如 `18` | CWA 颱風警報報數。 | 顯示「第幾報」，也可用於判斷同一颱風警報是否有新報。 |
| `warning_type` | string，例如 `海上`、`陸上`、`海上陸上`、`END` | CWA 警報類別。`END` 代表解除。 | 區分海上警報、陸上警報、海陸警報；`END` 不會讓 binary sensor 變成 `on`。 |
| `affected_areas` | list，例如 `["臺北市", "新北市"]` | CWA CAP 中列出的警戒 / 影響區域。 | 顯示警戒區；automation 可判斷特定縣市是否在警戒範圍內。 |
| `typhoon` | object | 颱風本身的結構化資訊，內含下列子欄位。 | dashboard 或通知可顯示颱風名稱與位置。 |
| `typhoon.name` | string，例如 `BAVI` | 國際颱風英文名稱。 | 顯示颱風英文名稱。 |
| `typhoon.cwa_name` | string，例如 `巴威` | CWA 使用的中文颱風名稱。 | 顯示給中文使用者，通常比英文名稱更直覺。 |
| `typhoon.analysis_time` | datetime string | CWA 分析定位時間。 | 判斷目前颱風位置資料的時間點。 |
| `typhoon.analysis_position` | list，例如 `[22.0, 120.8]` | CWA 分析位置，格式為 `[緯度, 經度]`。 | 可用於地圖卡、template 或外部視覺化。 |
| `typhoon.prediction_time` | datetime string | CWA 預測位置時間。 | 顯示預測點對應時間。 |
| `typhoon.prediction_position` | list，例如 `[24.4, 123.1]` | CWA 預測位置，格式為 `[緯度, 經度]`。 | 可用於簡易路徑顯示或通知使用者颱風預測方向。 |

#### 熱帶氣旋路徑 attributes

出現於：

- `sensor.*_tropical_cyclone`

| Attribute | 型別 / 範例 | 意義 | 用途 |
| --- | --- | --- | --- |
| `count` | integer | 目前 CWA 路徑資料中熱帶氣旋數量。 | sensor state 也會使用此數量；可用來快速判斷西北太平洋是否有活動中熱帶氣旋。 |
| `cyclones` | list | 每一個熱帶氣旋的結構化資料清單。 | dashboard 可迭代顯示多個熱帶氣旋。 |
| `cyclones[].year` | string | 颱風年度。 | 區分不同年度的熱帶氣旋資料。 |
| `cyclones[].name` | string | 國際英文名稱。 | 顯示英文名稱。 |
| `cyclones[].cwa_name` | string | CWA 中文名稱。 | 顯示中文名稱。 |
| `cyclones[].cwa_td_no` | string | CWA 熱帶性低氣壓編號。 | 若尚未成颱，可用此編號辨識系統。 |
| `cyclones[].cwa_ty_no` | string | CWA 颱風編號。 | 成颱後可用於對照 CWA 官方颱風編號。 |
| `cyclones[].latest_fix` | object 或 `null` | 最新一筆分析定位資料；若 CWA 未提供定位則為 `null`。 | 最常用於 dashboard 顯示目前位置、強度與移動方向。 |
| `cyclones[].analysis_fixes` | list | 歷史 / 分析定位點列表。 | 可用於繪製已走過的路徑。 |
| `cyclones[].forecast_fixes` | list | 預測定位點列表。 | 可用於繪製預測路徑。 |
| `*.fix.datetime` | datetime string | 該定位點時間。 | 搭配地圖或表格顯示定位時間。 |
| `*.fix.longitude` | number | 定位點經度。 | 地圖顯示路徑點。 |
| `*.fix.latitude` | number | 定位點緯度。 | 地圖顯示路徑點。 |
| `*.fix.max_wind_speed` | number | 中心附近最大風速，依 CWA 原始資料單位。 | 顯示強度變化；可用於通知強度增強。 |
| `*.fix.max_gust_speed` | number | 最大陣風，依 CWA 原始資料單位。 | 顯示陣風強度。 |
| `*.fix.pressure` | number | 中心氣壓。 | 判斷颱風強度；數值越低通常代表越強。 |
| `*.fix.moving_speed` | number | 移動速度。 | 顯示颱風移動快慢。 |
| `*.fix.moving_direction` | string，例如 `WNW` | 移動方向。 | 通知或卡片顯示颱風往哪個方向移動。 |
| `*.fix.circle_15ms` | number 或 `null` | 七級風暴風半徑。 | 判斷影響範圍；若 CWA 未提供則為 `null`。 |
| `*.fix.circle_25ms` | number 或 `null` | 十級風暴風半徑。 | 判斷較強風圈範圍；若 CWA 未提供則為 `null`。 |

> 注意：熱帶氣旋路徑資料只代表 CWA 有追蹤熱帶氣旋，不等於臺灣已有官方颱風警報。是否有官方警報請以 `binary_sensor.*_typhoon_warning` 為準。

#### 重大氣象警特報 attributes

出現於：

- `binary_sensor.*_weather_alert`
- `sensor.*_weather_alerts`

| Attribute | 型別 / 範例 | 意義 | 用途 |
| --- | --- | --- | --- |
| `count` | integer | CWA 目前回傳的警特報事件數量。 | sensor state 也會使用此數量；可用於顯示目前有幾筆警特報。 |
| `active_for_location` | boolean | 是否有任一警特報命中目前設定地點或推得的上層縣市 / 特殊區域。 | binary sensor 的 `on/off` 依據；automation 建議使用此欄位或 binary sensor。 |
| `matched_locations` | list | 已命中的 CWA 影響區域名稱。 | 告訴使用者「為什麼這個地點被判定有警特報」；也可放進通知內容。 |
| `unmatched_special_areas` | list | CWA 有提供特殊區域，但整合無法安全判定是否屬於目前設定地點的區域。 | 避免誤報，同時保留線索供使用者判讀，例如 `山區`、`沿海空曠地區`。 |
| `match_method` | string 或 `null` | 比對方式：`direct` 代表直接地名 / 縣市命中；`special_area` 代表特殊區域 mapping 命中；`all` 代表未指定 location 時視為全部命中；`null` 代表沒有命中。 | debug location matching，或在 dashboard 上顯示命中依據。 |
| `alerts` | list | 每一筆警特報的結構化資料清單。 | dashboard 可展開顯示警特報種類、影響區域與有效時間。 |
| `alerts[].phenomena` | string，例如 `陸上強風`、`大雨` | 警特報現象。 | 通知標題或卡片分類使用。 |
| `alerts[].significance` | string，例如 `特報`、`警報` | 警特報等級 / 類型。 | 區分資訊、特報、警報等重要程度。 |
| `alerts[].affected_areas` | list | 此警特報的 CWA 原始影響區域。 | 顯示官方列出的所有影響區域。 |
| `alerts[].matched_locations` | list | 此單一警特報命中的區域。 | 當有多筆 alerts 時，可知道是哪一筆、哪個區域命中目前地點。 |
| `alerts[].unmatched_special_areas` | list | 此單一警特報中無法安全 mapping 的特殊區域。 | 顯示「可能相關但不自動判定命中」的特殊區域。 |
| `alerts[].match_method` | string 或 `null` | 此單一警特報的命中方式。 | 細分每一筆 alert 的命中原因。 |
| `alerts[].content_text` | string | CWA 警特報內文。 | 推播通知或 dashboard 詳細內容。 |
| `alerts[].issue_time` | datetime string | CWA 發布時間。 | 顯示警特報發布時間。 |
| `alerts[].start_time` | datetime string | 警特報有效開始時間。 | 判斷何時開始影響。 |
| `alerts[].end_time` | datetime string | 警特報有效結束時間。 | 判斷是否過期；整合也會用此欄位排除已過期資料。 |

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