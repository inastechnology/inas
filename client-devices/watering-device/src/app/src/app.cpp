#include "app.h"

#include <Arduino.h>
#include <string.h>
#include <time.h>

#include "app_debug_log.h"
#include "app_def.h"
#include "app_device.h"
#include "app_network.h"
#include "app_runtime_config.h"
#include "app_watering.h"
#include "hal_power_switch.h"
#include "hal_rs485_modbus.h"

#define APP_WATERING_DUE_GRACE_SEC (15 * 60)

RTC_DATA_ATTR static time_t s_last_executed_schedule_utc = 0;

static int32_t app_pack_runtime_flags(uint8_t threshold, bool force_watering, bool debug_log_on_wake, uint8_t schedule_count)
{
    return static_cast<int32_t>(threshold) |
           (force_watering ? (1L << 8) : 0) |
           (debug_log_on_wake ? (1L << 9) : 0) |
           (static_cast<int32_t>(schedule_count) << 16);
}

struct Rs485SensorSample
{
    bool sensor_power_requested = false;
    bool sensor_power_configured = false;
    bool sensor_power_error = false;

    bool par_ok = false;
    uint16_t raw_par = 0;
    float base_par_umol_m2_s = 0.0f;
    float par_umol_m2_s = 0.0f;

    bool soil_rs485_ok = false;
    uint16_t raw_soil_moisture = 0;
    uint16_t raw_soil_temperature = 0;
    uint16_t raw_soil_ec = 0;
    uint16_t raw_soil_ph = 0;
    uint16_t raw_soil_nitrogen = 0;
    uint16_t raw_soil_phosphorus = 0;
    uint16_t raw_soil_potassium = 0;
    float base_soil_moisture_percent = 0.0f;
    float base_soil_temperature_c = 0.0f;
    float base_soil_ec_us_cm = 0.0f;
    float base_soil_ph = 0.0f;
    float base_soil_n_mg_kg = 0.0f;
    float base_soil_p_mg_kg = 0.0f;
    float base_soil_k_mg_kg = 0.0f;
    float soil_moisture_percent = 0.0f;
    float soil_temperature_c = 0.0f;
    float soil_ec_us_cm = 0.0f;
    float soil_ph = 0.0f;
    float soil_n_mg_kg = 0.0f;
    float soil_p_mg_kg = 0.0f;
    float soil_k_mg_kg = 0.0f;

    bool calibration_capture_applied = false;
    bool calibration_capture_duplicate = false;
    bool calibration_capture_error = false;
};

struct WateringCycleState
{
    bool watering_due = false;
    bool watering_started = false;
    bool startup_watering_test_requested = false;
    bool startup_watering_test_started = false;
    uint16_t watering_duration_sec = 0;
    uint32_t channel_mask = 0;
    time_t schedule_epoch_utc = 0;
    uint8_t last_soil_moisture = 0;
    bool force_watering = false;
    bool debug_log_on_wake = false;
    bool runtime_config_valid = false;
    uint32_t ota_check_interval_sec = APP_RUNTIME_DEFAULT_OTA_CHECK_INTERVAL_SEC;
    bool watering_pattern_enabled = false;
    uint16_t watering_pattern_on_sec = 0;
    uint16_t watering_pattern_off_sec = 0;
    uint8_t watering_pattern_repeat_count = 0;
    bool soil_calibration_auto_mode = false;
    bool soil_calibration_applied = false;
    bool soil_calibration_suggested = false;
    uint16_t soil_raw_before_watering = 0;
    uint16_t soil_raw_after_watering = 0;
    uint16_t soil_calibration_dry_raw = 0;
    uint16_t soil_calibration_wet_raw = 0;
    uint16_t soil_calibration_suggested_dry_raw = 0;
    uint16_t soil_calibration_suggested_wet_raw = 0;
    Rs485SensorSample rs485 = {};
};

static void app_cycle_idle_loop()
{
    app_network_loop();
}

static float app_scaled_tenths(uint16_t value)
{
    return static_cast<float>(value) / 10.0f;
}

static float app_scaled_signed_tenths(uint16_t value)
{
    return static_cast<float>(static_cast<int16_t>(value)) / 10.0f;
}

