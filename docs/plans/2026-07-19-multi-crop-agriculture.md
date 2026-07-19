# OpenCWA 1.5.0 Multi-Crop Agriculture Plan

## Product model

- One OpenCWA config entry represents one farm/location and shared CWA/provider configuration.
- Each crop is a Home Assistant native `crop` config subentry.
- Users can repeatedly add crops and natively reconfigure or remove each crop.
- Each crop subentry stores:
  - `crop_name` (canonical provider value or custom fallback)
  - `growth_stage`
  - `planting_date`
  - `area_hectares`
- Home Assistant's persistent `subentry_id` is the stable crop identity. Entity unique IDs must never depend on list order or editable crop names.

## Runtime

- Agriculture remains optional and default-off.
- Disabled mode does not import/construct the optional provider and creates no agriculture entities.
- One farm-level agriculture coordinator fetches city rows, crop catalog, and warning rules once per interval.
- The coordinator builds an independent snapshot for each crop subentry.
- Token-gated irrigation calls remain per crop because planting date and area differ.
- Provider failure never affects CWA coordinators. Each crop preserves its own successful cache as stale when possible.
- Crop entities are associated with `config_subentry_id` so native subentry deletion cleans up only that crop.

## Entity model

Each crop creates its own agriculture device and:

- Agricultural advisory status sensor
- Agricultural advisory notification sensor
- ET0 sensor
- Kc sensor
- ETc sensor
- Water requirement sensor
- Crop warning binary sensor
- Crop advisory binary sensor
- Crop data supported binary sensor

Unique ID shape:

```text
<entry-unique-id>-agriculture-<subentry-id>-<entity-kind>
```

## Migration

- Config flow version increases from 1 to 2.
- If an existing entry has legacy non-empty `crop_name` and no crop subentry, migration creates exactly one crop subentry.
- The crop subentry title is the crop name; its unique ID uses a generated stable UUID so duplicate crop names remain possible for separate fields/planting batches.
- Legacy crop fields are removed from parent data/options only after the subentry is created.
- Provider enable and token remain parent-level shared settings.
- Migration is idempotent.

## Config UX

- Parent Options Flow manages only global warning/provider settings and provider token.
- Integration page exposes native `Add crop` action.
- Crop subentry add/reconfigure uses the searchable 127-option selector with canonical values, aliases, and custom value fallback.
- Crop deletion uses Home Assistant's native subentry removal confirmation.

## Verification

1. RED tests for subentry registration, add, reconfigure, validation, migration, and stable IDs.
2. Shared-fetch coordinator tests for two crops and independent snapshots/stale caches.
3. Entity tests for per-crop names, unique IDs, config subentry association, and deletion isolation.
4. Full pytest, flake8, compile, JSON, diff and secret checks.
5. Independent fail-closed review.
6. Per-file deployment with SHA read-back to HA 2026.7.2.
7. Live UI add two crops, reconfigure one, remove one, restart, and verify CWA entity stability.
8. CI, tag and GitHub Release only after all gates pass.
