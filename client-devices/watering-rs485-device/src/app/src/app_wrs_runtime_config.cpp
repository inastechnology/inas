#include "app_wrs_runtime_config.h"

#include <ArduinoJson.h>
#include <LittleFS.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "app_utils.h"

#define APP_WRS_RUNTIME_CONFIG_FILE "/.wrs_runtime_config"
#define APP_WRS_RUNTIME_CONFIG_STORE_MAGIC 0x57525343UL
#define APP_WRS_RUNTIME_CONFIG_STORE_VERSION 1

static app_wrs_runtime_config_t s_runtime_config;

typedef struct
{
    uint32_t magic;
    uint16_t version;
    uint16_t config_size;
    app_wrs_runtime_config_t config;
    uint32_t crc32;
} app_wrs_runtime_config_store_t;

static_assert(
    offsetof(app_wrs_runtime_config_store_t, crc32) + sizeof(uint32_t) ==
        sizeof(app_wrs_runtime_config_store_t),
    "WRS runtime config store unexpectedly has CRC tail padding");

static void copy_string(char *dest, size_t dest_size, const char *src)
{
    if (dest == nullptr || dest_size == 0)
    {
        return;
    }
    if (src == nullptr)
    {
        dest[0] = '\0';
        return;
    }
    strncpy(dest, src, dest_size - 1);
    dest[dest_size - 1] = '\0';
}

static uint32_t sanitize_sleep_sec(uint32_t sleep_sec)
{
    return constrain(sleep_sec, APP_WRS_MIN_SLEEP_SEC, APP_WRS_MAX_SLEEP_SEC);
}

static uint32_t sanitize_ota_check_interval_sec(uint32_t interval_sec)
{
    return constrain(interval_sec, APP_WRS_MIN_OTA_CHECK_INTERVAL_SEC, APP_WRS_MAX_OTA_CHECK_INTERVAL_SEC);
}

static app_wrs_watering_config_t default_watering_config()
{
    app_wrs_watering_config_t config = {};
    config.enabled = true;
    config.auto_on_low_moisture = false;
    config.require_soil_feedback = true;
    config.force_watering = false;
    config.moisture_threshold_percent = 40;
    config.stop_moisture_percent = APP_WRS_WATERING_STOP_MOISTURE_PERCENT;
    config.max_duration_sec = APP_WRS_WATERING_MAX_DURATION_SEC;
    config.check_interval_sec = APP_WRS_WATERING_CHECK_INTERVAL_SEC;
    config.channel_mask = APP_WRS_WATERING_CHANNEL_MASK;
    return config;
}

static app_wrs_sensor_config_t default_sensor_config()
{
    app_wrs_sensor_config_t config = {};
    config.soil.enabled = APP_WRS_SOIL_RS485_ENABLED != 0;
    config.soil.modbus_slave_id = APP_WRS_SOIL_MODBUS_SLAVE_ID;
    config.soil.modbus_function = APP_WRS_SOIL_MODBUS_FUNCTION;
    config.soil.start_register = APP_WRS_SOIL_MODBUS_START_REGISTER;
    config.par.enabled = APP_WRS_PAR_ENABLED != 0;
    config.par.modbus_slave_id = APP_WRS_PAR_MODBUS_SLAVE_ID;
    config.par.modbus_function = APP_WRS_PAR_MODBUS_FUNCTION;
    config.par.register_address = APP_WRS_PAR_REGISTER;
    config.par.scale = APP_WRS_PAR_SCALE;
    config.power_settle_ms = APP_WRS_SENSOR_POWER_SETTLE_MS;
    return config;
}

static app_wrs_runtime_config_t default_runtime_config()
{
    app_wrs_runtime_config_t config = {};
    config.valid = true;
    config.received_from_mqtt = false;
    copy_string(config.ntp_server, sizeof(config.ntp_server), "pool.ntp.org");
    config.timezone_offset_sec = 32400;
    config.sleep_sec = APP_WRS_DEFAULT_SLEEP_SEC;
    config.ota_check_interval_sec = APP_WRS_DEFAULT_OTA_CHECK_INTERVAL_SEC;
    config.debug_log_on_wake = false;
    config.watering = default_watering_config();
    config.sensors = default_sensor_config();
    config.schedule_count = 0;
    return config;
}

