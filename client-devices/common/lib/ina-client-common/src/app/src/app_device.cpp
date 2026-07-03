#include "app_device.h"

#include <Arduino.h>
#include <LittleFS.h>
#include <string.h>

#include "esp_log.h"
#include "esp_system.h"

#include "app_config.h"
#include "app_debug_log.h"
#include "app_def.h"
#include "app_device_adapter.h"
#include "app_initial_setting.h"
#include "app_network.h"
#include "app_ota.h"
#include "app_task.h"
#include "app_time_sync.h"

#define TAG "app_device"

int AppDevice::initialize(const AppDeviceInitializeOptions &options)
{
    m_options = options;

    Serial.begin(m_options.serial_baud);
    app_debug_log_reset();
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                        APP_DEBUG_LOG_INFO,
                        APP_DEBUG_EVENT_BOOT,
                        static_cast<int32_t>(esp_reset_reason()),
                        0);
    esp_log_level_set(TAG, ESP_LOG_DEBUG);
    ESP_LOGI(TAG, "Start");
    print_boot_settings();

    if (!mount_littlefs())
    {
        return -1;
    }

    Serial.println("Load Config...");
    appConfig.init();
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                        APP_DEBUG_LOG_INFO,
                        APP_DEBUG_EVENT_CONFIG_LOADED,
                        appConfig.is_network_configured() ? 1 : 0,
                        static_cast<int32_t>(appConfig.crc32));

    if (m_options.setup_ap_enabled)
    {
        app_initial_setting_handle_setup_portal_request();
    }

    app_task_init();
    app_device_adapter_set(this);
    if (!on_initialize())
    {
        Serial.println("Device initialization failed");
        return -1;
    }
    app_ota_init();

    pinMode(APP_STATUS_LED_PIN, OUTPUT);
    digitalWrite(APP_STATUS_LED_PIN, APP_STATUS_LED_ACTIVE_LOW ? HIGH : LOW);

    if (m_options.print_littlefs_files)
    {
        print_littlefs_files();
    }

    app_network_set_setup_portal_enabled(m_options.setup_ap_enabled);
    if (m_options.start_network)
    {
        m_network_started = app_network_start();
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                            m_network_started ? APP_DEBUG_LOG_INFO : APP_DEBUG_LOG_ERROR,
                            APP_DEBUG_EVENT_NETWORK_START,
                            m_network_started ? 1 : 0,
                            app_network_is_connected() ? 1 : 0);
    }

    return 0;
}

void AppDevice::loop()
{
    AppDeviceWakeContext context = {};
    context.seq_id = esp_random() & 0x3FF;
    context.woke_from_deep_sleep = esp_reset_reason() == ESP_RST_DEEPSLEEP;
    context.network_retry_sleep_sec = m_options.network_retry_sleep_sec;

    context.network_connected = app_network_is_connected();
    if (!context.network_connected && m_network_started)
    {
        context.network_connected = app_network_reconnect();
        if (!context.network_connected)
        {
            ESP_LOGE(TAG, "Failed to reconnect; continuing offline when saved runtime config is available.");
        }
    }
    if (!context.network_connected)
    {
        Serial.println("Network is unavailable in this wake cycle.");
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP, APP_DEBUG_LOG_ERROR, APP_DEBUG_EVENT_NETWORK_UNAVAILABLE, 0, 0);
    }
    else
    {
        app_network_loop();
        app_ota_publish_pending_boot_status(context.seq_id);
    }

    prepare_runtime_config_request();
    context.config_requested = context.network_connected && app_network_request_runtime_config();
    context.config_received = context.config_requested && app_network_wait_for_runtime_config(m_options.config_fetch_timeout_ms);
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                        context.config_received ? APP_DEBUG_LOG_INFO : APP_DEBUG_LOG_WARNING,
                        APP_DEBUG_EVENT_RUNTIME_CONFIG_REQUEST,
                        context.config_requested ? 1 : 0,
                        context.config_received ? 1 : 0);
    if (!context.config_received)
    {
        Serial.println("Runtime config was not received; using saved/default configuration");
    }
    on_runtime_config_ready(context.config_received);

    if (context.network_connected)
    {
        context.ota_update_attempted = check_ota_update(context.seq_id);
    }

    context.time_synced = sync_time(context);

    AppDeviceCycleResult cycle_result = run_device_cycle(context);
    if (cycle_result.next_sleep_sec < m_options.min_sleep_sec)
    {
        cycle_result.next_sleep_sec = m_options.min_sleep_sec;
    }
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                        APP_DEBUG_LOG_INFO,
                        APP_DEBUG_EVENT_SLEEP_PLANNED,
                        static_cast<int32_t>(cycle_result.next_sleep_sec),
                        0);

    bool status_sent = false;
    if (context.network_connected)
    {
        status_sent = publish_device_status(context, cycle_result);
    }
    if (context.network_connected && !status_sent)
    {
        Serial.println("Failed to send status");
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP, APP_DEBUG_LOG_ERROR, APP_DEBUG_EVENT_STATUS_FAILED, 0, 0);
    }
    else if (!context.network_connected)
    {
        Serial.println("Skip status publish because network is unavailable");
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP, APP_DEBUG_LOG_WARNING, APP_DEBUG_EVENT_STATUS_SKIPPED, 0, 0);
    }

    if (context.network_connected && cycle_result.publish_debug_log)
    {
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                            APP_DEBUG_LOG_INFO,
                            APP_DEBUG_EVENT_DEBUG_LOG_PUBLISH_ENABLED,
                            status_sent ? 1 : 0,
                            static_cast<int32_t>(cycle_result.next_sleep_sec));
        if (app_debug_log_publish(context.seq_id))
        {
            app_network_flush(APP_DEBUG_LOG_PUBLISH_DRAIN_MS);
        }
        else
        {
            Serial.println("Failed to send debug log");
        }
    }

    app_network_stop();
    sleep(cycle_result.next_sleep_sec);
}

