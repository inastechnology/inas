#include "app.h"
#include <Arduino.h>
#include "LittleFS.h"
#include "esp_system.h"
#include "app_config.h"
#include "app_camera.h"
#include "app_debug_log.h"
#include "app_audio.h"
#include "app_initial_setting.h"
#include "app_network.h"
#include "app_runtime_config.h"
#include "app_sensor.h"
#include "app_time_sync.h"
#include "app_utils.h"

#include "app_task.h"
#include "app_watering.h"
#include "app_notifier.h"

#define TAG "app"

#define APP_CONFIG_FETCH_TIMEOUT_MS 5000
#define APP_NTP_SYNC_TIMEOUT_MS 15000
#define APP_MIN_SLEEP_SEC 5
#define APP_NETWORK_RETRY_SLEEP_SEC 60

RTC_DATA_ATTR static time_t s_last_executed_schedule_utc = 0;
static bool s_network_started = false;

void core0_loop(void *arg);

static int32_t app_pack_runtime_flags(uint8_t threshold, bool force_watering, bool debug_log_on_wake, uint8_t schedule_count)
{
    return static_cast<int32_t>(threshold) |
           (force_watering ? (1L << 8) : 0) |
           (debug_log_on_wake ? (1L << 9) : 0) |
           (static_cast<int32_t>(schedule_count) << 16);
}

static void app_print_boot_settings()
{
    Serial.println();
    Serial.println("========== INA Water Controller ==========");
    Serial.printf("Build: %s %s\n", __DATE__, __TIME__);
    Serial.printf("Reset reason: %d\n", static_cast<int>(esp_reset_reason()));
    Serial.printf("LittleFS partition: %s\n", APP_LITTLEFS_PARTITION_LABEL);
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

static bool app_publish_status(uint32_t seq_id,
                               bool config_received,
                               bool time_synced,
                               bool watering_due,
                               bool watering_started,
                               uint16_t watering_duration_sec,
                               uint32_t channel_mask,
                               time_t schedule_epoch_utc,
                               uint32_t next_sleep_sec,
                               uint8_t last_soil_moisture,
                               bool force_watering,
                               bool debug_log_on_wake,
                               bool network_connected,
                               bool runtime_config_valid)
{
    char payload[768];
    snprintf(payload,
             sizeof(payload),
             "{\"seq\":%u,\"network_connected\":%s,\"runtime_config_valid\":%s,\"config_received\":%s,\"time_synced\":%s,\"watering_due\":%s,\"watering_started\":%s,\"watering_duration_sec\":%u,\"channel_mask\":%lu,\"schedule_epoch_utc\":%ld,\"next_sleep_sec\":%lu,\"last_soil_moisture\":%u,\"threshold\":%u,\"force_watering\":%s,\"debug_log_on_wake\":%s}",
             seq_id,
             network_connected ? "true" : "false",
             runtime_config_valid ? "true" : "false",
             config_received ? "true" : "false",
             time_synced ? "true" : "false",
             watering_due ? "true" : "false",
             watering_started ? "true" : "false",
             watering_duration_sec,
             static_cast<unsigned long>(channel_mask),
             static_cast<long>(schedule_epoch_utc),
             static_cast<unsigned long>(next_sleep_sec),
             last_soil_moisture,
             app_watering_get_threshold(),
             force_watering ? "true" : "false",
             debug_log_on_wake ? "true" : "false");

    Serial.printf("Sending status: %s\n", payload);
    const bool sent = app_network_send(APP_MSG_TYPE_STATUS, reinterpret_cast<const uint8_t *>(payload), strlen(payload), seq_id);
    if (sent)
    {
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP, APP_DEBUG_LOG_INFO, APP_DEBUG_EVENT_STATUS_SENT, 0, 0);
        Serial.printf("Status publish queued; draining MQTT for %u ms\n",
                      static_cast<unsigned int>(APP_MQTT_STATUS_PUBLISH_DRAIN_MS));
        app_network_flush(APP_MQTT_STATUS_PUBLISH_DRAIN_MS);
    }
    return sent;
}

