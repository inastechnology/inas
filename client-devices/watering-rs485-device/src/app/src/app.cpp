#include "app.h"

#include <Arduino.h>
#include <string.h>
#include <time.h>

#include "app_debug_log.h"
#include "app_def.h"
#include "app_device.h"
#include "app_network.h"
#include "app_wrs_runtime_config.h"
#include "hal_mosfet_output.h"
#include "hal_power_switch.h"
#include "hal_rs485_bus.h"
#include "hal_rs485_sensor_protocol.h"

#ifndef APP_WRS_IRRIGATION1_PIN
#ifdef APP_WRS_VALVE_PIN
#define APP_WRS_IRRIGATION1_PIN APP_WRS_VALVE_PIN
#else
#define APP_WRS_IRRIGATION1_PIN D2
#endif
#endif

#ifndef APP_WRS_IRRIGATION2_PIN
#ifdef APP_WRS_PUMP_PIN
#define APP_WRS_IRRIGATION2_PIN APP_WRS_PUMP_PIN
#else
#define APP_WRS_IRRIGATION2_PIN D3
#endif
#endif

#ifndef APP_WRS_OUTPUT_ACTIVE_HIGH
#define APP_WRS_OUTPUT_ACTIVE_HIGH 1
#endif

#define APP_WRS_WATERING_DUE_GRACE_SEC (15 * 60)

RTC_DATA_ATTR static time_t s_last_executed_schedule_utc = 0;

static const uint8_t kWateringOutputPins[] = {
    APP_WRS_IRRIGATION1_PIN,
    APP_WRS_IRRIGATION2_PIN,
};
static constexpr uint32_t kWateringOutputMask = (1UL << (sizeof(kWateringOutputPins) / sizeof(kWateringOutputPins[0]))) - 1;

struct WrsSensorSample
{
    bool sensor_power_requested = false;
    bool sensor_power_configured = false;
    bool sensor_power_error = false;
    hal_rs485_soil_sample_t soil = {};
    hal_rs485_par_sample_t par = {};
};

struct WrsCycleState
{
    bool runtime_config_valid = false;
    bool schedule_due = false;
    bool auto_low_moisture_due = false;
    bool watering_due = false;
    bool watering_started = false;
    bool watering_completed = false;
    bool watering_skipped = false;
    const char *watering_reason = "none";
    const char *watering_stop_reason = "none";
    uint16_t watering_requested_duration_sec = 0;
    uint16_t watering_elapsed_sec = 0;
    uint16_t watering_monitor_reads = 0;
    uint32_t requested_channel_mask = 0;
    uint32_t output_channel_mask = 0;
    time_t schedule_epoch_utc = 0;
    float soil_moisture_before_watering = 0.0f;
    float soil_moisture_after_watering = 0.0f;
    bool soil_feedback_available_before_watering = false;
    bool soil_feedback_available_after_watering = false;
    WrsSensorSample sensors = {};
};

static int32_t pack_runtime_flags(const app_wrs_runtime_config_t &config)
{
    return static_cast<int32_t>(config.watering.moisture_threshold_percent) |
           (config.watering.force_watering ? (1L << 8) : 0) |
           (config.watering.auto_on_low_moisture ? (1L << 9) : 0) |
           (static_cast<int32_t>(config.schedule_count) << 16);
}

static uint32_t output_mask_for_channels(uint32_t requested_channel_mask)
{
    return requested_channel_mask & kWateringOutputMask;
}

class WateringRs485Device : public AppDevice
{
public:
    bool apply_runtime_config_json(const uint8_t *payload, size_t length) override
    {
        return app_wrs_runtime_config_apply_json(payload, length);
    }

    bool has_valid_runtime_config() const override
    {
        return app_wrs_runtime_config_is_valid();
    }

    bool is_runtime_config_received() const override
    {
        return app_wrs_runtime_config_is_received();
    }

protected:
    const char *device_name() const override
    {
        return "INA Watering RS485";
    }