void AppDevice::print_boot_settings() const
{
    Serial.println();
    Serial.printf("========== %s ==========\n", device_name());
    Serial.printf("Build: %s %s\n", __DATE__, __TIME__);
    Serial.printf("Reset reason: %d\n", static_cast<int>(esp_reset_reason()));
    Serial.printf("LittleFS partition: %s\n", APP_LITTLEFS_PARTITION_LABEL);
    Serial.printf("Setup AP: %s\n", m_options.setup_ap_enabled ? "enabled" : "disabled");
    Serial.printf("Setup AP SSID: %s\n", APP_INITIAL_SETTING_SSID);
    Serial.printf("Setup AP Password: %s (len=%u)\n",
                  strlen(APP_INITIAL_SETTING_PASS) > 0 ? "[SET]" : "(empty)",
                  static_cast<unsigned int>(strlen(APP_INITIAL_SETTING_PASS)));
    Serial.printf("Setup AP IP: %s\n", APP_INITIAL_SETTING_AP_IP);
    Serial.printf("Wi-Fi connect timeout: %u ms\n", static_cast<unsigned int>(APP_WIFI_CONNECT_TIMEOUT_MS));
    Serial.printf("MQTT connect retries: %u delay=%u ms\n",
                  static_cast<unsigned int>(APP_MQTT_CONNECT_RETRY_COUNT),
                  static_cast<unsigned int>(APP_MQTT_CONNECT_RETRY_DELAY_MS));
    Serial.printf("MQTT TCP probe: %s timeout=%u ms\n",
                  APP_MQTT_TCP_PROBE_ENABLED ? "enabled" : "disabled",
                  static_cast<unsigned int>(APP_MQTT_TCP_PROBE_TIMEOUT_MS));
    Serial.printf("Setup portal button pin: %u\n", static_cast<unsigned int>(APP_SETUP_PORTAL_BUTTON_PIN));
    Serial.printf("Setup portal arm window: %u ms\n", static_cast<unsigned int>(APP_SETUP_PORTAL_ARM_WINDOW_MS));
    Serial.printf("Setup portal hold: %u ms\n", static_cast<unsigned int>(APP_SETUP_PORTAL_HOLD_MS));
    Serial.printf("Connection reset hold: %u ms\n", static_cast<unsigned int>(APP_SETUP_PORTAL_RESET_HOLD_MS));
    Serial.printf("Setup portal recovery idle timeout: %u ms\n", static_cast<unsigned int>(APP_SETUP_PORTAL_RECOVERY_TIMEOUT_MS));
    Serial.printf("Status LED pin: %u active_low=%s request_blink=%u ms active_blink=%u ms\n",
                  static_cast<unsigned int>(APP_STATUS_LED_PIN),
                  APP_STATUS_LED_ACTIVE_LOW ? "true" : "false",
                  static_cast<unsigned int>(APP_SETUP_PORTAL_REQUEST_LED_BLINK_MS),
                  static_cast<unsigned int>(APP_SETUP_PORTAL_ACTIVE_LED_BLINK_MS));
    Serial.println("==========================================");
}

bool AppDevice::mount_littlefs() const
{
    Serial.printf("Mounting LittleFS label=%s mount_point=/littlefs...\n", APP_LITTLEFS_PARTITION_LABEL);
    if (!LittleFS.begin(true, "/littlefs", 10, APP_LITTLEFS_PARTITION_LABEL))
    {
        Serial.println("An Error has occurred while mounting LittleFS; app loop will not start.");
        return false;
    }

    Serial.println("LittleFS mounted successfully");
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP, APP_DEBUG_LOG_INFO, APP_DEBUG_EVENT_LITTLEFS_MOUNTED, 0, 0);
    return true;
}

void AppDevice::print_littlefs_files() const
{
    Serial.println("Files in LittleFS:");
    File root = LittleFS.open("/");
    File file = root.openNextFile();
    while (file)
    {
        Serial.print("FILE: ");
        Serial.println(file.name());
        file.close();
        file = root.openNextFile();
    }
}

