#include "app_runtime_config.h"

#include <ArduinoJson.h>
#include <LittleFS.h>
#include <stdio.h>
#include <string.h>

#include "app_config.h"
#include "app_debug_log.h"
#include "app_utils.h"

#define TAG "app_runtime_config"
#define APP_RUNTIME_CONFIG_FILE "/.runtime_config"
#define APP_RUNTIME_CONFIG_STORE_MAGIC 0x52544346UL
#define APP_RUNTIME_CONFIG_STORE_VERSION 4
#define APP_RUNTIME_CONFIG_STORE_VERSION_V3 3
#define APP_RUNTIME_CONFIG_STORE_VERSION_V2 2
#define APP_RUNTIME_CONFIG_STORE_VERSION_V1 1

static app_runtime_config_t s_runtime_config;

typedef struct
{
    uint8_t hour;
    uint8_t minute;
    uint16_t duration_sec;
    uint32_t channel_mask;
} app_schedule_entry_v1_t;

typedef struct
{
    bool valid;
    bool received_from_mqtt;
    char ntp_server[256];
    int32_t timezone_offset_sec;
    uint8_t moisture_threshold;
    bool force_watering;
    uint8_t schedule_count;
    bool debug_log_on_wake;
    app_schedule_entry_v1_t schedules[APP_RUNTIME_MAX_SCHEDULES];
} app_runtime_config_v1_t;

typedef struct
{
    bool valid;
    bool received_from_mqtt;
    char ntp_server[256];
    int32_t timezone_offset_sec;
    uint8_t moisture_threshold;
    bool force_watering;
    uint8_t schedule_count;
    bool debug_log_on_wake;
    uint32_t ota_check_interval_sec;
    app_schedule_entry_v1_t schedules[APP_RUNTIME_MAX_SCHEDULES];
} app_runtime_config_v2_t;


typedef struct
{
    bool valid;
    bool received_from_mqtt;
    char ntp_server[256];
    int32_t timezone_offset_sec;
    uint8_t moisture_threshold;
    bool force_watering;
    uint8_t schedule_count;
    bool debug_log_on_wake;
    uint32_t ota_check_interval_sec;
    app_watering_pattern_config_t watering_pattern;
    app_soil_calibration_config_t soil_calibration;
    app_schedule_entry_v1_t schedules[APP_RUNTIME_MAX_SCHEDULES];
} app_runtime_config_v3_t;

typedef struct
{
    uint32_t magic;
    uint16_t version;
    uint16_t config_size;
    app_runtime_config_t config;
    uint32_t crc32;
} app_runtime_config_store_t;

typedef struct
{
    uint32_t magic;
    uint16_t version;
    uint16_t config_size;
    app_runtime_config_v1_t config;
    uint32_t crc32;
} app_runtime_config_store_v1_t;

typedef struct
{
    uint32_t magic;
    uint16_t version;
    uint16_t config_size;
    app_runtime_config_v2_t config;
    uint32_t crc32;
} app_runtime_config_store_v2_t;

typedef struct
{
    uint32_t magic;
    uint16_t version;
    uint16_t config_size;
    app_runtime_config_v3_t config;
    uint32_t crc32;
} app_runtime_config_store_v3_t;

static_assert(offsetof(app_runtime_config_v1_t, schedules) == 268,
              "Unexpected app_runtime_config_v1_t layout; check migration");
static_assert(offsetof(app_runtime_config_v2_t, schedules) == 272,
              "Unexpected app_runtime_config_v2_t layout; check migration");
static_assert(offsetof(app_runtime_config_v3_t, schedules) > offsetof(app_runtime_config_v3_t, ota_check_interval_sec),
              "Unexpected app_runtime_config_v3_t layout; check migration");

static app_watering_pattern_config_t app_runtime_config_default_watering_pattern()
{
    app_watering_pattern_config_t pattern = {};
    pattern.enabled = false;
    pattern.on_sec = 0;
    pattern.off_sec = 0;
    pattern.repeat_count = 0;
    return pattern;
}