static float app_calibrated_value(float value, const app_env_metric_calibration_t &calibration)
{
    return value * calibration.scale + calibration.offset;
}

static bool app_env_soil_calibration_complete(const app_env_calibration_config_t &calibration)
{
    return calibration.soil_moisture_percent.calibrated &&
           calibration.soil_temperature_c.calibrated &&
           calibration.soil_ec_us_cm.calibrated &&
           calibration.soil_ph.calibrated &&
           calibration.soil_n_mg_kg.calibrated &&
           calibration.soil_p_mg_kg.calibrated &&
           calibration.soil_k_mg_kg.calibrated;
}

static bool app_rs485_base_value_for_metric(const Rs485SensorSample &sample, const char *metric, float &value)
{
    if (strcmp(metric, APP_ENV_METRIC_PAR) == 0)
    {
        value = sample.base_par_umol_m2_s;
        return sample.par_ok;
    }
    if (strcmp(metric, APP_ENV_METRIC_SOIL_MOISTURE) == 0)
    {
        value = sample.base_soil_moisture_percent;
        return sample.soil_rs485_ok;
    }
    if (strcmp(metric, APP_ENV_METRIC_SOIL_TEMPERATURE) == 0)
    {
        value = sample.base_soil_temperature_c;
        return sample.soil_rs485_ok;
    }
    if (strcmp(metric, APP_ENV_METRIC_SOIL_EC) == 0)
    {
        value = sample.base_soil_ec_us_cm;
        return sample.soil_rs485_ok;
    }
    if (strcmp(metric, APP_ENV_METRIC_SOIL_PH) == 0)
    {
        value = sample.base_soil_ph;
        return sample.soil_rs485_ok;
    }
    if (strcmp(metric, APP_ENV_METRIC_SOIL_N) == 0)
    {
        value = sample.base_soil_n_mg_kg;
        return sample.soil_rs485_ok;
    }
    if (strcmp(metric, APP_ENV_METRIC_SOIL_P) == 0)
    {
        value = sample.base_soil_p_mg_kg;
        return sample.soil_rs485_ok;
    }
    if (strcmp(metric, APP_ENV_METRIC_SOIL_K) == 0)
    {
        value = sample.base_soil_k_mg_kg;
        return sample.soil_rs485_ok;
    }
    return false;
}

static void app_apply_rs485_calibrations(Rs485SensorSample &sample, const app_runtime_config_t &config)
{
    sample.par_umol_m2_s = app_calibrated_value(sample.base_par_umol_m2_s, config.env_calibration.par_umol_m2_s);
    sample.soil_moisture_percent = app_calibrated_value(sample.base_soil_moisture_percent, config.env_calibration.soil_moisture_percent);
    sample.soil_temperature_c = app_calibrated_value(sample.base_soil_temperature_c, config.env_calibration.soil_temperature_c);
    sample.soil_ec_us_cm = app_calibrated_value(sample.base_soil_ec_us_cm, config.env_calibration.soil_ec_us_cm);
    sample.soil_ph = app_calibrated_value(sample.base_soil_ph, config.env_calibration.soil_ph);
    sample.soil_n_mg_kg = app_calibrated_value(sample.base_soil_n_mg_kg, config.env_calibration.soil_n_mg_kg);
    sample.soil_p_mg_kg = app_calibrated_value(sample.base_soil_p_mg_kg, config.env_calibration.soil_p_mg_kg);
    sample.soil_k_mg_kg = app_calibrated_value(sample.base_soil_k_mg_kg, config.env_calibration.soil_k_mg_kg);
}