static int32_t days_from_civil(int year, unsigned month, unsigned day)
{
    year -= month <= 2;
    const int era = (year >= 0 ? year : year - 399) / 400;
    const unsigned yoe = static_cast<unsigned>(year - era * 400);
    const unsigned doy = (153 * (month + (month > 2 ? -3 : 9)) + 2) / 5 + day - 1;
    const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097 + static_cast<int>(doe) - 719468;
}

static int32_t parse_date_epoch_day(const char *date)
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
    return days_from_civil(year, static_cast<unsigned>(month), static_cast<unsigned>(day));
}

static time_t local_day_start(time_t now_utc, int32_t timezone_offset_sec)
{
    const time_t local_now = now_utc + timezone_offset_sec;
    return (local_now / 86400) * 86400;
}

static int32_t local_epoch_day(time_t local_day)
{
    return static_cast<int32_t>(local_day / 86400);
}

static uint8_t weekday_from_epoch_day(int32_t epoch_day)
{
    int32_t weekday = (epoch_day + 4) % 7;
    if (weekday < 0)
    {
        weekday += 7;
    }
    return static_cast<uint8_t>(weekday);
}

static app_wrs_schedule_entry_t sanitize_schedule_frequency(app_wrs_schedule_entry_t schedule)
{
    if (schedule.frequency_type == APP_WRS_SCHEDULE_FREQUENCY_INTERVAL)
    {
        if (schedule.interval_days < 1)
        {
            schedule.interval_days = 1;
        }
        schedule.weekdays_mask = 0;
        return schedule;
    }
    if (schedule.frequency_type == APP_WRS_SCHEDULE_FREQUENCY_WEEKDAYS)
    {
        if (schedule.weekdays_mask == 0)
        {
            schedule.frequency_type = APP_WRS_SCHEDULE_FREQUENCY_DAILY;
            schedule.interval_days = 1;
        }
        return schedule;
    }
    schedule.frequency_type = APP_WRS_SCHEDULE_FREQUENCY_DAILY;
    schedule.interval_days = 1;
    schedule.weekdays_mask = 0;
    schedule.anchor_epoch_day = 0;
    return schedule;
}

static bool schedule_matches_day(const app_wrs_schedule_entry_t &schedule, int32_t epoch_day)
{
    if (schedule.frequency_type == APP_WRS_SCHEDULE_FREQUENCY_INTERVAL)
    {
        const uint8_t interval_days = schedule.interval_days == 0 ? 1 : schedule.interval_days;
        const int32_t elapsed_days = epoch_day - schedule.anchor_epoch_day;
        return elapsed_days >= 0 && elapsed_days % interval_days == 0;
    }
    if (schedule.frequency_type == APP_WRS_SCHEDULE_FREQUENCY_WEEKDAYS)
    {
        return (schedule.weekdays_mask & (1U << weekday_from_epoch_day(epoch_day))) != 0;
    }
    return true;
}

static time_t schedule_epoch_utc(const app_wrs_schedule_entry_t &schedule, time_t day_start, int32_t timezone_offset_sec)
{
    const time_t local_schedule_epoch = day_start + (schedule.hour * 3600) + (schedule.minute * 60);
    return local_schedule_epoch - timezone_offset_sec;
}

static bool content_is_valid(const app_wrs_runtime_config_t &config)
{
    return config.valid &&
           config.sleep_sec >= APP_WRS_MIN_SLEEP_SEC &&
           config.sleep_sec <= APP_WRS_MAX_SLEEP_SEC &&
           config.ota_check_interval_sec >= APP_WRS_MIN_OTA_CHECK_INTERVAL_SEC &&
           config.ota_check_interval_sec <= APP_WRS_MAX_OTA_CHECK_INTERVAL_SEC &&
           config.schedule_count <= APP_WRS_MAX_SCHEDULES &&
           config.watering.moisture_threshold_percent <= 100 &&
           config.watering.stop_moisture_percent <= 100 &&
           config.watering.max_duration_sec > 0 &&
           config.watering.check_interval_sec > 0;
}

