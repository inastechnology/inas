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
    "enabled": true,
    "moisture_guard": {"enabled": false, "threshold_percent": 40, "source": "first"},
    "timed_outputs": {
      "enabled": false,
      "water_inlet": {"on_sec": 0, "off_sec": 0, "repeat_count": 0},
      "nutrient_a": {"on_sec": 0, "off_sec": 0, "repeat_count": 0},
      "nutrient_b": {"on_sec": 0, "off_sec": 0, "repeat_count": 0},
      "mixer": {"on_sec": 0, "off_sec": 0, "repeat_count": 0},
      "irrigation": {"on_sec": 0, "off_sec": 0, "repeat_count": 0}
    },
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
      "soil": {"enabled": true, "modbus_slave_id": 1, "modbus_function": 3, "start_register": 0},
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
instead. Firmware consumes up to four valid daily entries. Hubの実効Runtime Configは
`fgt.enabled=true`を固定し、個々の予約と出力時間で実行内容を決める。

When `fgt.timed_outputs.enabled=true`, the timed sequence replaces the nutrient
recipe for every enabled FGT schedule. Each fixed output accepts `on_sec` and
`off_sec` from 0 to 1800 and `repeat_count` from 0 to 99. A zero repeat count
disables the output and its saved ON/OFF values are ignored; repeat counts from
1 to 99 require a positive ON time. Enabled outputs run sequentially in terminal
order. The planned sum of ON and intervening OFF intervals must not exceed
`fgt.limits.max_batch_sec`.
The top-level `fgt.enabled` is fixed to `true` by the Hub and is not a user-facing
operation switch.

FGT v1 accepts only `frequency.mode="daily"`. Interval and weekday entries are
ignored rather than accidentally being executed every day.

## Existing Hub database compatibility

### Soil moisture schedule guard (firmware 0.4.0+)

`fgt.moisture_guard` is optional. `enabled` is a boolean (default `false`),
`threshold_percent` an integer in 0..100 (default `40`), and `source` one of:

- `first` (default): first enabled soil sensor in local registration order;
- `sensor:<baud>:<slave_id>`: one specific soil sensor, identified by its bus
  speed (2400, 4800, or 9600) and address (1..247), independent of list position;
- `average`: arithmetic mean of every enabled local soil sensor. Disabled soil
  sensors and non-soil sensors are excluded. With only one enabled soil sensor,
  the mean is that sensor's value.

Without a saved local registry, the runtime soil sensor is the single available
source. A removed, disabled, or unreadable selected sensor is unavailable; no
other sensor is substituted. If any member of an average is unreadable, the
whole mean is unavailable rather than averaging a subset.

Before either a timed sequence or recipe starts, fresh moisture **greater than
or equal to** the threshold skips the entire scheduled operation: filling,
dosing, mixing, irrigation, and rinsing. This also applies to catch-up schedules.
A wet-soil skip is consumed in the journal and cannot be replayed after restart.
The guard does not stop a batch already in progress or infer rainfall.

**Unavailable feedback allows scheduled irrigation.** This includes no enabled
source, read errors, a partial/missing average, non-finite values, and readings
outside 0..100. Existing actuator, emergency, journal, and batch interlocks still
apply. Invalid configuration is rejected rather than interpreted as missing
feedback. This missing-feedback behavior replaces the 0.3.0 behavior, which
skipped when moisture was unavailable.

Status includes `moisture_guard_source_supported=true`, the applied
`moisture_guard_source`, `moisture_guard_missing_allows_watering=true`,
`moisture_guard_enabled`, `moisture_guard_threshold_percent`,
`moisture_guard_checked`, `moisture_guard_sensor_count` (selected enabled members),
`moisture_guard_sample_ok`, and `moisture_guard_sample_percent` (null on failure).
`moisture_guard_result` is `not_checked`, `skip_wet`, `allow_below`,
`allow_unavailable`, or `skip_invalid_config` (invalid settings). This result is
preserved even if a subsequent journal write fails. The decision sample is separate from later sensor telemetry;
allowing the moisture check alone does not imply that actuator operation succeeded.
Wet-soil skips retain `batch_skip_reason=soil_moisture_high`.

Runtime store version 4 preserves valid version 2 and 3 configurations. V2 loads
with the guard off; V3 retains enabled/threshold settings with `source=first`.
Corrupt records still load actuator-safe defaults. Firmware 0.4.0 implements the
new missing-feedback policy immediately, including for migrated configurations.
Downgrading requires retrieving configuration from the Hub again.

The Hub refuses to send an enabled guard until the device has reported source
support, preventing older firmware from silently interpreting a selected sensor
or mean as `first`. Saved settings may be prepared in advance; update firmware
and wait for its first status before sending them.

### Legacy Hub rows

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
- batch: `batch_due`, `batch_started`, `batch_completed`, `batch_id`,
  `batch_catch_up`, and `batch_delay_sec`;
- state machine: `fgt_phase`, `fgt_fault`, `fgt_phase_elapsed_ms`;
- operation: `fgt_operation_mode`, `fgt_timed_output`, and
  `fgt_timed_repeat_number`;
- water plan: `inlet_water_ml`, `nutrient_batch_water_target_ml`,
  `rinse_water_target_ml`, and `planned_irrigation_water_ml`;
- volume: `inlet_water_ml`, `target_water_ml`;
- physical safety: `tank_empty`, `tank_full`, `leak_detected`,
  `emergency_stop`, `io_ok`;
- commanded outputs: `water_inlet_on`, `nutrient_a_on`, `nutrient_b_on`,
  `mixer_on`, `irrigation_on`;
- current FGT RS485 measurements: soil moisture, temperature, EC, and PAR;
- `soil_sensor_profile="moisture_temperature_ec"` identifies the current
  three-register soil profile.

FGT 0.2.1以降は土壌センサーから先頭3レジスタだけを読み、`soil_ph`、
`soil_n_mg_kg`、`soil_p_mg_kg`、`soil_k_mg_kg`を送信しない。0.2.0以前が送った
これらの項目は現行FGTハードウェアで未対応のため、Hubは計測値として採用しない。

Hub UI wording must use the farmer-facing phase labels rather than these raw
field names. Raw fields belong in advanced diagnostics.

FGT 0.2.3以降は、通常の15分以内の実行猶予を過ぎても、予約時刻から6時間以内で
あれば、正常に読める保存履歴がある場合に限って最新の未実行予約を1回だけ追いつき実行する。6時間を超えた予約は安全のため
`schedule_too_old`として実行済みにし、複数回まとめて再生しない。OTA確認と予約が
重なった場合は予約を完了扱いにせず、通常の最短sleepで再確認する。安全入力異常、
出力異常、実行途中の再起動は従来どおり自動再開せず、明示的な復旧確認を必要とする。
初回起動や履歴を消去した機器は古い予約を追いつき実行しない。