int app_init()
{
    Serial.begin(115200);
    app_debug_log_reset();
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                        APP_DEBUG_LOG_INFO,
                        APP_DEBUG_EVENT_BOOT,
                        static_cast<int32_t>(esp_reset_reason()),
                        0);
    esp_log_level_set(TAG, ESP_LOG_DEBUG);
    ESP_LOGI(TAG, "Start");
    app_print_boot_settings();

    // LittleFS
    Serial.printf("Mounting LittleFS label=%s mount_point=/littlefs...\n", APP_LITTLEFS_PARTITION_LABEL);
    if (!LittleFS.begin(true, "/littlefs", 10, APP_LITTLEFS_PARTITION_LABEL))
    {
        Serial.println("An Error has occurred while mounting LittleFS; app loop will not start.");
        return -1;
    }
    else
    {
        Serial.println("LittleFS mounted successfully");
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP, APP_DEBUG_LOG_INFO, APP_DEBUG_EVENT_LITTLEFS_MOUNTED, 0, 0);
    }

    // config
    Serial.println("Load Config...");
    appConfig.init();
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                        APP_DEBUG_LOG_INFO,
                        APP_DEBUG_EVENT_CONFIG_LOADED,
                        appConfig.is_network_configured() ? 1 : 0,
                        static_cast<int32_t>(appConfig.crc32));

    app_initial_setting_handle_setup_portal_request();

    app_task_init();
    app_runtime_config_init();
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                        APP_DEBUG_LOG_INFO,
                        APP_DEBUG_EVENT_RUNTIME_CONFIG_INIT,
                        app_runtime_config_is_valid() ? 1 : 0,
                        app_runtime_config_get().debug_log_on_wake ? 1 : 0);

    // sensor
    app_watering_init();

    // network
    s_network_started = app_network_start();
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                        s_network_started ? APP_DEBUG_LOG_INFO : APP_DEBUG_LOG_ERROR,
                        APP_DEBUG_EVENT_NETWORK_START,
                        s_network_started ? 1 : 0,
                        app_network_is_connected() ? 1 : 0);
    pinMode(APP_STATUS_LED_PIN, OUTPUT);
    digitalWrite(APP_STATUS_LED_PIN, APP_STATUS_LED_ACTIVE_LOW ? HIGH : LOW);

    // show files in LittleFS
    Serial.println("Files in LittleFS:");
    {
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

    File file = LittleFS.open("/text.txt");
    if (!file)
    {
        Serial.println("File open failed");
    }
    else
    {
        Serial.println("File open success");
        String read_text = file.readString();
        Serial.println("Read text: " + read_text);
        // check is readabled
        String text_txt = "hello, world!!!!!!!!!!";
        if (read_text != text_txt)
        {
            Serial.println("!!!! File read failed:");
            Serial.println("Expected: " + text_txt);
            Serial.println("Actual: " + read_text);
        }
        file.close();
    }

    // app_audio_init();
    // app_camera_init();

    return 0;
}
void app_deinit() {}
void app_loop()
{
    const uint32_t seqId = esp_random() & 0x3FF;
    const bool woke_from_deep_sleep = (esp_reset_reason() == ESP_RST_DEEPSLEEP);

    bool network_connected = app_network_is_connected();
    if (!network_connected && s_network_started)
    {
        network_connected = app_network_reconnect();
        if (!network_connected)
        {
            ESP_LOGE(TAG, "Failed to reconnect; continuing offline when saved runtime config is available.");
        }
    }
    if (!network_connected)
    {
        Serial.println("Network is unavailable in this wake cycle.");
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP, APP_DEBUG_LOG_ERROR, APP_DEBUG_EVENT_NETWORK_UNAVAILABLE, 0, 0);
    }
    else
    {
        app_network_loop();
    }

    app_runtime_config_mark_waiting();
    const bool config_requested = network_connected && app_network_request_runtime_config();
    const bool config_received = config_requested && app_network_wait_for_runtime_config(APP_CONFIG_FETCH_TIMEOUT_MS);
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                        config_received ? APP_DEBUG_LOG_INFO : APP_DEBUG_LOG_WARNING,
                        APP_DEBUG_EVENT_RUNTIME_CONFIG_REQUEST,
                        config_requested ? 1 : 0,
                        config_received ? 1 : 0);
    if (!config_received)
    {
        Serial.println("Runtime config was not received; using saved/default configuration");
    }

    const app_runtime_config_t &runtime_config = app_runtime_config_get();
    app_watering_set_threshold(runtime_config.moisture_threshold);
    Serial.printf("Runtime config in app loop: threshold=%u force_watering=%s debug_log_on_wake=%s\n",
                  runtime_config.moisture_threshold,
                  runtime_config.force_watering ? "true" : "false",
                  runtime_config.debug_log_on_wake ? "true" : "false");
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                        APP_DEBUG_LOG_INFO,
                        APP_DEBUG_EVENT_RUNTIME_CONFIG_ACTIVE,
                        app_pack_runtime_flags(runtime_config.moisture_threshold,
                                               runtime_config.force_watering,
                                               runtime_config.debug_log_on_wake,
                                               runtime_config.schedule_count),
                        0);

    bool time_synced = false;
    if (network_connected)
    {
        time_synced = app_time_sync_with_ntp(runtime_config.ntp_server,
                                             runtime_config.timezone_offset_sec,
                                             APP_NTP_SYNC_TIMEOUT_MS);
        if (!time_synced && woke_from_deep_sleep && app_time_is_synchronized())
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
    else if (woke_from_deep_sleep && app_time_is_synchronized())
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
                            woke_from_deep_sleep ? 1 : 0,
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

    time_t now_utc = time(nullptr);
    app_schedule_entry_t due_schedule = {};
    time_t due_schedule_epoch_utc = 0;
    const bool watering_due = time_synced &&
                              app_runtime_config_find_due_schedule(now_utc,
                                                                   s_last_executed_schedule_utc,
                                                                   &due_schedule,
                                                                   &due_schedule_epoch_utc);
    Serial.printf("Schedule check: now=%ld last_executed=%ld due=%s runtime_valid=%s\n",
                  static_cast<long>(now_utc),
                  static_cast<long>(s_last_executed_schedule_utc),
                  watering_due ? "true" : "false",
                  app_runtime_config_is_valid() ? "true" : "false");
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                        watering_due ? APP_DEBUG_LOG_INFO : APP_DEBUG_LOG_WARNING,
                        APP_DEBUG_EVENT_SCHEDULE_CHECK,
                        (watering_due ? 1 : 0) | (app_runtime_config_is_valid() ? (1 << 1) : 0),
                        static_cast<int32_t>(s_last_executed_schedule_utc));

    bool watering_started = false;
    uint8_t last_soil_moisture = app_watering_get_last_soil_moisture();

    if (watering_due)
    {
        Serial.printf("Watering schedule due at %ld, mask=0x%lx, duration=%u\n",
                      static_cast<long>(due_schedule_epoch_utc),
                      static_cast<unsigned long>(due_schedule.channel_mask),
                      due_schedule.duration_sec);
        Serial.printf("Watering threshold before decision: %u%% force_watering=%s\n",
                      app_watering_get_threshold(),
                      runtime_config.force_watering ? "true" : "false");

        watering_started = app_watering_start_async(due_schedule.duration_sec,
                                                    due_schedule.channel_mask,
                                                    runtime_config.force_watering);
        last_soil_moisture = app_watering_get_last_soil_moisture();
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                            watering_started ? APP_DEBUG_LOG_INFO : APP_DEBUG_LOG_WARNING,
                            APP_DEBUG_EVENT_WATERING_DUE_RESULT,
                            static_cast<int32_t>(due_schedule.duration_sec) | (watering_started ? (1L << 16) : 0),
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
    uint32_t sleep_sec = (time_synced && app_runtime_config_is_valid())
                             ? app_runtime_config_seconds_until_next_schedule(now_utc)
                             : APP_NETWORK_RETRY_SLEEP_SEC;
    if (sleep_sec < APP_MIN_SLEEP_SEC)
    {
        sleep_sec = APP_MIN_SLEEP_SEC;
    }
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                        APP_DEBUG_LOG_INFO,
                        APP_DEBUG_EVENT_SLEEP_PLANNED,
                        static_cast<int32_t>(sleep_sec),
                        0);

    bool status_sent = false;
    if (network_connected)
    {
        status_sent = app_publish_status(seqId,
                                         config_received,
                                         time_synced,
                                         watering_due,
                                         watering_started,
                                         watering_due ? due_schedule.duration_sec : 0,
                                         watering_due ? due_schedule.channel_mask : 0,
                                         due_schedule_epoch_utc,
                                         sleep_sec,
                                         last_soil_moisture,
                                         runtime_config.force_watering,
                                         runtime_config.debug_log_on_wake,
                                         network_connected,
                                         app_runtime_config_is_valid());
    }
    if (network_connected && !status_sent)
    {
        Serial.println("Failed to send status");
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP, APP_DEBUG_LOG_ERROR, APP_DEBUG_EVENT_STATUS_FAILED, 0, 0);
    }
    else if (!network_connected)
    {
        Serial.println("Skip status publish because network is unavailable");
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP, APP_DEBUG_LOG_WARNING, APP_DEBUG_EVENT_STATUS_SKIPPED, 0, 0);
    }

    if (network_connected && app_runtime_config_is_valid() && runtime_config.debug_log_on_wake)
    {
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_APP,
                            APP_DEBUG_LOG_INFO,
                            APP_DEBUG_EVENT_DEBUG_LOG_PUBLISH_ENABLED,
                            status_sent ? 1 : 0,
                            static_cast<int32_t>(sleep_sec));
        if (app_debug_log_publish(seqId))
        {
            app_network_flush(APP_DEBUG_LOG_PUBLISH_DRAIN_MS);
        }
        else
        {
            Serial.println("Failed to send debug log");
        }
    }

    app_network_stop();
    Serial.printf("Sleep %lu sec\n", static_cast<unsigned long>(sleep_sec));
    Serial.flush();
    esp_sleep_enable_timer_wakeup(static_cast<uint64_t>(sleep_sec) * 1000000ULL);
    esp_deep_sleep_start();
}

void core0_loop(void *arg)
{
    while (1)
    {
        delay(1);
    }
}
