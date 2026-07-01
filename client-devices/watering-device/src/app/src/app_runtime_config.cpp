#include "app_runtime_config.h"

#include <ArduinoJson.h>
#include <LittleFS.h>
#include <string.h>

#include "app_config.h"
#include "app_debug_log.h"
#include "app_utils.h"

#define TAG "app_runtime_config"
#define APP_RUNTIME_CONFIG_FILE "/.runtime_config"
#define APP_RUNTIME_CONFIG_STORE_MAGIC 0x52544346UL
#define APP_RUNTIME_CONFIG_STORE_VERSION 1

static app_runtime_config_t s_runtime_config;

typedef struct
{
    uint32_t magic;
    uint16_t version;
    uint16_t config_size;
    app_runtime_config_t config;
    uint32_t crc32;
} app_runtime_config_store_t;

static time_t app_runtime_config_local_day_start(time_t now_utc, int32_t timezone_offset_sec)
{
    const time_t local_now = now_utc + timezone_offset_sec;
    return (local_now / 86400) * 86400;
}

static time_t app_runtime_config_schedule_epoch_utc(const app_schedule_entry_t &schedule, time_t local_day_start, int32_t timezone_offset_sec)
{
    const time_t local_schedule_epoch = local_day_start + (schedule.hour * 3600) + (schedule.minute * 60);
    return local_schedule_epoch - timezone_offset_sec;
}

static int32_t app_runtime_config_pack_flags(const app_runtime_config_t &config)
{
    return static_cast<int32_t>(config.moisture_threshold) |
           (config.force_watering ? (1L << 8) : 0) |
           (config.debug_log_on_wake ? (1L << 9) : 0) |
           (static_cast<int32_t>(config.schedule_count) << 16);
}

static void app_runtime_config_print_schedules(const app_runtime_config_t &config)
{
    Serial.printf("Runtime schedules: count=%u debug_log_on_wake=%s\n",
                  config.schedule_count,
                  config.debug_log_on_wake ? "true" : "false");
    for (uint8_t i = 0; i < config.schedule_count; i++)
    {
        const app_schedule_entry_t &schedule = config.schedules[i];
        Serial.printf("  schedule[%u]: %02u:%02u duration=%u sec channel_mask=0x%lx\n",
                      static_cast<unsigned int>(i),
                      static_cast<unsigned int>(schedule.hour),
                      static_cast<unsigned int>(schedule.minute),
                      static_cast<unsigned int>(schedule.duration_sec),
                      static_cast<unsigned long>(schedule.channel_mask));
    }
}

void app_runtime_config_init()
{
    memset(&s_runtime_config, 0, sizeof(s_runtime_config));
    strncpy(s_runtime_config.ntp_server, appConfig.mqtt_broker, sizeof(s_runtime_config.ntp_server) - 1);
    s_runtime_config.timezone_offset_sec = 0;
    s_runtime_config.moisture_threshold = 40;
    s_runtime_config.force_watering = false;
    s_runtime_config.debug_log_on_wake = false;

    if (app_runtime_config_load_saved())
    {
        Serial.printf("Loaded saved runtime config: ntp=%s tz=%ld threshold=%u force_watering=%s schedules=%u\n",
                      s_runtime_config.ntp_server,
                      static_cast<long>(s_runtime_config.timezone_offset_sec),
                      s_runtime_config.moisture_threshold,
                      s_runtime_config.force_watering ? "true" : "false",
                      s_runtime_config.schedule_count);
        app_runtime_config_print_schedules(s_runtime_config);
    }
}

void app_runtime_config_mark_waiting()
{
    s_runtime_config.received_from_mqtt = false;
}