static app_soil_calibration_config_t app_runtime_config_default_soil_calibration()
{
    app_soil_calibration_config_t calibration = {};
    calibration.auto_mode_enabled = false;
    calibration.apply_auto_calibration = false;
    calibration.drift_check_enabled = false;
    calibration.dry_raw = 1895;
    calibration.wet_raw = 1285;
    calibration.min_delta_raw = 80;
    calibration.drift_tolerance_raw = 120;
    return calibration;
}

static uint32_t app_runtime_config_sanitize_ota_check_interval(uint32_t interval_sec)
{
    if (interval_sec < APP_RUNTIME_MIN_OTA_CHECK_INTERVAL_SEC)
    {
        return APP_RUNTIME_MIN_OTA_CHECK_INTERVAL_SEC;
    }
    if (interval_sec > APP_RUNTIME_MAX_OTA_CHECK_INTERVAL_SEC)
    {
        return APP_RUNTIME_MAX_OTA_CHECK_INTERVAL_SEC;
    }
    return interval_sec;
}

static bool app_runtime_config_content_is_valid(const app_runtime_config_t &config)
{
    return config.valid &&
           config.schedule_count > 0 &&
           config.schedule_count <= APP_RUNTIME_MAX_SCHEDULES &&
           config.ota_check_interval_sec >= APP_RUNTIME_MIN_OTA_CHECK_INTERVAL_SEC &&
           config.ota_check_interval_sec <= APP_RUNTIME_MAX_OTA_CHECK_INTERVAL_SEC &&
           config.soil_calibration.dry_raw > config.soil_calibration.wet_raw;
}

static app_schedule_entry_t app_runtime_config_daily_schedule_from_legacy(const app_schedule_entry_v1_t &legacy)
{
    app_schedule_entry_t current = {};
    current.hour = legacy.hour;
    current.minute = legacy.minute;
    current.duration_sec = legacy.duration_sec;
    current.channel_mask = legacy.channel_mask;
    current.frequency_type = APP_SCHEDULE_FREQUENCY_DAILY;
    current.interval_days = 1;
    current.weekdays_mask = 0;
    current.anchor_epoch_day = 0;
    return current;
}

static app_schedule_entry_t app_runtime_config_sanitize_schedule_frequency(app_schedule_entry_t schedule)
{
    if (schedule.frequency_type == APP_SCHEDULE_FREQUENCY_INTERVAL)
    {
        if (schedule.interval_days < 1)
        {
            schedule.interval_days = 1;
        }
        schedule.weekdays_mask = 0;
        return schedule;
    }
    if (schedule.frequency_type == APP_SCHEDULE_FREQUENCY_WEEKDAYS)
    {
        if (schedule.weekdays_mask == 0)
        {
            schedule.frequency_type = APP_SCHEDULE_FREQUENCY_DAILY;
            schedule.interval_days = 1;
        }
        return schedule;
    }
    schedule.frequency_type = APP_SCHEDULE_FREQUENCY_DAILY;
    schedule.interval_days = 1;
    schedule.weekdays_mask = 0;
    schedule.anchor_epoch_day = 0;
    return schedule;
}

static void app_runtime_config_copy_legacy_schedules(app_schedule_entry_t *dest, const app_schedule_entry_v1_t *src)
{
    for (uint8_t i = 0; i < APP_RUNTIME_MAX_SCHEDULES; i++)
    {
        dest[i] = app_runtime_config_daily_schedule_from_legacy(src[i]);
    }
}

static app_runtime_config_t app_runtime_config_from_v2(const app_runtime_config_v2_t &legacy)
{
    app_runtime_config_t current = {};
    current.valid = legacy.valid;
    current.received_from_mqtt = legacy.received_from_mqtt;
    strncpy(current.ntp_server, legacy.ntp_server, sizeof(current.ntp_server) - 1);
    current.ntp_server[sizeof(current.ntp_server) - 1] = '\0';
    current.timezone_offset_sec = legacy.timezone_offset_sec;
    current.moisture_threshold = legacy.moisture_threshold;
    current.force_watering = legacy.force_watering;
    current.schedule_count = legacy.schedule_count;
    current.debug_log_on_wake = legacy.debug_log_on_wake;
    current.ota_check_interval_sec = app_runtime_config_sanitize_ota_check_interval(legacy.ota_check_interval_sec);
    current.watering_pattern = app_runtime_config_default_watering_pattern();
    current.soil_calibration = app_runtime_config_default_soil_calibration();
    app_runtime_config_copy_legacy_schedules(current.schedules, legacy.schedules);
    return current;
}

