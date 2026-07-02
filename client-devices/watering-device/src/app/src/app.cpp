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

#define APP_WATERING_DUE_GRACE_SEC (15 * 60)

RTC_DATA_ATTR static time_t s_last_executed_schedule_utc = 0;

static int32_t app_pack_runtime_flags(uint8_t threshold, bool force_watering, bool debug_log_on_wake, uint8_t schedule_count)
{
    return static_cast<int32_t>(threshold) |
           (force_watering ? (1L << 8) : 0) |
           (debug_log_on_wake ? (1L << 9) : 0) |
           (static_cast<int32_t>(schedule_count) << 16);
}

struct WateringCycleState
{
    bool watering_due = false;
    bool watering_started = false;
    uint16_t watering_duration_sec = 0;
    uint32_t channel_mask = 0;
    time_t schedule_epoch_utc = 0;
    uint8_t last_soil_moisture = 0;
    bool force_watering = false;
    bool debug_log_on_wake = false;
    bool runtime_config_valid = false;
    uint32_t ota_check_interval_sec = APP_RUNTIME_DEFAULT_OTA_CHECK_INTERVAL_SEC;
};

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
        Serial.printf("Runtime config in app loop: threshold=%u force_watering=%s debug_log_on_wake=%s ota_check_interval_sec=%lu\n",
                      runtime_config.moisture_threshold,
                      runtime_config.force_watering ? "true" : "false",
                      runtime_config.debug_log_on_wake ? "true" : "false",
                      static_cast<unsigned long>(runtime_config.ota_check_interval_sec));
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
        m_cycle.last_soil_moisture = app_watering_get_last_soil_moisture();
        m_cycle.force_watering = runtime_config.force_watering;
        m_cycle.debug_log_on_wake = runtime_config.debug_log_on_wake;
        m_cycle.runtime_config_valid = app_runtime_config_is_valid();
        m_cycle.ota_check_interval_sec = runtime_config.ota_check_interval_sec;

        time_t now_utc = time(nullptr);
        app_schedule_entry_t due_schedule = {};
        time_t due_schedule_epoch_utc = 0;
        m_cycle.watering_due = context.time_synced &&
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
        else if (m_cycle.watering_due)
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

            m_cycle.watering_started = app_watering_start_async(due_schedule.duration_sec,
                                                                due_schedule.channel_mask,
                                                                runtime_config.force_watering);
            m_cycle.last_soil_moisture = app_watering_get_last_soil_moisture();
            APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                                m_cycle.watering_started ? APP_DEBUG_LOG_INFO : APP_DEBUG_LOG_WARNING,
                                APP_DEBUG_EVENT_WATERING_DUE_RESULT,
                                static_cast<int32_t>(due_schedule.duration_sec) | (m_cycle.watering_started ? (1L << 16) : 0),
                                static_cast<int32_t>(due_schedule.channel_mask));

            while (app_watering_is_in_progress())
            {
                app_watering_loop();
                app_network_loop();
                delay(50);
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
        char payload[1024];
        snprintf(payload,
                 sizeof(payload),
                 "{\"seq\":%u,\"device_kind\":\"%s\",\"firmware_version\":\"%s\",\"firmware_build_id\":\"%s\",\"network_connected\":%s,\"runtime_config_valid\":%s,\"config_received\":%s,\"time_synced\":%s,\"watering_due\":%s,\"watering_started\":%s,\"watering_duration_sec\":%u,\"channel_mask\":%lu,\"schedule_epoch_utc\":%ld,\"next_sleep_sec\":%lu,\"ota_check_interval_sec\":%lu,\"last_soil_moisture\":%u,\"threshold\":%u,\"force_watering\":%s,\"debug_log_on_wake\":%s,\"ota_update_attempted\":%s}",
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
                 m_cycle.watering_duration_sec,
                 static_cast<unsigned long>(m_cycle.channel_mask),
                 static_cast<long>(m_cycle.schedule_epoch_utc),
                 static_cast<unsigned long>(cycle_result.next_sleep_sec),
                 static_cast<unsigned long>(m_cycle.ota_check_interval_sec),
                 m_cycle.last_soil_moisture,
                 app_watering_get_threshold(),
                 m_cycle.force_watering ? "true" : "false",
                 m_cycle.debug_log_on_wake ? "true" : "false",
                 context.ota_update_attempted ? "true" : "false");

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
}

void app_loop()
{
    s_watering_device.loop();
}