    bool on_initialize() override
    {
        app_wrs_runtime_config_init();
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                            APP_DEBUG_LOG_INFO,
                            APP_DEBUG_EVENT_RUNTIME_CONFIG_INIT,
                            app_wrs_runtime_config_is_valid() ? 1 : 0,
                            app_wrs_runtime_config_get().debug_log_on_wake ? 1 : 0);

        hal_mosfet_output_init(kWateringOutputPins,
                               sizeof(kWateringOutputPins) / sizeof(kWateringOutputPins[0]),
                               APP_WRS_OUTPUT_ACTIVE_HIGH != 0);
        Serial.printf("WRS output map: output_mask=0x%lx irrigation1_pin=%u irrigation2_pin=%u\n",
                      static_cast<unsigned long>(kWateringOutputMask),
                      static_cast<unsigned int>(APP_WRS_IRRIGATION1_PIN),
                      static_cast<unsigned int>(APP_WRS_IRRIGATION2_PIN));
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_WATERING,
                            APP_DEBUG_LOG_INFO,
                            APP_DEBUG_EVENT_WATERING_OUTPUT_MAP,
                            static_cast<int32_t>(kWateringOutputMask),
                            0);

        const hal_power_switch_config_t power_switch_config = hal_power_switch_default_config();
        hal_power_switch_init(&power_switch_config);
        const hal_rs485_modbus_config_t rs485_config = hal_rs485_modbus_default_config();
        const bool rs485_ready = hal_rs485_bus_init(&rs485_config);
        Serial.printf("WRS RS485 bus ready=%s\n", rs485_ready ? "true" : "false");
        return rs485_ready;
    }

    void prepare_runtime_config_request() override
    {
        app_wrs_runtime_config_mark_waiting();
    }

    void on_runtime_config_ready(bool config_received) override
    {
        (void)config_received;
        const app_wrs_runtime_config_t &config = app_wrs_runtime_config_get();
        Serial.printf("WRS runtime config active: valid=%s sleep=%lu schedules=%u threshold=%u stop=%u max=%u check=%u auto=%s force=%s soil=%s par=%s power_settle=%lu\n",
                      config.valid ? "true" : "false",
                      static_cast<unsigned long>(config.sleep_sec),
                      static_cast<unsigned int>(config.schedule_count),
                      config.watering.moisture_threshold_percent,
                      config.watering.stop_moisture_percent,
                      config.watering.max_duration_sec,
                      config.watering.check_interval_sec,
                      config.watering.auto_on_low_moisture ? "true" : "false",
                      config.watering.force_watering ? "true" : "false",
                      config.sensors.soil.enabled ? "true" : "false",
                      config.sensors.par.enabled ? "true" : "false",
                      static_cast<unsigned long>(config.sensors.power_settle_ms));
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                            APP_DEBUG_LOG_INFO,
                            APP_DEBUG_EVENT_RUNTIME_CONFIG_ACTIVE,
                            pack_runtime_flags(config),
                            0);
    }

    const char *runtime_ntp_server() const override
    {
        return app_wrs_runtime_config_get().ntp_server;
    }

    int32_t runtime_timezone_offset_sec() const override
    {
        return app_wrs_runtime_config_get().timezone_offset_sec;
    }

    AppDeviceCycleResult run_device_cycle(const AppDeviceWakeContext &context) override
    {
        AppDeviceCycleResult result = {};
        const app_wrs_runtime_config_t &config = app_wrs_runtime_config_get();
        m_cycle = {};
        m_cycle.runtime_config_valid = app_wrs_runtime_config_is_valid();

        app_wrs_schedule_entry_t due_schedule = {};
        time_t due_schedule_epoch_utc = 0;
        const time_t now_utc = time(nullptr);
        m_cycle.schedule_due = context.time_synced &&
                               app_wrs_runtime_config_find_due_schedule(now_utc,
                                                                        s_last_executed_schedule_utc,
                                                                        &due_schedule,
                                                                        &due_schedule_epoch_utc);
        if (m_cycle.schedule_due && now_utc - due_schedule_epoch_utc > APP_WRS_WATERING_DUE_GRACE_SEC)
        {
            Serial.printf("WRS watering schedule due at %ld is too old; skipped at now=%ld\n",
                          static_cast<long>(due_schedule_epoch_utc),
                          static_cast<long>(now_utc));
            s_last_executed_schedule_utc = due_schedule_epoch_utc;
            m_cycle.schedule_due = false;
        }

        const bool keep_sensor_power = config.watering.enabled &&
                                       (m_cycle.schedule_due || config.watering.auto_on_low_moisture);
        read_sensors(keep_sensor_power);

        m_cycle.auto_low_moisture_due = config.watering.auto_on_low_moisture &&
                                        m_cycle.sensors.soil.ok &&
                                        m_cycle.sensors.soil.moisture_percent < config.watering.moisture_threshold_percent;
        m_cycle.watering_due = m_cycle.schedule_due || m_cycle.auto_low_moisture_due;
        m_cycle.watering_reason = m_cycle.schedule_due ? "schedule" : (m_cycle.auto_low_moisture_due ? "auto_low_moisture" : "none");
        if (m_cycle.watering_due && context.ota_update_attempted)
        {
            m_cycle.watering_skipped = true;
            m_cycle.watering_stop_reason = "ota_update_attempted";
        }
        else if (m_cycle.watering_due)
        {
            const uint16_t requested_duration = m_cycle.schedule_due
                                                    ? due_schedule.duration_sec
                                                    : config.watering.max_duration_sec;
            const uint32_t requested_channel_mask = m_cycle.schedule_due
                                                        ? due_schedule.channel_mask
                                                        : config.watering.channel_mask;
            m_cycle.schedule_epoch_utc = due_schedule_epoch_utc;
            run_watering_with_feedback(config, requested_duration, requested_channel_mask);
            if (m_cycle.schedule_due)
            {
                s_last_executed_schedule_utc = due_schedule_epoch_utc;
            }
        }

        if (hal_power_switch_is_enabled())
        {
            hal_power_switch_set_enabled(false);
        }

        const time_t finish_utc = time(nullptr);
        if (context.time_synced && app_wrs_runtime_config_is_valid())
        {
            const uint32_t schedule_sleep_sec = app_wrs_runtime_config_seconds_until_next_schedule(finish_utc);
            result.next_sleep_sec = min(config.sleep_sec, min(schedule_sleep_sec, config.ota_check_interval_sec));
        }
        else
        {
            result.next_sleep_sec = context.network_retry_sleep_sec;
        }
        result.publish_debug_log = app_wrs_runtime_config_is_valid() && config.debug_log_on_wake;
        return result;
    }

    bool publish_device_status(const AppDeviceWakeContext &context,
                               const AppDeviceCycleResult &cycle_result) override
    {
        const app_wrs_runtime_config_t &config = app_wrs_runtime_config_get();
        char payload[4096];
        snprintf(payload,
                 sizeof(payload),
                 "{\"seq\":%lu,\"device_kind\":\"%s\",\"sensor_model\":\"RS485-WATERING-AIO\",\"firmware_version\":\"%s\",\"firmware_build_id\":\"%s\",\"network_connected\":%s,\"runtime_config_valid\":%s,\"config_received\":%s,\"time_synced\":%s,\"ota_update_attempted\":%s,\"next_sleep_sec\":%lu,\"ota_check_interval_sec\":%lu,\"schedule_count\":%u,\"watering_enabled\":%s,\"watering_due\":%s,\"watering_reason\":\"%s\",\"watering_started\":%s,\"watering_completed\":%s,\"watering_skipped\":%s,\"watering_stop_reason\":\"%s\",\"watering_requested_duration_sec\":%u,\"watering_elapsed_sec\":%u,\"watering_monitor_reads\":%u,\"channel_mask\":%lu,\"output_channel_mask\":%lu,\"schedule_epoch_utc\":%ld,\"threshold\":%u,\"force_watering\":%s,\"wrs_auto_on_low_moisture\":%s,\"wrs_stop_moisture_percent\":%u,\"soil_moisture_before_watering\":%.1f,\"soil_moisture_after_watering\":%.1f,\"sensor_12v_power_requested\":%s,\"sensor_12v_power_configured\":%s,\"sensor_12v_power_error\":%s,\"soil_rs485_enabled\":%s,\"soil_rs485_ok\":%s,\"soil_rs485_modbus_slave_id\":%u,\"soil_moisture_percent\":%.1f,\"soil_temperature_c\":%.1f,\"soil_ec_us_cm\":%.1f,\"soil_ph\":%.2f,\"soil_n_mg_kg\":%.1f,\"soil_p_mg_kg\":%.1f,\"soil_k_mg_kg\":%.1f,\"raw_soil_moisture\":%u,\"raw_soil_temperature\":%u,\"raw_soil_ec\":%u,\"raw_soil_ph\":%u,\"raw_soil_nitrogen\":%u,\"raw_soil_phosphorus\":%u,\"raw_soil_potassium\":%u,\"par_enabled\":%s,\"par_ok\":%s,\"par_modbus_slave_id\":%u,\"par_umol_m2_s\":%.1f,\"raw_par\":%u}",
                 static_cast<unsigned long>(context.seq_id),
                 APP_DEVICE_KIND,
                 APP_FIRMWARE_VERSION,
                 APP_FIRMWARE_BUILD_ID,
                 context.network_connected ? "true" : "false",
                 m_cycle.runtime_config_valid ? "true" : "false",
                 context.config_received ? "true" : "false",
                 context.time_synced ? "true" : "false",
                 context.ota_update_attempted ? "true" : "false",
                 static_cast<unsigned long>(cycle_result.next_sleep_sec),
                 static_cast<unsigned long>(config.ota_check_interval_sec),
                 static_cast<unsigned int>(config.schedule_count),
                 config.watering.enabled ? "true" : "false",
                 m_cycle.watering_due ? "true" : "false",
                 m_cycle.watering_reason,
                 m_cycle.watering_started ? "true" : "false",
                 m_cycle.watering_completed ? "true" : "false",
                 m_cycle.watering_skipped ? "true" : "false",
                 m_cycle.watering_stop_reason,
                 m_cycle.watering_requested_duration_sec,
                 m_cycle.watering_elapsed_sec,
                 m_cycle.watering_monitor_reads,
                 static_cast<unsigned long>(m_cycle.requested_channel_mask),
                 static_cast<unsigned long>(m_cycle.output_channel_mask),
                 static_cast<long>(m_cycle.schedule_epoch_utc),
                 config.watering.moisture_threshold_percent,
                 config.watering.force_watering ? "true" : "false",
                 config.watering.auto_on_low_moisture ? "true" : "false",
                 config.watering.stop_moisture_percent,
                 static_cast<double>(m_cycle.soil_moisture_before_watering),
                 static_cast<double>(m_cycle.soil_moisture_after_watering),
                 m_cycle.sensors.sensor_power_requested ? "true" : "false",
                 m_cycle.sensors.sensor_power_configured ? "true" : "false",
                 m_cycle.sensors.sensor_power_error ? "true" : "false",
                 config.sensors.soil.enabled ? "true" : "false",
                 m_cycle.sensors.soil.ok ? "true" : "false",
                 static_cast<unsigned int>(config.sensors.soil.modbus_slave_id),
                 static_cast<double>(m_cycle.sensors.soil.moisture_percent),
                 static_cast<double>(m_cycle.sensors.soil.temperature_c),
                 static_cast<double>(m_cycle.sensors.soil.ec_us_cm),
                 static_cast<double>(m_cycle.sensors.soil.ph),
                 static_cast<double>(m_cycle.sensors.soil.n_mg_kg),
                 static_cast<double>(m_cycle.sensors.soil.p_mg_kg),
                 static_cast<double>(m_cycle.sensors.soil.k_mg_kg),
                 m_cycle.sensors.soil.raw_moisture,
                 m_cycle.sensors.soil.raw_temperature,
                 m_cycle.sensors.soil.raw_ec,
                 m_cycle.sensors.soil.raw_ph,
                 m_cycle.sensors.soil.raw_nitrogen,
                 m_cycle.sensors.soil.raw_phosphorus,
                 m_cycle.sensors.soil.raw_potassium,
                 config.sensors.par.enabled ? "true" : "false",
                 m_cycle.sensors.par.ok ? "true" : "false",
                 static_cast<unsigned int>(config.sensors.par.modbus_slave_id),
                 static_cast<double>(m_cycle.sensors.par.par_umol_m2_s),
                 m_cycle.sensors.par.raw_par);

        Serial.printf("Sending WRS status: %s\n", payload);
        const bool sent = app_network_send(APP_MSG_TYPE_STATUS,
                                           reinterpret_cast<const uint8_t *>(payload),
                                           strlen(payload),
                                           context.seq_id);
        if (sent)
        {
            APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP, APP_DEBUG_LOG_INFO, APP_DEBUG_EVENT_STATUS_SENT, 0, 0);
            app_network_flush(APP_MQTT_STATUS_PUBLISH_DRAIN_MS);
        }
        return sent;
    }