static void parse_sensor_config(JsonObjectConst sensors, app_wrs_sensor_config_t &next)
{
    if (sensors["soil"].is<JsonObjectConst>())
    {
        JsonObjectConst soil = sensors["soil"].as<JsonObjectConst>();
        next.soil.enabled = soil["enabled"] | next.soil.enabled;
        next.soil.modbus_slave_id = static_cast<uint8_t>(constrain(soil["modbus_slave_id"] | next.soil.modbus_slave_id, 1, 247));
        next.soil.modbus_function = static_cast<uint8_t>(constrain(soil["modbus_function"] | next.soil.modbus_function, 3, 4));
        next.soil.start_register = static_cast<uint16_t>(constrain(soil["start_register"] | next.soil.start_register, 0, 65535));
    }
    if (sensors["par"].is<JsonObjectConst>())
    {
        JsonObjectConst par = sensors["par"].as<JsonObjectConst>();
        next.par.enabled = par["enabled"] | next.par.enabled;
        next.par.modbus_slave_id = static_cast<uint8_t>(constrain(par["modbus_slave_id"] | next.par.modbus_slave_id, 1, 247));
        next.par.modbus_function = static_cast<uint8_t>(constrain(par["modbus_function"] | next.par.modbus_function, 3, 4));
        next.par.register_address = static_cast<uint16_t>(constrain(par["register"] | next.par.register_address, 0, 65535));
        if (par["scale"].is<float>() || par["scale"].is<int>())
        {
            next.par.scale = constrain(par["scale"].as<float>(), 0.0001f, 100000.0f);
        }
    }
    long power_settle_ms = sensors["power_settle_ms"] | static_cast<long>(next.power_settle_ms);
    next.power_settle_ms = static_cast<uint32_t>(constrain(power_settle_ms, 0L, 30000L));
}

static void parse_watering_config(JsonObjectConst watering, app_wrs_watering_config_t &next)
{
    next.enabled = watering["enabled"] | next.enabled;
    next.auto_on_low_moisture = watering["auto_on_low_moisture"] | next.auto_on_low_moisture;
    next.require_soil_feedback = watering["require_soil_feedback"] | next.require_soil_feedback;
    next.force_watering = watering["force_watering"] | next.force_watering;
    next.moisture_threshold_percent = static_cast<uint8_t>(constrain(watering["moisture_threshold"] | next.moisture_threshold_percent, 0, 100));
    next.stop_moisture_percent = static_cast<uint8_t>(constrain(watering["stop_moisture_percent"] | next.stop_moisture_percent, 0, 100));
    next.max_duration_sec = static_cast<uint16_t>(constrain(watering["max_duration_sec"] | next.max_duration_sec, 1, 3600));
    next.check_interval_sec = static_cast<uint16_t>(constrain(watering["check_interval_sec"] | next.check_interval_sec, 1, 600));
    next.channel_mask = watering["channel_mask"] | next.channel_mask;
    if (next.channel_mask == 0)
    {
        next.channel_mask = APP_WRS_WATERING_CHANNEL_MASK;
    }
}

void app_wrs_runtime_config_init()
{
    s_runtime_config = default_runtime_config();
    if (app_wrs_runtime_config_load_saved())
    {
        Serial.printf("Loaded WRS runtime config: sleep=%lu schedules=%u soil=%s par=%s threshold=%u stop=%u max=%u check=%u\n",
                      static_cast<unsigned long>(s_runtime_config.sleep_sec),
                      static_cast<unsigned int>(s_runtime_config.schedule_count),
                      s_runtime_config.sensors.soil.enabled ? "true" : "false",
                      s_runtime_config.sensors.par.enabled ? "true" : "false",
                      s_runtime_config.watering.moisture_threshold_percent,
                      s_runtime_config.watering.stop_moisture_percent,
                      s_runtime_config.watering.max_duration_sec,
                      s_runtime_config.watering.check_interval_sec);
    }
}