static app_runtime_config_t app_runtime_config_from_v3(const app_runtime_config_v3_t &legacy)
{
    app_runtime_config_t current = {};
    current.valid = legacy.valid;
    current.received_from_mqtt = legacy.received_from_mqtt;
    strncpy(current.ntp_server, legacy.ntp_server, sizeof(current.ntp_server) - 1);
    current.ntp_server[sizeof(current.ntp_server) - 1] = '\0';
    current.timezone_offset_sec = legacy.timezone_offset_sec;
    current.moisture_threshold = legacy.moisture_threshold;
    current.force_watering = legacy.force_watering;
    current.schedule_count = legacy.schedule_count;
    current.debug_log_on_wake = legacy.debug_log_on_wake;
    current.ota_check_interval_sec = app_runtime_config_sanitize_ota_check_interval(legacy.ota_check_interval_sec);
    current.watering_pattern = legacy.watering_pattern;
    current.soil_calibration = legacy.soil_calibration;
    app_runtime_config_copy_legacy_schedules(current.schedules, legacy.schedules);
    return current;
}

static app_runtime_config_t app_runtime_config_from_v1(const app_runtime_config_v1_t &legacy)
{
    app_runtime_config_v2_t v2 = {};
    v2.valid = legacy.valid;
    v2.received_from_mqtt = legacy.received_from_mqtt;
    strncpy(v2.ntp_server, legacy.ntp_server, sizeof(v2.ntp_server) - 1);
    v2.ntp_server[sizeof(v2.ntp_server) - 1] = '\0';
    v2.timezone_offset_sec = legacy.timezone_offset_sec;
    v2.moisture_threshold = legacy.moisture_threshold;
    v2.force_watering = legacy.force_watering;
    v2.schedule_count = legacy.schedule_count;
    v2.debug_log_on_wake = legacy.debug_log_on_wake;
    v2.ota_check_interval_sec = APP_RUNTIME_DEFAULT_OTA_CHECK_INTERVAL_SEC;
    memcpy(v2.schedules, legacy.schedules, sizeof(v2.schedules));
    return app_runtime_config_from_v2(v2);
}

static time_t app_runtime_config_local_day_start(time_t now_utc, int32_t timezone_offset_sec)
{
    const time_t local_now = now_utc + timezone_offset_sec;
    return (local_now / 86400) * 86400;
}

static int32_t app_runtime_config_days_from_civil(int year, unsigned month, unsigned day)
{
    year -= month <= 2;
    const int era = (year >= 0 ? year : year - 399) / 400;
    const unsigned yoe = static_cast<unsigned>(year - era * 400);
    const unsigned doy = (153 * (month + (month > 2 ? -3 : 9)) + 2) / 5 + day - 1;
    const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097 + static_cast<int>(doe) - 719468;
}

static int32_t app_runtime_config_parse_date_epoch_day(const char *date)
{
    if (date == nullptr)
    {
        return 0;
    }
    int year = 0;
    int month = 0;
    int day = 0;
    if (sscanf(date, "%d-%d-%d", &year, &month, &day) != 3 ||
        year < 1970 || month < 1 || month > 12 || day < 1 || day > 31)
    {
        return 0;
    }
    return app_runtime_config_days_from_civil(year, static_cast<unsigned>(month), static_cast<unsigned>(day));
}

static int32_t app_runtime_config_local_epoch_day(time_t local_day_start)
{
    return static_cast<int32_t>(local_day_start / 86400);
}