private:
    WrsCycleState m_cycle = {};

    bool enable_sensor_power(WrsSensorSample &sample, const app_wrs_runtime_config_t &config)
    {
        sample.sensor_power_requested = config.sensors.soil.enabled || config.sensors.par.enabled;
        sample.sensor_power_configured = hal_power_switch_is_configured();
        if (!sample.sensor_power_requested)
        {
            return true;
        }
        if (hal_power_switch_is_enabled())
        {
            return true;
        }
        if (!hal_power_switch_enable_and_wait(config.sensors.power_settle_ms))
        {
            sample.sensor_power_error = true;
            hal_power_switch_set_enabled(false);
            return false;
        }
        return true;
    }

    void read_sensors(bool keep_power_enabled)
    {
        const app_wrs_runtime_config_t &config = app_wrs_runtime_config_get();
        WrsSensorSample sample = {};
        if (!enable_sensor_power(sample, config))
        {
            m_cycle.sensors = sample;
            return;
        }

        if (config.sensors.soil.enabled)
        {
            hal_rs485_soil_sensor_read(&config.sensors.soil, &sample.soil);
        }
        if (config.sensors.par.enabled)
        {
            hal_rs485_par_sensor_read(&config.sensors.par, &sample.par);
        }
        if (!keep_power_enabled)
        {
            hal_power_switch_set_enabled(false);
        }
        m_cycle.sensors = sample;
    }

    bool should_start_watering(const app_wrs_runtime_config_t &config)
    {
        if (!config.watering.enabled)
        {
            m_cycle.watering_skipped = true;
            m_cycle.watering_stop_reason = "watering_disabled";
            return false;
        }
        if (m_cycle.output_channel_mask == 0)
        {
            m_cycle.watering_skipped = true;
            m_cycle.watering_stop_reason = "invalid_channel_mask";
            return false;
        }
        if (config.watering.force_watering)
        {
            return true;
        }
        if (!m_cycle.sensors.soil.ok)
        {
            if (!config.watering.require_soil_feedback)
            {
                return true;
            }
            m_cycle.watering_skipped = true;
            m_cycle.watering_stop_reason = "soil_feedback_unavailable";
            return false;
        }
        if (m_cycle.sensors.soil.moisture_percent >= config.watering.moisture_threshold_percent)
        {
            m_cycle.watering_skipped = true;
            m_cycle.watering_stop_reason = "moisture_above_threshold";
            return false;
        }
        return true;
    }

    void run_watering_with_feedback(const app_wrs_runtime_config_t &config,
                                    uint16_t requested_duration_sec,
                                    uint32_t requested_channel_mask)
    {
        m_cycle.requested_channel_mask = requested_channel_mask;
        m_cycle.output_channel_mask = output_mask_for_channels(requested_channel_mask);
        m_cycle.soil_feedback_available_before_watering = m_cycle.sensors.soil.ok;
        m_cycle.soil_moisture_before_watering = m_cycle.sensors.soil.moisture_percent;
        m_cycle.soil_moisture_after_watering = m_cycle.sensors.soil.moisture_percent;
        m_cycle.watering_requested_duration_sec = min(requested_duration_sec, config.watering.max_duration_sec);

        if (!should_start_watering(config))
        {
            return;
        }

        while (m_cycle.watering_elapsed_sec < m_cycle.watering_requested_duration_sec)
        {
            const uint16_t remaining_sec = m_cycle.watering_requested_duration_sec - m_cycle.watering_elapsed_sec;
            const uint16_t chunk_sec = min(remaining_sec, config.watering.check_interval_sec);
            if (!hal_mosfet_output_start_channels(m_cycle.output_channel_mask, static_cast<uint32_t>(chunk_sec) * 1000UL))
            {
                m_cycle.watering_skipped = !m_cycle.watering_started;
                m_cycle.watering_stop_reason = "output_start_failed";
                APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_WATERING,
                                    APP_DEBUG_LOG_ERROR,
                                    APP_DEBUG_EVENT_WATERING_OUTPUT_START_FAILED,
                                    chunk_sec,
                                    static_cast<int32_t>(m_cycle.output_channel_mask));
                return;
            }

            m_cycle.watering_started = true;
            APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_WATERING,
                                APP_DEBUG_LOG_INFO,
                                APP_DEBUG_EVENT_WATERING_STARTED,
                                chunk_sec,
                                static_cast<int32_t>(m_cycle.output_channel_mask));
            while (hal_mosfet_output_is_in_progress())
            {
                hal_mosfet_output_loop();
                app_network_loop();
                delay(50);
            }
            m_cycle.watering_elapsed_sec += chunk_sec;

            read_sensors(true);
            m_cycle.watering_monitor_reads++;
            m_cycle.soil_feedback_available_after_watering = m_cycle.sensors.soil.ok;
            m_cycle.soil_moisture_after_watering = m_cycle.sensors.soil.moisture_percent;

            if (!m_cycle.sensors.soil.ok && config.watering.require_soil_feedback)
            {
                m_cycle.watering_stop_reason = "soil_feedback_lost";
                hal_mosfet_output_stop_all();
                return;
            }
            if (m_cycle.sensors.soil.ok &&
                m_cycle.sensors.soil.moisture_percent >= config.watering.stop_moisture_percent)
            {
                m_cycle.watering_completed = true;
                m_cycle.watering_stop_reason = "target_moisture_reached";
                hal_mosfet_output_stop_all();
                APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_WATERING,
                                    APP_DEBUG_LOG_INFO,
                                    APP_DEBUG_EVENT_WATERING_COMPLETED,
                                    static_cast<int32_t>(m_cycle.sensors.soil.moisture_percent),
                                    m_cycle.watering_elapsed_sec);
                return;
            }
        }

        m_cycle.watering_completed = true;
        m_cycle.watering_stop_reason = "duration_limit_reached";
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_WATERING,
                            APP_DEBUG_LOG_INFO,
                            APP_DEBUG_EVENT_WATERING_COMPLETED,
                            m_cycle.watering_elapsed_sec,
                            0);
    }
};

static WateringRs485Device s_device;

int app_init()
{
    AppDeviceInitializeOptions options;
    options.setup_ap_enabled = true;
    options.start_network = true;
    options.print_littlefs_files = false;
    return s_device.initialize(options);
}

void app_deinit()
{
    hal_mosfet_output_deinit();
    hal_power_switch_deinit();
    hal_rs485_bus_deinit();
}

void app_loop()
{
    s_device.loop();
}