void app_wrs_runtime_config_mark_waiting()
{
    s_runtime_config.received_from_mqtt = false;
}

bool app_wrs_runtime_config_apply_json(const uint8_t *payload, size_t length)
{
    if (payload == nullptr || length == 0)
    {
        return false;
    }

    JsonDocument doc;
    const DeserializationError error = deserializeJson(doc, payload, length);
    if (error)
    {
        Serial.printf("Failed to parse WRS runtime config JSON: %s\n", error.c_str());
        return false;
    }

    app_wrs_runtime_config_t next = s_runtime_config;
    next.received_from_mqtt = true;
    memset(next.schedules, 0, sizeof(next.schedules));
    next.schedule_count = 0;

    copy_string(next.ntp_server, sizeof(next.ntp_server), doc["ntp_server"] | next.ntp_server);
    next.timezone_offset_sec = doc["timezone_offset_sec"] | next.timezone_offset_sec;
    long sleep_sec = doc["sleep_sec"] | static_cast<long>(next.sleep_sec);
    next.sleep_sec = sanitize_sleep_sec(static_cast<uint32_t>(max(0L, sleep_sec)));
    long ota_check_interval_sec = doc["ota_check_interval_sec"] | static_cast<long>(next.ota_check_interval_sec);
    next.ota_check_interval_sec = sanitize_ota_check_interval_sec(static_cast<uint32_t>(max(0L, ota_check_interval_sec)));
    next.debug_log_on_wake = doc["debug_log_on_wake"] | (doc["debug_log_enabled"] | next.debug_log_on_wake);

    next.watering.moisture_threshold_percent = static_cast<uint8_t>(constrain(doc["moisture_threshold"] | next.watering.moisture_threshold_percent, 0, 100));
    next.watering.force_watering = doc["force_watering"] | next.watering.force_watering;

    if (doc["env_sensors"].is<JsonObjectConst>())
    {
        parse_sensor_config(doc["env_sensors"].as<JsonObjectConst>(), next.sensors);
    }
    if (doc["wrs"].is<JsonObjectConst>())
    {
        JsonObjectConst wrs = doc["wrs"].as<JsonObjectConst>();
        if (wrs["sensors"].is<JsonObjectConst>())
        {
            parse_sensor_config(wrs["sensors"].as<JsonObjectConst>(), next.sensors);
        }
        if (wrs["watering"].is<JsonObjectConst>())
        {
            parse_watering_config(wrs["watering"].as<JsonObjectConst>(), next.watering);
        }
    }

    if (doc["schedules"].is<JsonArrayConst>())
    {
        for (JsonObjectConst schedule_json : doc["schedules"].as<JsonArrayConst>())
        {
            if (next.schedule_count >= APP_WRS_MAX_SCHEDULES)
            {
                break;
            }

            const int hour = schedule_json["hour"] | -1;
            const int minute = schedule_json["minute"] | -1;
            const int duration_sec = schedule_json["duration_sec"] | 0;
            const uint32_t channel_mask = schedule_json["channel_mask"] | next.watering.channel_mask;
            if (hour < 0 || hour > 23 || minute < 0 || minute > 59 || duration_sec <= 0 || channel_mask == 0)
            {
                Serial.println("Ignoring invalid WRS schedule entry");
                continue;
            }

            app_wrs_schedule_entry_t schedule = {};
            schedule.hour = static_cast<uint8_t>(hour);
            schedule.minute = static_cast<uint8_t>(minute);
            schedule.duration_sec = static_cast<uint16_t>(constrain(duration_sec, 1, 3600));
            schedule.channel_mask = channel_mask;
            schedule.frequency_type = APP_WRS_SCHEDULE_FREQUENCY_DAILY;
            schedule.interval_days = 1;
            schedule.weekdays_mask = 0;
            schedule.anchor_epoch_day = 0;

            if (schedule_json["frequency"].is<JsonObjectConst>())
            {
                JsonObjectConst frequency = schedule_json["frequency"].as<JsonObjectConst>();
                const char *mode = frequency["mode"] | "daily";
                if (strcmp(mode, "interval") == 0)
                {
                    schedule.frequency_type = APP_WRS_SCHEDULE_FREQUENCY_INTERVAL;
                    schedule.interval_days = static_cast<uint8_t>(constrain(frequency["interval_days"] | 1, 1, 31));
                    schedule.anchor_epoch_day = parse_date_epoch_day(frequency["start_date"] | nullptr);
                }
                else if (strcmp(mode, "weekdays") == 0)
                {
                    schedule.frequency_type = APP_WRS_SCHEDULE_FREQUENCY_WEEKDAYS;
                    int weekdays_mask = frequency["weekdays_mask"] | 0;
                    if (frequency["weekdays"].is<JsonArrayConst>())
                    {
                        weekdays_mask = 0;
                        for (JsonVariantConst weekday_json : frequency["weekdays"].as<JsonArrayConst>())
                        {
                            const int weekday = weekday_json.as<int>();
                            if (weekday >= 0 && weekday <= 6)
                            {
                                weekdays_mask |= 1 << weekday;
                            }
                        }
                    }
                    schedule.weekdays_mask = static_cast<uint8_t>(weekdays_mask & 0x7F);
                }
            }

            next.schedules[next.schedule_count++] = sanitize_schedule_frequency(schedule);
        }
    }

    next.valid = content_is_valid(next);
    if (!next.valid)
    {
        Serial.println("WRS runtime config content is invalid");
        return false;
    }

    s_runtime_config = next;
    app_wrs_runtime_config_save_current();
    Serial.printf("WRS runtime config updated: sleep=%lu schedules=%u soil=%s par=%s threshold=%u stop=%u max=%u check=%u auto=%s force=%s\n",
                  static_cast<unsigned long>(s_runtime_config.sleep_sec),
                  static_cast<unsigned int>(s_runtime_config.schedule_count),
                  s_runtime_config.sensors.soil.enabled ? "true" : "false",
                  s_runtime_config.sensors.par.enabled ? "true" : "false",
                  s_runtime_config.watering.moisture_threshold_percent,
                  s_runtime_config.watering.stop_moisture_percent,
                  s_runtime_config.watering.max_duration_sec,
                  s_runtime_config.watering.check_interval_sec,
                  s_runtime_config.watering.auto_on_low_moisture ? "true" : "false",
                  s_runtime_config.watering.force_watering ? "true" : "false");
    return true;
}