static uint8_t app_runtime_config_weekday_from_epoch_day(int32_t epoch_day)
{
    int32_t weekday = (epoch_day + 4) % 7;
    if (weekday < 0)
    {
        weekday += 7;
    }
    return static_cast<uint8_t>(weekday);
}

static bool app_runtime_config_schedule_matches_day(const app_schedule_entry_t &schedule, int32_t local_epoch_day)
{
    if (schedule.frequency_type == APP_SCHEDULE_FREQUENCY_INTERVAL)
    {
        const uint8_t interval_days = schedule.interval_days == 0 ? 1 : schedule.interval_days;
        const int32_t elapsed_days = local_epoch_day - schedule.anchor_epoch_day;
        return elapsed_days >= 0 && elapsed_days % interval_days == 0;
    }
    if (schedule.frequency_type == APP_SCHEDULE_FREQUENCY_WEEKDAYS)
    {
        const uint8_t weekday = app_runtime_config_weekday_from_epoch_day(local_epoch_day);
        return (schedule.weekdays_mask & (1U << weekday)) != 0;
    }
    return true;
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
    Serial.printf("Runtime schedules: count=%u debug_log_on_wake=%s ota_check_interval_sec=%lu\n",
                  config.schedule_count,
                  config.debug_log_on_wake ? "true" : "false",
                  static_cast<unsigned long>(config.ota_check_interval_sec));
    for (uint8_t i = 0; i < config.schedule_count; i++)
    {
        const app_schedule_entry_t &schedule = config.schedules[i];
        Serial.printf("  schedule[%u]: %02u:%02u duration=%u sec channel_mask=0x%lx frequency=%u interval_days=%u weekdays_mask=0x%02x anchor_day=%ld\n",
                      static_cast<unsigned int>(i),
                      static_cast<unsigned int>(schedule.hour),
                      static_cast<unsigned int>(schedule.minute),
                      static_cast<unsigned int>(schedule.duration_sec),
                      static_cast<unsigned long>(schedule.channel_mask),
                      static_cast<unsigned int>(schedule.frequency_type),
                      static_cast<unsigned int>(schedule.interval_days),
                      static_cast<unsigned int>(schedule.weekdays_mask),
                      static_cast<long>(schedule.anchor_epoch_day));
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
    s_runtime_config.ota_check_interval_sec = APP_RUNTIME_DEFAULT_OTA_CHECK_INTERVAL_SEC;
    s_runtime_config.watering_pattern = app_runtime_config_default_watering_pattern();
    s_runtime_config.soil_calibration = app_runtime_config_default_soil_calibration();

    if (app_runtime_config_load_saved())
    {
        Serial.printf("Loaded saved runtime config: ntp=%s tz=%ld threshold=%u force_watering=%s ota_check_interval_sec=%lu schedules=%u\n",
                      s_runtime_config.ntp_server,
                      static_cast<long>(s_runtime_config.timezone_offset_sec),
                      s_runtime_config.moisture_threshold,
                      s_runtime_config.force_watering ? "true" : "false",
                      static_cast<unsigned long>(s_runtime_config.ota_check_interval_sec),
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
    long ota_check_interval_sec = doc["ota_check_interval_sec"] | static_cast<long>(next.ota_check_interval_sec);
    if (ota_check_interval_sec < 0)
    {
        ota_check_interval_sec = 0;
    }
    next.ota_check_interval_sec = app_runtime_config_sanitize_ota_check_interval(static_cast<uint32_t>(ota_check_interval_sec));

    next.watering_pattern = app_runtime_config_default_watering_pattern();
    if (doc["watering_pattern"].is<JsonObjectConst>())
    {
        JsonObjectConst pattern_json = doc["watering_pattern"].as<JsonObjectConst>();
        next.watering_pattern.enabled = pattern_json["enabled"] | false;
        int on_sec = pattern_json["on_sec"] | 0;
        int off_sec = pattern_json["off_sec"] | 0;
        int repeat_count = pattern_json["repeat_count"] | 0;
        next.watering_pattern.on_sec = static_cast<uint16_t>(constrain(on_sec, 0, 3600));
        next.watering_pattern.off_sec = static_cast<uint16_t>(constrain(off_sec, 0, 3600));
        next.watering_pattern.repeat_count = static_cast<uint8_t>(constrain(repeat_count, 0, 20));
        if (next.watering_pattern.enabled &&
            (next.watering_pattern.on_sec == 0 || next.watering_pattern.repeat_count == 0))
        {
            Serial.println("Ignoring invalid watering_pattern");
            next.watering_pattern = app_runtime_config_default_watering_pattern();
        }
    }

    next.soil_calibration = app_runtime_config_default_soil_calibration();
    if (doc["soil_calibration"].is<JsonObjectConst>())
    {
        JsonObjectConst calibration_json = doc["soil_calibration"].as<JsonObjectConst>();
        next.soil_calibration.auto_mode_enabled = calibration_json["auto_mode_enabled"] | false;
        next.soil_calibration.apply_auto_calibration = calibration_json["apply_auto_calibration"] | false;
        next.soil_calibration.drift_check_enabled = calibration_json["drift_check_enabled"] | false;
        int dry_raw = calibration_json["dry_raw"] | next.soil_calibration.dry_raw;
        int wet_raw = calibration_json["wet_raw"] | next.soil_calibration.wet_raw;
        int min_delta_raw = calibration_json["min_delta_raw"] | next.soil_calibration.min_delta_raw;
        int drift_tolerance_raw = calibration_json["drift_tolerance_raw"] | next.soil_calibration.drift_tolerance_raw;
        next.soil_calibration.dry_raw = static_cast<uint16_t>(constrain(dry_raw, 1, 4095));
        next.soil_calibration.wet_raw = static_cast<uint16_t>(constrain(wet_raw, 0, 4094));
        next.soil_calibration.min_delta_raw = static_cast<uint16_t>(constrain(min_delta_raw, 10, 2000));
        next.soil_calibration.drift_tolerance_raw = static_cast<uint16_t>(constrain(drift_tolerance_raw, 10, 2000));
        if (next.soil_calibration.dry_raw <= next.soil_calibration.wet_raw)
        {
            Serial.println("Ignoring invalid soil_calibration dry/wet raw values");
            next.soil_calibration = app_runtime_config_default_soil_calibration();
        }
    }

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

        app_schedule_entry_t schedule = {};
        schedule.hour = static_cast<uint8_t>(hour);
        schedule.minute = static_cast<uint8_t>(minute);
        schedule.duration_sec = static_cast<uint16_t>(duration_sec);
        schedule.channel_mask = channel_mask;
        schedule.frequency_type = APP_SCHEDULE_FREQUENCY_DAILY;
        schedule.interval_days = 1;
        schedule.weekdays_mask = 0;
        schedule.anchor_epoch_day = 0;

        if (schedule_json["frequency"].is<JsonObjectConst>())
        {
            JsonObjectConst frequency_json = schedule_json["frequency"].as<JsonObjectConst>();
            const char *mode = frequency_json["mode"] | "daily";
            if (strcmp(mode, "interval") == 0)
            {
                int interval_days = frequency_json["interval_days"] | 1;
                schedule.frequency_type = APP_SCHEDULE_FREQUENCY_INTERVAL;
                schedule.interval_days = static_cast<uint8_t>(constrain(interval_days, 1, 31));
                schedule.anchor_epoch_day = app_runtime_config_parse_date_epoch_day(frequency_json["start_date"] | nullptr);
            }
            else if (strcmp(mode, "weekdays") == 0)
            {
                schedule.frequency_type = APP_SCHEDULE_FREQUENCY_WEEKDAYS;
                int weekdays_mask = frequency_json["weekdays_mask"] | 0;
                if (frequency_json["weekdays"].is<JsonArrayConst>())
                {
                    weekdays_mask = 0;
                    for (JsonVariantConst weekday_json : frequency_json["weekdays"].as<JsonArrayConst>())
                    {
                        const int weekday = weekday_json.as<int>();
                        if (weekday >= 0 && weekday <= 6)
                        {
                            weekdays_mask |= (1 << weekday);
                        }
                    }
                }
                schedule.weekdays_mask = static_cast<uint8_t>(weekdays_mask & 0x7F);
            }
        }

        next.schedules[next.schedule_count++] = app_runtime_config_sanitize_schedule_frequency(schedule);
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

    Serial.printf("Runtime config updated: ntp=%s tz=%ld threshold=%u force_watering=%s ota_check_interval_sec=%lu schedules=%u\n",
                  s_runtime_config.ntp_server,
                  static_cast<long>(s_runtime_config.timezone_offset_sec),
                  s_runtime_config.moisture_threshold,
                  s_runtime_config.force_watering ? "true" : "false",
                  static_cast<unsigned long>(s_runtime_config.ota_check_interval_sec),
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

    struct
    {
        uint32_t magic;
        uint16_t version;
        uint16_t config_size;
    } header = {};
    const size_t header_read_size = file.read(reinterpret_cast<uint8_t *>(&header), sizeof(header));
    if (header_read_size != sizeof(header))
    {
        Serial.println("Saved runtime config header read failed");
        file.close();
        return false;
    }

    if (header.magic != APP_RUNTIME_CONFIG_STORE_MAGIC)
    {
        Serial.println("Saved runtime config header is invalid");
        file.close();
        return false;
    }

    if (header.version == APP_RUNTIME_CONFIG_STORE_VERSION_V1 &&
        header.config_size == sizeof(app_runtime_config_v1_t))
    {
        app_runtime_config_store_v1_t store = {};
        file.seek(0);
        const size_t read_size = file.read(reinterpret_cast<uint8_t *>(&store), sizeof(store));
        file.close();

        if (read_size != sizeof(store))
        {
            Serial.printf("Saved runtime config v1 size mismatch: %u/%u\n",
                          static_cast<unsigned int>(read_size),
                          static_cast<unsigned int>(sizeof(store)));
            return false;
        }

        const uint32_t expected_crc32 = AppUtils::crc32(reinterpret_cast<const uint8_t *>(&store),
                                                       sizeof(store) - sizeof(store.crc32));
        if (store.crc32 != expected_crc32)
        {
            Serial.printf("Saved runtime config v1 CRC mismatch actual=0x%08X expected=0x%08X\n",
                          store.crc32,
                          expected_crc32);
            return false;
        }

        app_runtime_config_t migrated = app_runtime_config_from_v1(store.config);
        migrated.received_from_mqtt = false;
        if (!app_runtime_config_content_is_valid(migrated))
        {
            Serial.println("Saved runtime config v1 content is invalid");
            return false;
        }

        s_runtime_config = migrated;
        app_runtime_config_save_current();
        return true;
    }

    if (header.version == APP_RUNTIME_CONFIG_STORE_VERSION_V2 &&
        header.config_size == sizeof(app_runtime_config_v2_t))
    {
        app_runtime_config_store_v2_t store = {};
        file.seek(0);
        const size_t read_size = file.read(reinterpret_cast<uint8_t *>(&store), sizeof(store));
        file.close();

        if (read_size != sizeof(store))
        {
            Serial.printf("Saved runtime config v2 size mismatch: %u/%u\n",
                          static_cast<unsigned int>(read_size),
                          static_cast<unsigned int>(sizeof(store)));
            return false;
        }

        const uint32_t expected_crc32 = AppUtils::crc32(reinterpret_cast<const uint8_t *>(&store),
                                                       sizeof(store) - sizeof(store.crc32));
        if (store.crc32 != expected_crc32)
        {
            Serial.printf("Saved runtime config v2 CRC mismatch actual=0x%08X expected=0x%08X\n",
                          store.crc32,
                          expected_crc32);
            return false;
        }

        app_runtime_config_t migrated = app_runtime_config_from_v2(store.config);
        migrated.received_from_mqtt = false;
        if (!app_runtime_config_content_is_valid(migrated))
        {
            Serial.println("Saved runtime config v2 content is invalid");
            return false;
        }

        s_runtime_config = migrated;
        app_runtime_config_save_current();
        return true;
    }

    if (header.version == APP_RUNTIME_CONFIG_STORE_VERSION_V3 &&
        header.config_size == sizeof(app_runtime_config_v3_t))
    {
        app_runtime_config_store_v3_t store = {};
        file.seek(0);
        const size_t read_size = file.read(reinterpret_cast<uint8_t *>(&store), sizeof(store));
        file.close();

        if (read_size != sizeof(store))
        {
            Serial.printf("Saved runtime config v3 size mismatch: %u/%u\n",
                          static_cast<unsigned int>(read_size),
                          static_cast<unsigned int>(sizeof(store)));
            return false;
        }

        const uint32_t expected_crc32 = AppUtils::crc32(reinterpret_cast<const uint8_t *>(&store),
                                                       sizeof(store) - sizeof(store.crc32));
        if (store.crc32 != expected_crc32)
        {
            Serial.printf("Saved runtime config v3 CRC mismatch actual=0x%08X expected=0x%08X\n",
                          store.crc32,
                          expected_crc32);
            return false;
        }

        app_runtime_config_t migrated = app_runtime_config_from_v3(store.config);
        migrated.received_from_mqtt = false;
        if (!app_runtime_config_content_is_valid(migrated))
        {
            Serial.println("Saved runtime config v3 content is invalid");
            return false;
        }

        s_runtime_config = migrated;
        app_runtime_config_save_current();
        return true;
    }

    if (header.version != APP_RUNTIME_CONFIG_STORE_VERSION ||
        header.config_size != sizeof(app_runtime_config_t))
    {
        Serial.println("Saved runtime config header is unsupported");
        file.close();
        return false;
    }

    app_runtime_config_store_t store = {};
    file.seek(0);
    const size_t read_size = file.read(reinterpret_cast<uint8_t *>(&store), sizeof(store));
    file.close();

    if (read_size != sizeof(store))
    {
        Serial.printf("Saved runtime config size mismatch: %u/%u\n",
                      static_cast<unsigned int>(read_size),
                      static_cast<unsigned int>(sizeof(store)));
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

    if (!app_runtime_config_content_is_valid(store.config))
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
    if (!app_runtime_config_content_is_valid(s_runtime_config))
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

bool app_runtime_config_update_soil_calibration(uint16_t dry_raw, uint16_t wet_raw)
{
    if (dry_raw <= wet_raw)
    {
        Serial.println("Skip invalid soil calibration update");
        return false;
    }
    s_runtime_config.soil_calibration.dry_raw = dry_raw;
    s_runtime_config.soil_calibration.wet_raw = wet_raw;
    return app_runtime_config_save_current();
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
    const int32_t local_epoch_day = app_runtime_config_local_epoch_day(local_day_start);
    bool found = false;
    time_t selected_epoch = 0;
    app_schedule_entry_t selected_schedule = {};

    for (uint8_t i = 0; i < s_runtime_config.schedule_count; i++)
    {
        const app_schedule_entry_t &candidate = s_runtime_config.schedules[i];
        if (!app_runtime_config_schedule_matches_day(candidate, local_epoch_day))
        {
            continue;
        }
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

    for (uint16_t day_offset = 0; day_offset <= 370; day_offset++)
    {
        const time_t candidate_day_start = local_day_start + (static_cast<time_t>(day_offset) * 86400);
        const int32_t candidate_epoch_day = app_runtime_config_local_epoch_day(candidate_day_start);
        for (uint8_t i = 0; i < s_runtime_config.schedule_count; i++)
        {
            const app_schedule_entry_t &schedule = s_runtime_config.schedules[i];
            if (!app_runtime_config_schedule_matches_day(schedule, candidate_epoch_day))
            {
                continue;
            }
            const time_t candidate_epoch = app_runtime_config_schedule_epoch_utc(schedule, candidate_day_start, s_runtime_config.timezone_offset_sec);
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