static void app_apply_rs485_calibration_mode(Rs485SensorSample &sample, const app_runtime_config_t &config)
{
    if (strcmp(config.env_calibration.mode, APP_ENV_CALIBRATION_MODE_CAPTURE_REFERENCE) != 0)
    {
        return;
    }

    if (strlen(config.env_calibration.request_id) > 0 &&
        strcmp(config.env_calibration.request_id, config.env_calibration.last_request_id) == 0)
    {
        const app_env_metric_calibration_t &current =
            app_runtime_config_env_metric_calibration(config, config.env_calibration.target);
        sample.calibration_capture_duplicate = true;
        app_runtime_config_update_env_metric_calibration(config.env_calibration.target,
                                                         current.scale,
                                                         current.offset,
                                                         current.calibrated,
                                                         config.env_calibration.request_id);
        return;
    }

    float base_value = 0.0f;
    if (!app_rs485_base_value_for_metric(sample, config.env_calibration.target, base_value))
    {
        sample.calibration_capture_error = true;
        Serial.printf("WTR RS485 calibration target is not available: target=%s\n", config.env_calibration.target);
        return;
    }

    const app_env_metric_calibration_t &current =
        app_runtime_config_env_metric_calibration(config, config.env_calibration.target);
    const float offset = config.env_calibration.reference_value - (base_value * current.scale);
    sample.calibration_capture_applied =
        app_runtime_config_update_env_metric_calibration(config.env_calibration.target,
                                                         current.scale,
                                                         offset,
                                                         true,
                                                         config.env_calibration.request_id);
}

static void app_read_rs485_sensors(const app_runtime_config_t &config, Rs485SensorSample &sample)
{
    if (!config.env_sensors.par.enabled && !config.env_sensors.soil.enabled)
    {
        return;
    }

    sample.sensor_power_requested = true;
    sample.sensor_power_configured = hal_power_switch_is_configured();
    if (!hal_power_switch_enable_and_wait(config.env_sensors.power_settle_ms))
    {
        sample.sensor_power_error = true;
        hal_power_switch_set_enabled(false);
        Serial.println("Failed to enable 12V sensor power switch");
        return;
    }

    if (config.env_sensors.par.enabled)
    {
        uint16_t par_registers[1] = {};
        sample.par_ok = hal_rs485_modbus_read_registers(config.env_sensors.par.modbus_slave_id,
                                                        config.env_sensors.par.modbus_function,
                                                        config.env_sensors.par.register_address,
                                                        1,
                                                        par_registers,
                                                        1);
        if (sample.par_ok)
        {
            sample.raw_par = par_registers[0];
            sample.base_par_umol_m2_s = static_cast<float>(sample.raw_par);
        }
    }

    if (config.env_sensors.soil.enabled)
    {
        uint16_t soil_registers[7] = {};
        sample.soil_rs485_ok = hal_rs485_modbus_read_registers(config.env_sensors.soil.modbus_slave_id,
                                                               config.env_sensors.soil.modbus_function,
                                                               config.env_sensors.soil.start_register,
                                                               7,
                                                               soil_registers,
                                                               7);
        if (sample.soil_rs485_ok)
        {
            sample.raw_soil_moisture = soil_registers[0];
            sample.raw_soil_temperature = soil_registers[1];
            sample.raw_soil_ec = soil_registers[2];
            sample.raw_soil_ph = soil_registers[3];
            sample.raw_soil_nitrogen = soil_registers[4];
            sample.raw_soil_phosphorus = soil_registers[5];
            sample.raw_soil_potassium = soil_registers[6];
            sample.base_soil_moisture_percent = app_scaled_tenths(sample.raw_soil_moisture);
            sample.base_soil_temperature_c = app_scaled_signed_tenths(sample.raw_soil_temperature);
            sample.base_soil_ec_us_cm = static_cast<float>(sample.raw_soil_ec);
            sample.base_soil_ph = app_scaled_tenths(sample.raw_soil_ph);
            sample.base_soil_n_mg_kg = static_cast<float>(sample.raw_soil_nitrogen);
            sample.base_soil_p_mg_kg = static_cast<float>(sample.raw_soil_phosphorus);
            sample.base_soil_k_mg_kg = static_cast<float>(sample.raw_soil_potassium);
        }
    }

    hal_power_switch_set_enabled(false);
    app_apply_rs485_calibration_mode(sample, config);
    app_apply_rs485_calibrations(sample, config);
}

class WateringDevice : public AppDevice
{
public:
    bool apply_runtime_config_json(const uint8_t *payload, size_t length) override
    {
        return app_runtime_config_apply_json(payload, length);
    }

    bool has_valid_runtime_config() const override
    {
        return app_runtime_config_is_valid();
    }

    bool is_runtime_config_received() const override
    {
        return app_runtime_config_is_received();
    }

protected:
    const char *device_name() const override
    {
        return "INA Water Controller";
    }