bool app_wrs_runtime_config_load_saved()
{
    if (!LittleFS.exists(APP_WRS_RUNTIME_CONFIG_FILE))
    {
        return false;
    }

    File file = LittleFS.open(APP_WRS_RUNTIME_CONFIG_FILE, "r");
    if (!file)
    {
        return false;
    }

    app_wrs_runtime_config_store_t store = {};
    const size_t read_size = file.read(reinterpret_cast<uint8_t *>(&store), sizeof(store));
    file.close();
    if (read_size != sizeof(store) ||
        store.magic != APP_WRS_RUNTIME_CONFIG_STORE_MAGIC ||
        store.version != APP_WRS_RUNTIME_CONFIG_STORE_VERSION ||
        store.config_size != sizeof(app_wrs_runtime_config_t))
    {
        return false;
    }

    const uint32_t expected_crc32 = AppUtils::crc32(
        reinterpret_cast<const uint8_t *>(&store),
        offsetof(app_wrs_runtime_config_store_t, crc32));
    if (store.crc32 != expected_crc32 || !content_is_valid(store.config))
    {
        Serial.println("Saved WRS runtime config is invalid");
        return false;
    }

    store.config.received_from_mqtt = false;
    s_runtime_config = store.config;
    return true;
}

bool app_wrs_runtime_config_save_current()
{
    if (!content_is_valid(s_runtime_config))
    {
        return false;
    }

    app_wrs_runtime_config_store_t store = {};
    store.magic = APP_WRS_RUNTIME_CONFIG_STORE_MAGIC;
    store.version = APP_WRS_RUNTIME_CONFIG_STORE_VERSION;
    store.config_size = sizeof(app_wrs_runtime_config_t);
    store.config = s_runtime_config;
    store.config.received_from_mqtt = false;
    store.crc32 = AppUtils::crc32(
        reinterpret_cast<const uint8_t *>(&store),
        offsetof(app_wrs_runtime_config_store_t, crc32));

    File file = LittleFS.open(APP_WRS_RUNTIME_CONFIG_FILE, "w");
    if (!file)
    {
        return false;
    }
    const size_t written = file.write(reinterpret_cast<const uint8_t *>(&store), sizeof(store));
    file.close();
    return written == sizeof(store);
}

