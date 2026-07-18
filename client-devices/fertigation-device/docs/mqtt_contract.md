# Runtime Configuration And Status Contract

## Runtime configuration

FGT consumes common network/time fields plus an `fgt` object. Values shown are
the v1 defaults and remain bounded by firmware limits.

```json
{
  "ntp_server": "pool.ntp.org",
  "timezone_offset_sec": 32400,
  "sleep_sec": 300,
  "ota_check_interval_sec": 21600,
  "debug_log_on_wake": false,
  "fgt": {
    "enabled": false,
    "recipe": {
      "total_water_ml": 4500,
      "initial_water_ml": 1250,
      "nutrient_a_ml": 10,
      "nutrient_b_ml": 10,
      "nutrient_a_rate_ml_min": 100,
      "nutrient_b_rate_ml_min": 100,
      "pre_mix_sec": 10,
      "mix_after_a_sec": 30,
      "mix_after_b_sec": 60,
      "final_mix_sec": 120,
      "irrigation_max_sec": 900,
      "rinse_water_ml": 500,
      "rinse_mix_sec": 30,
      "rinse_drain_max_sec": 180
    },
    "limits": {
      "max_total_water_ml": 10000,
      "max_nutrient_ml": 100,
      "water_no_flow_timeout_sec": 15,
      "max_fill_sec": 300,
      "max_batch_sec": 1800,
      "volume_tolerance_ml": 100
    },
    "sensors": {
      "soil": {"enabled": true, "modbus_slave_id": 2, "modbus_function": 4, "start_register": 0},
      "par": {"enabled": true, "modbus_slave_id": 1, "modbus_function": 3, "register": 0, "scale": 1.0},
      "power_settle_ms": 800,
      "flow_pulses_per_liter": 450
    }
  },
  "schedules": [
    {"hour": 6, "minute": 30, "duration_sec": 900, "channel_mask": 1, "enabled": true},
    {"hour": 16, "minute": 30, "duration_sec": 900, "channel_mask": 1, "enabled": false}
  ]
}
```

`duration_sec` and `channel_mask` remain in the shared Hub schedule schema for
backward compatibility; FGT uses its recipe timeout and fixed irrigation output
instead. Firmware consumes up to four valid daily entries. A fresh device
defaults to `fgt.enabled=false`, so a generic legacy config cannot start nutrient
dosing.

FGT v1 accepts only `frequency.mode="daily"`. Interval and weekday entries are
ignored rather than accidentally being executed every day.

## Existing Hub database compatibility

`fgt` is an optional overlay in the Hub device-config validator. Existing
WTR/WRS/ENV/SOI records without that key are loaded and republished without an
FGT overlay, so no database migration or destructive rewrite is required. The
shared validator adds backward-compatible defaults for `sleep_sec` and schedule
`enabled` when older records omit them. Firmware also defaults FGT execution to
disabled, which prevents an old generic schedule from starting nutrient dosing.

`total_water_ml` is the clean water used to prepare the nutrient batch, not the
whole irrigation event. The planned water delivered to plants is
`total_water_ml + rinse_water_ml`; the v1 defaults therefore deliver 4.5 L of
batch water plus 0.5 L of rinse water, approximately 5.0 L in total. A/B stock
solution volume is recorded separately and is not used to hide irrigation
volume.

## Status fields

The normal status payload includes:

- identity: `device_kind`, firmware version/build, sequence identifier;
- lifecycle: network/config/time/OTA state and next sleep;
- batch: `batch_due`, `batch_started`, `batch_completed`, `batch_id`;
- state machine: `fgt_phase`, `fgt_fault`, `fgt_phase_elapsed_ms`;
- water plan: `inlet_water_ml`, `nutrient_batch_water_target_ml`,
  `rinse_water_target_ml`, and `planned_irrigation_water_ml`;
- volume: `inlet_water_ml`, `target_water_ml`;
- physical safety: `tank_empty`, `tank_full`, `leak_detected`,
  `emergency_stop`, `io_ok`;
- commanded outputs: `water_inlet_on`, `nutrient_a_on`, `nutrient_b_on`,
  `mixer_on`, `irrigation_on`;
- shared RS485 measurement names used by WRS: soil moisture, temperature, EC,
  pH, N/P/K, and PAR.

Hub UI wording must use the farmer-facing phase labels rather than these raw
field names. Raw fields belong in advanced diagnostics.