    bool on_initialize() override
    {
        app_runtime_config_init();
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                            APP_DEBUG_LOG_INFO,
                            APP_DEBUG_EVENT_RUNTIME_CONFIG_INIT,
                            app_runtime_config_is_valid() ? 1 : 0,
                            app_runtime_config_get().debug_log_on_wake ? 1 : 0);

        app_watering_init();
        const hal_power_switch_config_t power_switch_config = hal_power_switch_default_config();
        hal_power_switch_init(&power_switch_config);
        const hal_rs485_modbus_config_t rs485_config = hal_rs485_modbus_default_config();
        const bool rs485_ready = hal_rs485_modbus_init(&rs485_config);
        Serial.printf("WTR RS485 Modbus ready=%s\n", rs485_ready ? "true" : "false");
        return true;
    }

    void prepare_runtime_config_request() override
    {
        app_runtime_config_mark_waiting();
    }

    void on_runtime_config_ready(bool config_received) override
    {
        (void)config_received;
        const app_runtime_config_t &runtime_config = app_runtime_config_get();
        app_watering_set_threshold(runtime_config.moisture_threshold);
        app_watering_set_soil_calibration(runtime_config.soil_calibration.dry_raw,
                                          runtime_config.soil_calibration.wet_raw);
        Serial.printf("Runtime config in app loop: threshold=%u force_watering=%s debug_log_on_wake=%s ota_check_interval_sec=%lu watering_pattern=%s soil_calibration=%u/%u env_par=%s env_soil=%s power_settle_ms=%lu env_calibration_mode=%s target=%s\n",
                      runtime_config.moisture_threshold,
                      runtime_config.force_watering ? "true" : "false",
                      runtime_config.debug_log_on_wake ? "true" : "false",
                      static_cast<unsigned long>(runtime_config.ota_check_interval_sec),
                      runtime_config.watering_pattern.enabled ? "true" : "false",
                      runtime_config.soil_calibration.dry_raw,
                      runtime_config.soil_calibration.wet_raw,
                      runtime_config.env_sensors.par.enabled ? "true" : "false",
                      runtime_config.env_sensors.soil.enabled ? "true" : "false",
                      static_cast<unsigned long>(runtime_config.env_sensors.power_settle_ms),
                      runtime_config.env_calibration.mode,
                      runtime_config.env_calibration.target);
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                            APP_DEBUG_LOG_INFO,
                            APP_DEBUG_EVENT_RUNTIME_CONFIG_ACTIVE,
                            app_pack_runtime_flags(runtime_config.moisture_threshold,
                                                   runtime_config.force_watering,
                                                   runtime_config.debug_log_on_wake,
                                                   runtime_config.schedule_count),
                            0);
    }

    const char *runtime_ntp_server() const override
    {
        return app_runtime_config_get().ntp_server;
    }

    int32_t runtime_timezone_offset_sec() const override
    {
        return app_runtime_config_get().timezone_offset_sec;
    }

    AppDeviceCycleResult run_device_cycle(const AppDeviceWakeContext &context) override
    {
        AppDeviceCycleResult result = {};
        const app_runtime_config_t &runtime_config = app_runtime_config_get();

        m_cycle = {};
        m_cycle.last_soil_moisture = app_watering_read_soil_moisture();
        m_cycle.force_watering = runtime_config.force_watering;
        m_cycle.debug_log_on_wake = runtime_config.debug_log_on_wake;
        m_cycle.runtime_config_valid = app_runtime_config_is_valid();
        m_cycle.ota_check_interval_sec = runtime_config.ota_check_interval_sec;
        app_read_rs485_sensors(runtime_config, m_cycle.rs485);

        const app_startup_watering_test_config_t &startup_test = app_runtime_config_get_startup_watering_test();
        m_cycle.startup_watering_test_requested = !context.woke_from_deep_sleep && context.config_received && startup_test.enabled;
        if (m_cycle.startup_watering_test_requested && !context.ota_update_attempted)
        {
            m_cycle.watering_duration_sec = startup_test.duration_sec;
            m_cycle.channel_mask = startup_test.channel_mask;
            m_cycle.startup_watering_test_started = app_watering_start_async(startup_test.duration_sec,
                                                                              startup_test.channel_mask,
                                                                              true);
            m_cycle.watering_started = m_cycle.startup_watering_test_started;
            Serial.printf("Startup watering test: started=%s mask=0x%lx duration=%u\n",
                          m_cycle.startup_watering_test_started ? "true" : "false",
                          static_cast<unsigned long>(startup_test.channel_mask),
                          startup_test.duration_sec);
            while (app_watering_is_in_progress())
            {
                app_watering_loop();
                app_network_loop();
                delay(50);
            }
        }

        time_t now_utc = time(nullptr);
        app_schedule_entry_t due_schedule = {};
        time_t due_schedule_epoch_utc = 0;
        m_cycle.watering_due = !m_cycle.startup_watering_test_started && context.time_synced &&
                               app_runtime_config_find_due_schedule(now_utc,
                                                                    s_last_executed_schedule_utc,
                                                                    &due_schedule,
                                                                    &due_schedule_epoch_utc);
        if (m_cycle.watering_due && now_utc - due_schedule_epoch_utc > APP_WATERING_DUE_GRACE_SEC)
        {
            Serial.printf("Watering schedule due at %ld is too old; skipped at now=%ld grace=%lu sec\n",
                          static_cast<long>(due_schedule_epoch_utc),
                          static_cast<long>(now_utc),
                          static_cast<unsigned long>(APP_WATERING_DUE_GRACE_SEC));
            s_last_executed_schedule_utc = due_schedule_epoch_utc;
            m_cycle.watering_due = false;
            due_schedule_epoch_utc = 0;
            memset(&due_schedule, 0, sizeof(due_schedule));
        }
        Serial.printf("Schedule check: now=%ld last_executed=%ld due=%s runtime_valid=%s\n",
                      static_cast<long>(now_utc),
                      static_cast<long>(s_last_executed_schedule_utc),
                      m_cycle.watering_due ? "true" : "false",
                      app_runtime_config_is_valid() ? "true" : "false");
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                            m_cycle.watering_due ? APP_DEBUG_LOG_INFO : APP_DEBUG_LOG_WARNING,
                            APP_DEBUG_EVENT_SCHEDULE_CHECK,
                            (m_cycle.watering_due ? 1 : 0) | (app_runtime_config_is_valid() ? (1 << 1) : 0),
                            static_cast<int32_t>(s_last_executed_schedule_utc));

        if (m_cycle.watering_due && context.ota_update_attempted)
        {
            Serial.println("Watering schedule is due but skipped because OTA update was attempted in this wake cycle.");
        }
        else if (m_cycle.watering_due && !m_cycle.startup_watering_test_started)
        {
            m_cycle.watering_duration_sec = due_schedule.duration_sec;
            m_cycle.channel_mask = due_schedule.channel_mask;
            m_cycle.schedule_epoch_utc = due_schedule_epoch_utc;

            Serial.printf("Watering schedule due at %ld, mask=0x%lx, duration=%u\n",
                          static_cast<long>(due_schedule_epoch_utc),
                          static_cast<unsigned long>(due_schedule.channel_mask),
                          due_schedule.duration_sec);
            Serial.printf("Watering threshold before decision: %u%% force_watering=%s\n",
                          app_watering_get_threshold(),
                          runtime_config.force_watering ? "true" : "false");

            m_cycle.watering_pattern_enabled = runtime_config.watering_pattern.enabled;
            m_cycle.watering_pattern_on_sec = runtime_config.watering_pattern.on_sec;
            m_cycle.watering_pattern_off_sec = runtime_config.watering_pattern.off_sec;
            m_cycle.watering_pattern_repeat_count = runtime_config.watering_pattern.repeat_count;
            m_cycle.soil_calibration_auto_mode = runtime_config.soil_calibration.auto_mode_enabled;
            m_cycle.soil_calibration_dry_raw = runtime_config.soil_calibration.dry_raw;
            m_cycle.soil_calibration_wet_raw = runtime_config.soil_calibration.wet_raw;

            const bool should_probe_soil_calibration =
                runtime_config.soil_calibration.auto_mode_enabled ||
                runtime_config.soil_calibration.drift_check_enabled;
            if (should_probe_soil_calibration)
            {
                m_cycle.soil_raw_before_watering = app_watering_read_soil_raw_average(20, 40);
            }

            if (runtime_config.watering_pattern.enabled)
            {
                m_cycle.watering_duration_sec =
                    runtime_config.watering_pattern.on_sec * runtime_config.watering_pattern.repeat_count;
                m_cycle.watering_started = app_watering_run_pattern(runtime_config.watering_pattern.on_sec,
                                                                    runtime_config.watering_pattern.off_sec,
                                                                    runtime_config.watering_pattern.repeat_count,
                                                                    due_schedule.channel_mask,
                                                                    runtime_config.force_watering,
                                                                    app_cycle_idle_loop);
            }
            else
            {
                m_cycle.watering_started = app_watering_start_async(due_schedule.duration_sec,
                                                                    due_schedule.channel_mask,
                                                                    runtime_config.force_watering);
            }
            m_cycle.last_soil_moisture = app_watering_get_last_soil_moisture();
            APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                                m_cycle.watering_started ? APP_DEBUG_LOG_INFO : APP_DEBUG_LOG_WARNING,
                                APP_DEBUG_EVENT_WATERING_DUE_RESULT,
                                static_cast<int32_t>(due_schedule.duration_sec) | (m_cycle.watering_started ? (1L << 16) : 0),
                                static_cast<int32_t>(due_schedule.channel_mask));

            while (!runtime_config.watering_pattern.enabled && app_watering_is_in_progress())
            {
                app_watering_loop();
                app_network_loop();
                delay(50);
            }

            if (m_cycle.watering_started && should_probe_soil_calibration)
            {
                delay(2000);
                m_cycle.soil_raw_after_watering = app_watering_read_soil_raw_average(20, 40);
                const uint16_t before_raw = m_cycle.soil_raw_before_watering;
                const uint16_t after_raw = m_cycle.soil_raw_after_watering;
                const uint16_t delta_raw = before_raw > after_raw ? before_raw - after_raw : 0;
                if (delta_raw >= runtime_config.soil_calibration.min_delta_raw)
                {
                    m_cycle.soil_calibration_suggested = true;
                    m_cycle.soil_calibration_suggested_dry_raw = before_raw;
                    m_cycle.soil_calibration_suggested_wet_raw = after_raw;
                    if (runtime_config.soil_calibration.auto_mode_enabled &&
                        runtime_config.soil_calibration.apply_auto_calibration)
                    {
                        app_watering_set_soil_calibration(before_raw, after_raw);
                        app_runtime_config_update_soil_calibration(before_raw, after_raw);
                        m_cycle.soil_calibration_applied = true;
                        m_cycle.soil_calibration_dry_raw = before_raw;
                        m_cycle.soil_calibration_wet_raw = after_raw;
                    }
                }
                else if (runtime_config.soil_calibration.drift_check_enabled &&
                         delta_raw < runtime_config.soil_calibration.drift_tolerance_raw)
                {
                    m_cycle.soil_calibration_suggested = true;
                    m_cycle.soil_calibration_suggested_dry_raw = runtime_config.soil_calibration.dry_raw;
                    m_cycle.soil_calibration_suggested_wet_raw = runtime_config.soil_calibration.wet_raw;
                }
            }

            s_last_executed_schedule_utc = due_schedule_epoch_utc;
        }

        now_utc = time(nullptr);
        if (context.time_synced && app_runtime_config_is_valid())
        {
            const uint32_t schedule_sleep_sec = app_runtime_config_seconds_until_next_schedule(now_utc);
            result.next_sleep_sec = schedule_sleep_sec < runtime_config.ota_check_interval_sec
                                        ? schedule_sleep_sec
                                        : runtime_config.ota_check_interval_sec;
        }
        else
        {
            result.next_sleep_sec = context.network_retry_sleep_sec;
        }
        result.publish_debug_log = app_runtime_config_is_valid() && runtime_config.debug_log_on_wake;
        return result;
    }

    bool publish_device_status(const AppDeviceWakeContext &context,
                               const AppDeviceCycleResult &cycle_result) override
    {
        const app_runtime_config_t &runtime_config = app_runtime_config_get();
        const bool env_par_calibrated = runtime_config.env_calibration.par_umol_m2_s.calibrated;
        const bool env_soil_calibrated = app_env_soil_calibration_complete(runtime_config.env_calibration);
        const bool env_calibration_required =
            (runtime_config.env_sensors.par.enabled && !env_par_calibrated) ||
            (runtime_config.env_sensors.soil.enabled && !env_soil_calibrated);

        char payload[4096];
        snprintf(payload,
                 sizeof(payload),
                 "{\"seq\":%u,\"device_kind\":\"%s\",\"sensor_model\":\"WTR-ALL-IN-ONE-12V-RS485\",\"firmware_version\":\"%s\",\"firmware_build_id\":\"%s\",\"network_connected\":%s,\"runtime_config_valid\":%s,\"config_received\":%s,\"time_synced\":%s,\"watering_due\":%s,\"watering_started\":%s,\"startup_watering_test_requested\":%s,\"startup_watering_test_started\":%s,\"watering_duration_sec\":%u,\"channel_mask\":%lu,\"schedule_epoch_utc\":%ld,\"next_sleep_sec\":%lu,\"ota_check_interval_sec\":%lu,\"last_soil_moisture\":%u,\"threshold\":%u,\"force_watering\":%s,\"debug_log_on_wake\":%s,\"ota_update_attempted\":%s,\"watering_pattern_enabled\":%s,\"watering_pattern_on_sec\":%u,\"watering_pattern_off_sec\":%u,\"watering_pattern_repeat_count\":%u,\"soil_calibration_auto_mode\":%s,\"soil_calibration_applied\":%s,\"soil_calibration_suggested\":%s,\"soil_raw_before_watering\":%u,\"soil_raw_after_watering\":%u,\"soil_calibration_dry_raw\":%u,\"soil_calibration_wet_raw\":%u,\"soil_calibration_suggested_dry_raw\":%u,\"soil_calibration_suggested_wet_raw\":%u,\"sensor_12v_power_requested\":%s,\"sensor_12v_power_configured\":%s,\"sensor_12v_power_error\":%s,\"par_enabled\":%s,\"par_ok\":%s,\"par_modbus_slave_id\":%u,\"par_umol_m2_s\":%.1f,\"raw_par\":%u,\"soil_rs485_enabled\":%s,\"soil_rs485_ok\":%s,\"soil_rs485_modbus_slave_id\":%u,\"soil_moisture_percent\":%.1f,\"soil_temperature_c\":%.1f,\"soil_ec_us_cm\":%.1f,\"soil_ph\":%.2f,\"soil_n_mg_kg\":%.1f,\"soil_p_mg_kg\":%.1f,\"soil_k_mg_kg\":%.1f,\"raw_soil_moisture\":%u,\"raw_soil_temperature\":%u,\"raw_soil_ec\":%u,\"raw_soil_ph\":%u,\"raw_soil_nitrogen\":%u,\"raw_soil_phosphorus\":%u,\"raw_soil_potassium\":%u,\"env_calibration_required\":%s,\"env_calibration_mode\":\"%s\",\"env_calibration_target\":\"%s\",\"env_par_calibrated\":%s,\"env_soil_calibrated\":%s,\"env_calibration_capture_applied\":%s,\"env_calibration_capture_duplicate\":%s,\"env_calibration_capture_error\":%s}",
                 context.seq_id,
                 APP_DEVICE_KIND,
                 APP_FIRMWARE_VERSION,
                 APP_FIRMWARE_BUILD_ID,
                 context.network_connected ? "true" : "false",
                 m_cycle.runtime_config_valid ? "true" : "false",
                 context.config_received ? "true" : "false",
                 context.time_synced ? "true" : "false",
                 m_cycle.watering_due ? "true" : "false",
                 m_cycle.watering_started ? "true" : "false",
                 m_cycle.startup_watering_test_requested ? "true" : "false",
                 m_cycle.startup_watering_test_started ? "true" : "false",
                 m_cycle.watering_duration_sec,
                 static_cast<unsigned long>(m_cycle.channel_mask),
                 static_cast<long>(m_cycle.schedule_epoch_utc),
                 static_cast<unsigned long>(cycle_result.next_sleep_sec),
                 static_cast<unsigned long>(m_cycle.ota_check_interval_sec),
                 m_cycle.last_soil_moisture,
                 app_watering_get_threshold(),
                 m_cycle.force_watering ? "true" : "false",
                 m_cycle.debug_log_on_wake ? "true" : "false",
                 context.ota_update_attempted ? "true" : "false",
                 m_cycle.watering_pattern_enabled ? "true" : "false",
                 m_cycle.watering_pattern_on_sec,
                 m_cycle.watering_pattern_off_sec,
                 m_cycle.watering_pattern_repeat_count,
                 m_cycle.soil_calibration_auto_mode ? "true" : "false",
                 m_cycle.soil_calibration_applied ? "true" : "false",
                 m_cycle.soil_calibration_suggested ? "true" : "false",
                 m_cycle.soil_raw_before_watering,
                 m_cycle.soil_raw_after_watering,
                 m_cycle.soil_calibration_dry_raw,
                 m_cycle.soil_calibration_wet_raw,
                 m_cycle.soil_calibration_suggested_dry_raw,
                 m_cycle.soil_calibration_suggested_wet_raw,
                 m_cycle.rs485.sensor_power_requested ? "true" : "false",
                 m_cycle.rs485.sensor_power_configured ? "true" : "false",
                 m_cycle.rs485.sensor_power_error ? "true" : "false",
                 runtime_config.env_sensors.par.enabled ? "true" : "false",
                 m_cycle.rs485.par_ok ? "true" : "false",
                 static_cast<unsigned int>(runtime_config.env_sensors.par.modbus_slave_id),
                 static_cast<double>(m_cycle.rs485.par_umol_m2_s),
                 m_cycle.rs485.raw_par,
                 runtime_config.env_sensors.soil.enabled ? "true" : "false",
                 m_cycle.rs485.soil_rs485_ok ? "true" : "false",
                 static_cast<unsigned int>(runtime_config.env_sensors.soil.modbus_slave_id),
                 static_cast<double>(m_cycle.rs485.soil_moisture_percent),
                 static_cast<double>(m_cycle.rs485.soil_temperature_c),
                 static_cast<double>(m_cycle.rs485.soil_ec_us_cm),
                 static_cast<double>(m_cycle.rs485.soil_ph),
                 static_cast<double>(m_cycle.rs485.soil_n_mg_kg),
                 static_cast<double>(m_cycle.rs485.soil_p_mg_kg),
                 static_cast<double>(m_cycle.rs485.soil_k_mg_kg),
                 m_cycle.rs485.raw_soil_moisture,
                 m_cycle.rs485.raw_soil_temperature,
                 m_cycle.rs485.raw_soil_ec,
                 m_cycle.rs485.raw_soil_ph,
                 m_cycle.rs485.raw_soil_nitrogen,
                 m_cycle.rs485.raw_soil_phosphorus,
                 m_cycle.rs485.raw_soil_potassium,
                 env_calibration_required ? "true" : "false",
                 runtime_config.env_calibration.mode,
                 runtime_config.env_calibration.target,
                 env_par_calibrated ? "true" : "false",
                 env_soil_calibrated ? "true" : "false",
                 m_cycle.rs485.calibration_capture_applied ? "true" : "false",
                 m_cycle.rs485.calibration_capture_duplicate ? "true" : "false",
                 m_cycle.rs485.calibration_capture_error ? "true" : "false");

        Serial.printf("Sending status: %s\n", payload);
        const bool sent = app_network_send(APP_MSG_TYPE_STATUS,
                                           reinterpret_cast<const uint8_t *>(payload),
                                           strlen(payload),
                                           context.seq_id);
        if (sent)
        {
            APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP, APP_DEBUG_LOG_INFO, APP_DEBUG_EVENT_STATUS_SENT, 0, 0);
            Serial.printf("Status publish queued; draining MQTT for %u ms\n",
                          static_cast<unsigned int>(APP_MQTT_STATUS_PUBLISH_DRAIN_MS));
            app_network_flush(APP_MQTT_STATUS_PUBLISH_DRAIN_MS);
        }
        return sent;
    }

private:
    WateringCycleState m_cycle;
};

static WateringDevice s_watering_device;

int app_init()
{
    AppDeviceInitializeOptions options;
    options.setup_ap_enabled = true;
    options.start_network = true;
    options.print_littlefs_files = false;
    return s_watering_device.initialize(options);
}

void app_deinit()
{
    app_watering_deinit();
    hal_rs485_modbus_deinit();
    hal_power_switch_deinit();
}

void app_loop()
{
    s_watering_device.loop();
}