bool app_runtime_config_apply_json(const uint8_t *payload, size_t length)
{
    if (payload == nullptr || length == 0)
    {
        return false;
    }

    JsonDocument doc;
    const DeserializationError error = deserializeJson(doc, payload, length);
    if (error)
    {
        Serial.printf("Failed to parse runtime config JSON: %s\n", error.c_str());
        return false;
    }

    if (!doc["schedules"].is<JsonArrayConst>())
    {
        Serial.println("Runtime config must include schedules array");
        return false;
    }

    app_runtime_config_t next = s_runtime_config;
    memset(next.schedules, 0, sizeof(next.schedules));
    next.schedule_count = 0;

    const char *ntp_server = doc["ntp_server"] | appConfig.mqtt_broker;
    strncpy(next.ntp_server, ntp_server, sizeof(next.ntp_server) - 1);
    next.ntp_server[sizeof(next.ntp_server) - 1] = '\0';

    next.timezone_offset_sec = doc["timezone_offset_sec"] | 0;

    int threshold = doc["moisture_threshold"] | next.moisture_threshold;
    threshold = constrain(threshold, 0, 100);
    next.moisture_threshold = static_cast<uint8_t>(threshold);
    next.force_watering = doc["force_watering"] | false;
    next.debug_log_on_wake = doc["debug_log_on_wake"] | (doc["debug_log_enabled"] | false);

    const JsonArrayConst schedules = doc["schedules"].as<JsonArrayConst>();
    for (JsonObjectConst schedule_json : schedules)
    {
        if (next.schedule_count >= APP_RUNTIME_MAX_SCHEDULES)
        {
            break;
        }

        const int hour = schedule_json["hour"] | -1;
        const int minute = schedule_json["minute"] | -1;
        const int duration_sec = schedule_json["duration_sec"] | 0;
        const uint32_t channel_mask = schedule_json["channel_mask"] | 0;

        if (hour < 0 || hour > 23 || minute < 0 || minute > 59 || duration_sec <= 0 || channel_mask == 0)
        {
            Serial.println("Ignoring invalid schedule entry");
            continue;
        }

        app_schedule_entry_t &schedule = next.schedules[next.schedule_count++];
        schedule.hour = static_cast<uint8_t>(hour);
        schedule.minute = static_cast<uint8_t>(minute);
        schedule.duration_sec = static_cast<uint16_t>(duration_sec);
        schedule.channel_mask = channel_mask;
    }

    if (next.schedule_count == 0)
    {
        Serial.println("Runtime config contains no valid schedules");
        return false;
    }

    next.valid = true;
    next.received_from_mqtt = true;
    s_runtime_config = next;

    app_runtime_config_save_current();

    Serial.printf("Runtime config updated: ntp=%s tz=%ld threshold=%u force_watering=%s schedules=%u\n",
                  s_runtime_config.ntp_server,
                  static_cast<long>(s_runtime_config.timezone_offset_sec),
                  s_runtime_config.moisture_threshold,
                  s_runtime_config.force_watering ? "true" : "false",
                  s_runtime_config.schedule_count);
    app_runtime_config_print_schedules(s_runtime_config);
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_RUNTIME_CONFIG,
                        APP_DEBUG_LOG_INFO,
                        APP_DEBUG_EVENT_RUNTIME_CONFIG_UPDATED,
                        app_runtime_config_pack_flags(s_runtime_config),
                        static_cast<int32_t>(s_runtime_config.timezone_offset_sec));

    return true;
}

bool app_runtime_config_load_saved()
{
    if (!LittleFS.exists(APP_RUNTIME_CONFIG_FILE))
    {
        Serial.println("Saved runtime config does not exist");
        return false;
    }

    File file = LittleFS.open(APP_RUNTIME_CONFIG_FILE, "r");
    if (!file)
    {
        Serial.println("Failed to open saved runtime config");
        return false;
    }

    app_runtime_config_store_t store = {};
    const size_t read_size = file.read(reinterpret_cast<uint8_t *>(&store), sizeof(store));
    file.close();

    if (read_size != sizeof(store))
    {
        Serial.printf("Saved runtime config size mismatch: %u/%u\n",
                      static_cast<unsigned int>(read_size),
                      static_cast<unsigned int>(sizeof(store)));
        return false;
    }

    if (store.magic != APP_RUNTIME_CONFIG_STORE_MAGIC ||
        store.version != APP_RUNTIME_CONFIG_STORE_VERSION ||
        store.config_size != sizeof(app_runtime_config_t))
    {
        Serial.println("Saved runtime config header is invalid");
        return false;
    }

    const uint32_t expected_crc32 = AppUtils::crc32(reinterpret_cast<const uint8_t *>(&store),
                                                   sizeof(store) - sizeof(store.crc32));
    if (store.crc32 != expected_crc32)
    {
        Serial.printf("Saved runtime config CRC mismatch actual=0x%08X expected=0x%08X\n",
                      store.crc32,
                      expected_crc32);
        return false;
    }

    if (!store.config.valid || store.config.schedule_count == 0 || store.config.schedule_count > APP_RUNTIME_MAX_SCHEDULES)
    {
        Serial.println("Saved runtime config content is invalid");
        return false;
    }

    store.config.received_from_mqtt = false;
    s_runtime_config = store.config;
    return true;
}