bool app_wrs_runtime_config_is_valid()
{
    return s_runtime_config.valid;
}

bool app_wrs_runtime_config_is_received()
{
    return s_runtime_config.received_from_mqtt;
}

const app_wrs_runtime_config_t &app_wrs_runtime_config_get()
{
    return s_runtime_config;
}

bool app_wrs_runtime_config_find_due_schedule(time_t now_utc,
                                              time_t last_executed_schedule_utc,
                                              app_wrs_schedule_entry_t *schedule_out,
                                              time_t *schedule_epoch_utc_out)
{
    if (!s_runtime_config.valid || schedule_out == nullptr || schedule_epoch_utc_out == nullptr)
    {
        return false;
    }

    const time_t day_start = local_day_start(now_utc, s_runtime_config.timezone_offset_sec);
    const int32_t epoch_day = local_epoch_day(day_start);
    bool found = false;
    time_t selected_epoch = 0;
    app_wrs_schedule_entry_t selected = {};

    for (uint8_t i = 0; i < s_runtime_config.schedule_count; ++i)
    {
        const app_wrs_schedule_entry_t &candidate = s_runtime_config.schedules[i];
        if (!schedule_matches_day(candidate, epoch_day))
        {
            continue;
        }
        const time_t candidate_epoch = schedule_epoch_utc(candidate, day_start, s_runtime_config.timezone_offset_sec);
        if (candidate_epoch > now_utc || candidate_epoch <= last_executed_schedule_utc)
        {
            continue;
        }
        if (!found || candidate_epoch > selected_epoch)
        {
            found = true;
            selected_epoch = candidate_epoch;
            selected = candidate;
        }
    }

    if (!found)
    {
        return false;
    }
    *schedule_out = selected;
    *schedule_epoch_utc_out = selected_epoch;
    return true;
}

uint32_t app_wrs_runtime_config_seconds_until_next_schedule(time_t now_utc)
{
    if (!s_runtime_config.valid || s_runtime_config.schedule_count == 0)
    {
        return s_runtime_config.sleep_sec;
    }

    const time_t current_day_start = local_day_start(now_utc, s_runtime_config.timezone_offset_sec);
    bool found = false;
    time_t selected_epoch = 0;
    for (uint16_t day_offset = 0; day_offset <= 370; ++day_offset)
    {
        const time_t candidate_day_start = current_day_start + static_cast<time_t>(day_offset) * 86400;
        const int32_t candidate_epoch_day = local_epoch_day(candidate_day_start);
        for (uint8_t i = 0; i < s_runtime_config.schedule_count; ++i)
        {
            const app_wrs_schedule_entry_t &schedule = s_runtime_config.schedules[i];
            if (!schedule_matches_day(schedule, candidate_epoch_day))
            {
                continue;
            }
            const time_t candidate_epoch = schedule_epoch_utc(schedule, candidate_day_start, s_runtime_config.timezone_offset_sec);
            if (candidate_epoch <= now_utc)
            {
                continue;
            }
            if (!found || candidate_epoch < selected_epoch)
            {
                found = true;
                selected_epoch = candidate_epoch;
            }
        }
        if (found)
        {
            break;
        }
    }

    if (!found)
    {
        return s_runtime_config.sleep_sec;
    }
    return static_cast<uint32_t>(selected_epoch - now_utc);
}
