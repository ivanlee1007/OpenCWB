# Optional KCG Agricultural Advisory Extension Implementation Plan

> **For Hermes:** Implement task-by-task with strict RED→GREEN→REFACTOR cycles.

**Goal:** Extend OpenCWA with optional nationwide agricultural advisories and irrigation-reference data from 高雄農來訊 without making existing weather, forecast, warning, or typhoon behavior depend on that provider.

**Architecture:** Add a provider-specific client/parser and a separate `AgricultureUpdateCoordinator`. The coordinator exists only when `enable_agriculture_advisories` is true, treats every provider failure as non-fatal, keeps source attribution separate, and exposes concise per-location/per-crop entities rather than raw nationwide payloads. CWA remains the authoritative weather source; agricultural threshold evaluations are explicitly marked as platform-issued or OpenCWA-derived guidance.

**Tech Stack:** Python, Home Assistant config entries/options, `requests`, `DataUpdateCoordinator`, pytest-style unit tests.

---

### Task 1: Define optional configuration and data contracts

**Files:**
- Modify: `custom_components/opencwb/const.py`
- Test: `tests/test_kcg_agriculture.py`

1. Write a failing test for disabled-by-default configuration and stable agriculture data keys.
2. Run the focused test and confirm failure due to missing constants.
3. Add minimal constants for enable flag, optional token, crop name, growth stage, coordinator key, source attribution, warning/advisory/support/notification/ET0 keys.
4. Run focused and full tests.

### Task 2: Build defensive client and parser

**Files:**
- Create: `custom_components/opencwb/core/agriculture/__init__.py`
- Create: `custom_components/opencwb/core/agriculture/kcg_client.py`
- Create: `custom_components/opencwb/core/agriculture/kcg_parser.py`
- Test: `tests/test_kcg_agriculture.py`

1. Write failing tests for HTTP-200/business-error handling, `text/plain` JSON, Note severity classification, stale timestamps, exact crop matching, and local town filtering.
2. Verify each RED failure.
3. Implement minimal parser/client behavior with token redaction and no full request URL in errors.
4. Verify GREEN and refactor common normalization.

### Task 3: Add non-fatal agriculture coordinator

**Files:**
- Create: `custom_components/opencwb/agriculture_update_coordinator.py`
- Modify: `custom_components/opencwb/__init__.py`
- Test: `tests/test_kcg_agriculture.py`

1. Write a failing test proving disabled agriculture creates no coordinator and existing OpenCWA setup remains independent.
2. Write a failing test proving enabled-provider exceptions return unavailable/stale agriculture data rather than raising `UpdateFailed` for weather.
3. Implement a separate optional coordinator with city resolution, per-entry crop/town filtering, source timestamp/data-age diagnostics, and last-success metadata.
4. Run focused and full tests.

### Task 4: Add Home Assistant options

**Files:**
- Modify: `custom_components/opencwb/config_flow.py`
- Modify: `custom_components/opencwb/strings.json`
- Modify: `custom_components/opencwb/translations/zh-Hant.json`
- Modify: `custom_components/opencwb/translations/en.json`
- Test: `tests/test_kcg_agriculture.py`

1. Write failing schema tests for an off-by-default enable switch and optional token/crop/growth-stage fields.
2. Implement options without validating or contacting 高雄農來訊 when disabled.
3. When enabled, accept token as optional for public advisory endpoints; token-gated irrigation data remains unavailable unless a token is supplied.
4. Verify all visible strings in both languages.

### Task 5: Expose concise agriculture entities

**Files:**
- Modify: `custom_components/opencwb/sensor.py`
- Modify: `custom_components/opencwb/binary_sensor.py`
- Modify: `custom_components/opencwb/__init__.py`
- Test: `tests/test_kcg_agriculture.py`

1. Write failing tests for crop warning, crop advisory, crop-data-supported, notification, counts, and diagnostics.
2. Implement entities only when agriculture is enabled.
3. Keep raw nationwide rows out of entity attributes; expose matched records, source/provider attribution, source timestamp, stale/error state, and stable notification fields.
4. Remove stale registry entities when the option is disabled.

### Task 6: Add optional irrigation-reference data

**Files:**
- Modify: `custom_components/opencwb/core/agriculture/kcg_client.py`
- Modify: `custom_components/opencwb/core/agriculture/kcg_parser.py`
- Modify: `custom_components/opencwb/agriculture_update_coordinator.py`
- Modify: `custom_components/opencwb/sensor.py`
- Test: `tests/test_kcg_agriculture.py`

1. Write failing tests for ET0/Kc/ETc business success/error responses and unsupported crops.
2. Implement token-gated calls only when a token and crop are configured.
3. Expose ET0, Kc, ETc, water requirement and support status; never translate missing data into numeric zero.
4. Mark values as references/advisories and never actuate irrigation directly.

### Task 7: Documentation and versioning

**Files:**
- Modify: `README.md`
- Modify: `README_zh-tw.md`
- Modify: `custom_components/opencwb/manifest.json`
- Modify: `custom_components/opencwb/core/__version__.py`

Document opt-in behavior, provider/source attribution, supported/unsupported crop semantics, Note classification, stale handling, entity examples, notification automation, API/token limitations, and that OpenCWA remains fully functional when disabled or unavailable.

### Task 8: Verification and delivery

1. Run focused tests and the entire suite.
2. Run Python compilation/static checks and JSON validation.
3. Run live no-token smoke tests for `List_Warning`, `CropVType`, and one configured-city `cropweatherTaiwan` request without persisting payloads or secrets.
4. Verify disabled-path behavior locally.
5. Review diff for token leakage, raw nationwide attributes, provider coupling, and UI string completeness.
6. Commit, push, inspect GitHub CI, and fix verified failures before reporting completion.