bool app_runtime_config_save_current()
{
    if (!s_runtime_config.valid || s_runtime_config.schedule_count == 0)
    {
        Serial.println("Skip saving invalid runtime config");
        return false;
    }

    app_runtime_config_store_t store = {};
    store.magic = APP_RUNTIME_CONFIG_STORE_MAGIC;
    store.version = APP_RUNTIME_CONFIG_STORE_VERSION;
    store.config_size = sizeof(app_runtime_config_t);
    store.config = s_runtime_config;
    store.config.received_from_mqtt = false;
    store.crc32 = AppUtils::crc32(reinterpret_cast<const uint8_t *>(&store),
                                  sizeof(store) - sizeof(store.crc32));

    File file = LittleFS.open(APP_RUNTIME_CONFIG_FILE, "w");
    if (!file)
    {
        Serial.println("Failed to open runtime config for save");
        return false;
    }

    const size_t write_size = file.write(reinterpret_cast<const uint8_t *>(&store), sizeof(store));
    file.close();

    if (write_size != sizeof(store))
    {
        Serial.printf("Failed to save runtime config: %u/%u\n",
                      static_cast<unsigned int>(write_size),
                      static_cast<unsigned int>(sizeof(store)));
        return false;
    }

    Serial.println("Saved runtime config to LittleFS");
    return true;
}

bool app_runtime_config_is_valid()
{
    return s_runtime_config.valid;
}

bool app_runtime_config_is_received()
{
    return s_runtime_config.received_from_mqtt;
}

const app_runtime_config_t &app_runtime_config_get()
{
    return s_runtime_config;
}

bool app_runtime_config_find_due_schedule(time_t now_utc,
                                          time_t last_executed_schedule_utc,
                                          app_schedule_entry_t *schedule_out,
                                          time_t *schedule_epoch_utc_out)
{
    if (!s_runtime_config.valid || schedule_out == nullptr || schedule_epoch_utc_out == nullptr)
    {
        return false;
    }

    const time_t local_day_start = app_runtime_config_local_day_start(now_utc, s_runtime_config.timezone_offset_sec);
    bool found = false;
    time_t selected_epoch = 0;
    app_schedule_entry_t selected_schedule = {};

    for (uint8_t i = 0; i < s_runtime_config.schedule_count; i++)
    {
        const app_schedule_entry_t &candidate = s_runtime_config.schedules[i];
        const time_t candidate_epoch = app_runtime_config_schedule_epoch_utc(candidate, local_day_start, s_runtime_config.timezone_offset_sec);
        if (candidate_epoch > now_utc)
        {
            continue;
        }
        if (candidate_epoch <= last_executed_schedule_utc)
        {
            continue;
        }
        if (!found || candidate_epoch > selected_epoch)
        {
            found = true;
            selected_epoch = candidate_epoch;
            selected_schedule = candidate;
        }
    }

    if (!found)
    {
        return false;
    }

    *schedule_out = selected_schedule;
    *schedule_epoch_utc_out = selected_epoch;
    return true;
}

uint32_t app_runtime_config_seconds_until_next_schedule(time_t now_utc)
{
    if (!s_runtime_config.valid)
    {
        return 60;
    }

    const time_t local_day_start = app_runtime_config_local_day_start(now_utc, s_runtime_config.timezone_offset_sec);
    time_t next_epoch = 0;
    bool found = false;

    for (uint8_t day_offset = 0; day_offset < 2; day_offset++)
    {
        const time_t candidate_day_start = local_day_start + (static_cast<time_t>(day_offset) * 86400);
        for (uint8_t i = 0; i < s_runtime_config.schedule_count; i++)
        {
            const time_t candidate_epoch = app_runtime_config_schedule_epoch_utc(s_runtime_config.schedules[i], candidate_day_start, s_runtime_config.timezone_offset_sec);
            if (candidate_epoch <= now_utc)
            {
                continue;
            }
            if (!found || candidate_epoch < next_epoch)
            {
                found = true;
                next_epoch = candidate_epoch;
            }
        }
        if (found)
        {
            break;
        }
    }

    if (!found)
    {
        return 60;
    }

    return static_cast<uint32_t>(next_epoch - now_utc);
}