bool AppDevice::sync_time(const AppDeviceWakeContext &context) const
{
    bool time_synced = false;
    if (context.network_connected)
    {
        time_synced = app_time_sync_with_ntp(runtime_ntp_server(),
                                             runtime_timezone_offset_sec(),
                                             m_options.ntp_sync_timeout_ms);
        if (!time_synced && context.woke_from_deep_sleep && app_time_is_synchronized())
        {
            Serial.println("NTP sync failed; using existing RTC time from deep sleep wake.");
            APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                                APP_DEBUG_LOG_WARNING,
                                APP_DEBUG_EVENT_TIME_SYNC_NTP_FAILED_RTC,
                                1,
                                0);
            time_synced = true;
        }
    }
    else if (context.woke_from_deep_sleep && app_time_is_synchronized())
    {
        Serial.println("Using existing RTC time from deep sleep wake for offline schedule evaluation.");
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP, APP_DEBUG_LOG_WARNING, APP_DEBUG_EVENT_TIME_SYNC_OFFLINE_RTC, 1, 0);
        time_synced = true;
    }
    else
    {
        Serial.println("Time is not synchronized or this is not a deep sleep wake; offline schedule evaluation is skipped.");
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                            APP_DEBUG_LOG_ERROR,
                            APP_DEBUG_EVENT_TIME_SYNC_UNAVAILABLE,
                            context.woke_from_deep_sleep ? 1 : 0,
                            0);
    }

    if (time_synced)
    {
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                            APP_DEBUG_LOG_INFO,
                            APP_DEBUG_EVENT_TIME_SYNC_OK,
                            static_cast<int32_t>(time(nullptr)),
                            0);
    }
    return time_synced;
}

bool AppDevice::check_ota_update(uint32_t seq_id) const
{
    app_ota_mark_waiting();
    bool ota_requested = false;
    bool ota_offer_received = false;
    const uint32_t started_at_ms = millis();
    const uint8_t request_retry_count = APP_OTA_REQUEST_RETRY_COUNT > 0 ? APP_OTA_REQUEST_RETRY_COUNT : 1;
    const uint32_t wait_slice_ms = APP_OTA_OFFER_WAIT_MS / request_retry_count;

    for (uint8_t attempt = 1; attempt <= request_retry_count; attempt++)
    {
        const uint32_t elapsed_ms = millis() - started_at_ms;
        if (elapsed_ms >= APP_OTA_OFFER_WAIT_MS)
        {
            break;
        }

        const bool request_sent = app_network_request_ota_update(seq_id);
        ota_requested = ota_requested || request_sent;
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                            request_sent ? APP_DEBUG_LOG_INFO : APP_DEBUG_LOG_ERROR,
                            request_sent ? APP_DEBUG_EVENT_OTA_REQUEST_SENT : APP_DEBUG_EVENT_OTA_REQUEST_FAILED,
                            attempt,
                            APP_OTA_OFFER_WAIT_MS);
        if (!request_sent)
        {
            continue;
        }

        const uint32_t remaining_ms = APP_OTA_OFFER_WAIT_MS - elapsed_ms;
        uint32_t wait_ms = wait_slice_ms > 0 ? wait_slice_ms : remaining_ms;
        if (attempt == request_retry_count || wait_ms > remaining_ms)
        {
            wait_ms = remaining_ms;
        }
        ota_offer_received = app_network_wait_for_ota_offer(wait_ms);
        if (ota_offer_received)
        {
            break;
        }
    }

    if (ota_offer_received)
    {
        app_ota_finish_waiting();
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                            APP_DEBUG_LOG_INFO,
                            APP_DEBUG_EVENT_OTA_OFFER_RECEIVED,
                            1,
                            APP_OTA_OFFER_WAIT_MS);
        const bool ota_attempted = app_ota_handle_offer(seq_id);
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                            ota_attempted ? APP_DEBUG_LOG_INFO : APP_DEBUG_LOG_WARNING,
                            APP_DEBUG_EVENT_OTA_HANDLE_RESULT,
                            ota_attempted ? 1 : 0,
                            0);
        return ota_attempted;
    }

    app_ota_finish_waiting();
    if (!ota_requested)
    {
        Serial.println("OTA update request was not sent; reporting failure before normal wake cycle continues");
        app_ota_publish_request_failed_status(seq_id);
        return false;
    }

    Serial.println("OTA offer was not received; reporting timeout before normal wake cycle continues");
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                        APP_DEBUG_LOG_WARNING,
                        APP_DEBUG_EVENT_OTA_OFFER_TIMEOUT,
                        APP_OTA_OFFER_WAIT_MS,
                        0);
    app_ota_publish_offer_timeout_status(seq_id, APP_OTA_OFFER_WAIT_MS);
    return false;
}

void AppDevice::sleep(uint32_t sleep_sec) const
{
    Serial.printf("Sleep %lu sec\n", static_cast<unsigned long>(sleep_sec));
    Serial.flush();
    esp_sleep_enable_timer_wakeup(static_cast<uint64_t>(sleep_sec) * 1000000ULL);
    esp_deep_sleep_start();
}
