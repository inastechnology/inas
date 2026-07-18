#include "app_fgt_runtime_config.h"

#include <ArduinoJson.h>
#include <LittleFS.h>
#include <string.h>

#include "app_utils.h"

#define APP_FGT_RUNTIME_CONFIG_FILE "/.fgt_runtime_config"
#define APP_FGT_RUNTIME_CONFIG_STORE_MAGIC 0x46475443UL
#define APP_FGT_RUNTIME_CONFIG_STORE_VERSION 1

#ifndef APP_FGT_SOIL_RS485_ENABLED
#define APP_FGT_SOIL_RS485_ENABLED 1
#endif
#ifndef APP_FGT_SOIL_MODBUS_SLAVE_ID
#define APP_FGT_SOIL_MODBUS_SLAVE_ID 2
#endif
#ifndef APP_FGT_SOIL_MODBUS_FUNCTION
#define APP_FGT_SOIL_MODBUS_FUNCTION 4
#endif
#ifndef APP_FGT_SOIL_MODBUS_START_REGISTER
#define APP_FGT_SOIL_MODBUS_START_REGISTER 0
#endif
#ifndef APP_FGT_PAR_ENABLED
#define APP_FGT_PAR_ENABLED 1
#endif
#ifndef APP_FGT_PAR_MODBUS_SLAVE_ID
#define APP_FGT_PAR_MODBUS_SLAVE_ID 1
#endif
#ifndef APP_FGT_PAR_MODBUS_FUNCTION
#define APP_FGT_PAR_MODBUS_FUNCTION 3
#endif
#ifndef APP_FGT_PAR_REGISTER
#define APP_FGT_PAR_REGISTER 0
#endif
#ifndef APP_FGT_PAR_SCALE
#define APP_FGT_PAR_SCALE 1.0f
#endif
#ifndef APP_FGT_SENSOR_POWER_SETTLE_MS
#define APP_FGT_SENSOR_POWER_SETTLE_MS 800
#endif
#ifndef APP_FGT_FLOW_PULSES_PER_LITER
#define APP_FGT_FLOW_PULSES_PER_LITER 450
#endif

typedef struct
{
    uint32_t magic;
    uint16_t version;
    uint16_t config_size;
    app_fgt_runtime_config_t config;
    uint32_t crc32;
} app_fgt_runtime_config_store_t;

static app_fgt_runtime_config_t s_runtime_config = {};

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

static uint32_t bounded_u32(JsonVariantConst value, uint32_t current, uint32_t minimum, uint32_t maximum)
{
    if (!value.is<int>() && !value.is<unsigned int>() && !value.is<long>() && !value.is<unsigned long>())
    {
        return current;
    }
    const int64_t parsed = value.as<int64_t>();
    if (parsed < static_cast<int64_t>(minimum)) return minimum;
    if (parsed > static_cast<int64_t>(maximum)) return maximum;
    return static_cast<uint32_t>(parsed);
}

static uint32_t seconds_to_ms(JsonVariantConst value, uint32_t current_ms, uint32_t min_sec, uint32_t max_sec)
{
    const uint32_t current_sec = current_ms / 1000UL;
    return bounded_u32(value, current_sec, min_sec, max_sec) * 1000UL;
}

static app_fgt_sensor_config_t default_sensors()
{
    app_fgt_sensor_config_t sensors = {};
    sensors.soil.enabled = APP_FGT_SOIL_RS485_ENABLED != 0;
    sensors.soil.modbus_slave_id = APP_FGT_SOIL_MODBUS_SLAVE_ID;
    sensors.soil.modbus_function = APP_FGT_SOIL_MODBUS_FUNCTION;
    sensors.soil.start_register = APP_FGT_SOIL_MODBUS_START_REGISTER;
    sensors.par.enabled = APP_FGT_PAR_ENABLED != 0;
    sensors.par.modbus_slave_id = APP_FGT_PAR_MODBUS_SLAVE_ID;
    sensors.par.modbus_function = APP_FGT_PAR_MODBUS_FUNCTION;
    sensors.par.register_address = APP_FGT_PAR_REGISTER;
    sensors.par.scale = APP_FGT_PAR_SCALE;
    sensors.power_settle_ms = APP_FGT_SENSOR_POWER_SETTLE_MS;
    sensors.flow_pulses_per_liter = APP_FGT_FLOW_PULSES_PER_LITER;
    return sensors;
}

static app_fgt_runtime_config_t default_config()
{
    app_fgt_runtime_config_t config = {};
    config.valid = true;
    copy_string(config.ntp_server, sizeof(config.ntp_server), "pool.ntp.org");
    config.timezone_offset_sec = 32400;
    config.sleep_sec = APP_FGT_DEFAULT_SLEEP_SEC;
    config.ota_check_interval_sec = APP_FGT_DEFAULT_OTA_CHECK_INTERVAL_SEC;
    // Unattended nutrient dosing requires an explicit Hub opt-in. A generic
    // config reply or a freshly flashed device must remain actuator-safe.
    config.enabled = false;
    config.recipe = fgt::Recipe{};
    config.limits = fgt::Limits{};
    config.sensors = default_sensors();
    return config;
}

static bool content_is_valid(const app_fgt_runtime_config_t &config)
{
    if (!config.valid || config.sleep_sec < APP_FGT_MIN_SLEEP_SEC || config.sleep_sec > APP_FGT_MAX_SLEEP_SEC ||
        config.ota_check_interval_sec < APP_FGT_MIN_OTA_CHECK_INTERVAL_SEC ||
        config.ota_check_interval_sec > APP_FGT_MAX_OTA_CHECK_INTERVAL_SEC ||
        config.schedule_count > APP_FGT_MAX_SCHEDULES || config.sensors.flow_pulses_per_liter == 0 ||
        !fgt::recipe_valid(config.recipe, config.limits))
    {
        return false;
    }
    for (uint8_t i = 0; i < config.schedule_count; ++i)
    {
        if (config.schedules[i].hour > 23 || config.schedules[i].minute > 59)
        {
            return false;
        }
    }
    return true;
}

static void parse_recipe(JsonObjectConst json, fgt::Recipe &recipe)
{
    recipe.total_water_ml = bounded_u32(json["total_water_ml"], recipe.total_water_ml, 100, 100000);
    recipe.initial_water_ml = bounded_u32(json["initial_water_ml"], recipe.initial_water_ml, 50, 100000);
    recipe.nutrient_a_ml = bounded_u32(json["nutrient_a_ml"], recipe.nutrient_a_ml, 0, 10000);
    recipe.nutrient_b_ml = bounded_u32(json["nutrient_b_ml"], recipe.nutrient_b_ml, 0, 10000);
    recipe.nutrient_a_rate_ml_min = bounded_u32(json["nutrient_a_rate_ml_min"], recipe.nutrient_a_rate_ml_min, 1, 10000);
    recipe.nutrient_b_rate_ml_min = bounded_u32(json["nutrient_b_rate_ml_min"], recipe.nutrient_b_rate_ml_min, 1, 10000);
    recipe.pre_mix_ms = seconds_to_ms(json["pre_mix_sec"], recipe.pre_mix_ms, 1, 600);
    recipe.mix_after_a_ms = seconds_to_ms(json["mix_after_a_sec"], recipe.mix_after_a_ms, 0, 1800);
    recipe.mix_after_b_ms = seconds_to_ms(json["mix_after_b_sec"], recipe.mix_after_b_ms, 0, 1800);
    recipe.final_mix_ms = seconds_to_ms(json["final_mix_sec"], recipe.final_mix_ms, 1, 3600);
    recipe.irrigation_max_ms = seconds_to_ms(json["irrigation_max_sec"], recipe.irrigation_max_ms, 1, 7200);
    recipe.rinse_water_ml = bounded_u32(json["rinse_water_ml"], recipe.rinse_water_ml, 0, 100000);
    recipe.rinse_mix_ms = seconds_to_ms(json["rinse_mix_sec"], recipe.rinse_mix_ms, 0, 1800);
    recipe.rinse_drain_max_ms = seconds_to_ms(json["rinse_drain_max_sec"], recipe.rinse_drain_max_ms, 0, 3600);
}

static void parse_limits(JsonObjectConst json, fgt::Limits &limits)
{
    limits.max_total_water_ml = bounded_u32(json["max_total_water_ml"], limits.max_total_water_ml, 100, 100000);
    limits.max_nutrient_ml = bounded_u32(json["max_nutrient_ml"], limits.max_nutrient_ml, 1, 10000);
    limits.water_no_flow_timeout_ms = seconds_to_ms(json["water_no_flow_timeout_sec"], limits.water_no_flow_timeout_ms, 1, 300);
    limits.max_fill_ms = seconds_to_ms(json["max_fill_sec"], limits.max_fill_ms, 1, 3600);
    limits.max_batch_ms = seconds_to_ms(json["max_batch_sec"], limits.max_batch_ms, 60, 14400);
    limits.volume_tolerance_ml = bounded_u32(json["volume_tolerance_ml"], limits.volume_tolerance_ml, 0, 5000);
}

static void parse_sensors(JsonObjectConst json, app_fgt_sensor_config_t &sensors)
{
    if (json["soil"].is<JsonObjectConst>())
    {
        JsonObjectConst soil = json["soil"].as<JsonObjectConst>();
        sensors.soil.enabled = soil["enabled"] | sensors.soil.enabled;
        sensors.soil.modbus_slave_id = static_cast<uint8_t>(bounded_u32(soil["modbus_slave_id"], sensors.soil.modbus_slave_id, 1, 247));
        sensors.soil.modbus_function = static_cast<uint8_t>(bounded_u32(soil["modbus_function"], sensors.soil.modbus_function, 3, 4));
        sensors.soil.start_register = static_cast<uint16_t>(bounded_u32(soil["start_register"], sensors.soil.start_register, 0, 65535));
    }
    if (json["par"].is<JsonObjectConst>())
    {
        JsonObjectConst par = json["par"].as<JsonObjectConst>();
        sensors.par.enabled = par["enabled"] | sensors.par.enabled;
        sensors.par.modbus_slave_id = static_cast<uint8_t>(bounded_u32(par["modbus_slave_id"], sensors.par.modbus_slave_id, 1, 247));
        sensors.par.modbus_function = static_cast<uint8_t>(bounded_u32(par["modbus_function"], sensors.par.modbus_function, 3, 4));
        sensors.par.register_address = static_cast<uint16_t>(bounded_u32(par["register"], sensors.par.register_address, 0, 65535));
        if (par["scale"].is<float>() || par["scale"].is<int>())
        {
            sensors.par.scale = constrain(par["scale"].as<float>(), 0.0001f, 100000.0f);
        }
    }
    sensors.power_settle_ms = bounded_u32(json["power_settle_ms"], sensors.power_settle_ms, 0, 30000);
    sensors.flow_pulses_per_liter = bounded_u32(json["flow_pulses_per_liter"], sensors.flow_pulses_per_liter, 1, 1000000);
}

void app_fgt_runtime_config_init()
{
    s_runtime_config = default_config();
    app_fgt_runtime_config_load_saved();
}

void app_fgt_runtime_config_mark_waiting()
{
    s_runtime_config.received_from_mqtt = false;
}

bool app_fgt_runtime_config_apply_json(const uint8_t *payload, size_t length)
{
    if (payload == nullptr || length == 0)
    {
        return false;
    }
    JsonDocument doc;
    const DeserializationError error = deserializeJson(doc, payload, length);
    if (error)
    {
        Serial.printf("Failed to parse FGT runtime config JSON: %s\n", error.c_str());
        return false;
    }

    app_fgt_runtime_config_t next = s_runtime_config;
    next.received_from_mqtt = true;
    copy_string(next.ntp_server, sizeof(next.ntp_server), doc["ntp_server"] | next.ntp_server);
    next.timezone_offset_sec = doc["timezone_offset_sec"] | next.timezone_offset_sec;
    next.sleep_sec = bounded_u32(doc["sleep_sec"], next.sleep_sec, APP_FGT_MIN_SLEEP_SEC, APP_FGT_MAX_SLEEP_SEC);
    next.ota_check_interval_sec = bounded_u32(doc["ota_check_interval_sec"], next.ota_check_interval_sec,
                                               APP_FGT_MIN_OTA_CHECK_INTERVAL_SEC, APP_FGT_MAX_OTA_CHECK_INTERVAL_SEC);
    next.debug_log_on_wake = doc["debug_log_on_wake"] | (doc["debug_log_enabled"] | next.debug_log_on_wake);

    if (doc["fgt"].is<JsonObjectConst>())
    {
        JsonObjectConst fgt_json = doc["fgt"].as<JsonObjectConst>();
        next.enabled = fgt_json["enabled"] | next.enabled;
        next.recovery_ack = bounded_u32(fgt_json["recovery_ack"], next.recovery_ack, 0, UINT32_MAX);
        if (fgt_json["recipe"].is<JsonObjectConst>()) parse_recipe(fgt_json["recipe"].as<JsonObjectConst>(), next.recipe);
        if (fgt_json["limits"].is<JsonObjectConst>()) parse_limits(fgt_json["limits"].as<JsonObjectConst>(), next.limits);
        if (fgt_json["sensors"].is<JsonObjectConst>()) parse_sensors(fgt_json["sensors"].as<JsonObjectConst>(), next.sensors);
    }

    memset(next.schedules, 0, sizeof(next.schedules));
    next.schedule_count = 0;
    if (doc["schedules"].is<JsonArrayConst>())
    {
        for (JsonObjectConst schedule_json : doc["schedules"].as<JsonArrayConst>())
        {
            if (next.schedule_count >= APP_FGT_MAX_SCHEDULES) break;
            if (schedule_json["frequency"].is<JsonObjectConst>())
            {
                const char *mode = schedule_json["frequency"]["mode"] | "daily";
                // FGT v1 deliberately supports daily schedules only. Silently
                // treating an interval/weekday schedule as daily could dose far
                // more often than configured, so unsupported entries are skipped.
                if (strcmp(mode, "daily") != 0) continue;
            }
            const int hour = schedule_json["hour"] | -1;
            const int minute = schedule_json["minute"] | -1;
            if (hour < 0 || hour > 23 || minute < 0 || minute > 59) continue;
            app_fgt_schedule_entry_t schedule = {};
            schedule.enabled = schedule_json["enabled"] | true;
            schedule.hour = static_cast<uint8_t>(hour);
            schedule.minute = static_cast<uint8_t>(minute);
            next.schedules[next.schedule_count++] = schedule;
        }
    }

    next.valid = content_is_valid(next);
    if (!next.valid)
    {
        Serial.println("FGT runtime config content is invalid");
        return false;
    }
    s_runtime_config = next;
    return app_fgt_runtime_config_save_current();
}

bool app_fgt_runtime_config_load_saved()
{
    if (!LittleFS.exists(APP_FGT_RUNTIME_CONFIG_FILE)) return false;
    File file = LittleFS.open(APP_FGT_RUNTIME_CONFIG_FILE, "r");
    if (!file) return false;
    app_fgt_runtime_config_store_t store = {};
    const size_t read_size = file.read(reinterpret_cast<uint8_t *>(&store), sizeof(store));
    file.close();
    const uint32_t expected = AppUtils::crc32(reinterpret_cast<const uint8_t *>(&store), sizeof(store) - sizeof(store.crc32));
    if (read_size != sizeof(store) || store.magic != APP_FGT_RUNTIME_CONFIG_STORE_MAGIC ||
        store.version != APP_FGT_RUNTIME_CONFIG_STORE_VERSION || store.config_size != sizeof(store.config) ||
        store.crc32 != expected || !content_is_valid(store.config))
    {
        Serial.println("Saved FGT runtime config is invalid; using safe defaults");
        return false;
    }
    store.config.received_from_mqtt = false;
    s_runtime_config = store.config;
    return true;
}

bool app_fgt_runtime_config_save_current()
{
    if (!content_is_valid(s_runtime_config)) return false;
    app_fgt_runtime_config_store_t store = {};
    store.magic = APP_FGT_RUNTIME_CONFIG_STORE_MAGIC;
    store.version = APP_FGT_RUNTIME_CONFIG_STORE_VERSION;
    store.config_size = sizeof(store.config);
    store.config = s_runtime_config;
    store.config.received_from_mqtt = false;
    store.crc32 = AppUtils::crc32(reinterpret_cast<const uint8_t *>(&store), sizeof(store) - sizeof(store.crc32));
    File file = LittleFS.open(APP_FGT_RUNTIME_CONFIG_FILE, "w");
    if (!file) return false;
    const size_t written = file.write(reinterpret_cast<const uint8_t *>(&store), sizeof(store));
    file.close();
    return written == sizeof(store);
}

bool app_fgt_runtime_config_is_valid() { return s_runtime_config.valid; }
bool app_fgt_runtime_config_is_received() { return s_runtime_config.received_from_mqtt; }
const app_fgt_runtime_config_t &app_fgt_runtime_config_get() { return s_runtime_config; }

static time_t local_day_start(time_t now_utc)
{
    const time_t local_now = now_utc + s_runtime_config.timezone_offset_sec;
    return (local_now / 86400) * 86400;
}

static time_t schedule_epoch(const app_fgt_schedule_entry_t &schedule, time_t local_day)
{
    return local_day + schedule.hour * 3600 + schedule.minute * 60 - s_runtime_config.timezone_offset_sec;
}

bool app_fgt_runtime_config_find_due_schedule(time_t now_utc,
                                              time_t last_executed_schedule_utc,
                                              app_fgt_schedule_entry_t *schedule_out,
                                              time_t *schedule_epoch_utc_out)
{
    if (!content_is_valid(s_runtime_config) || schedule_out == nullptr || schedule_epoch_utc_out == nullptr) return false;
    const time_t day_start = local_day_start(now_utc);
    bool found = false;
    time_t selected_epoch = 0;
    app_fgt_schedule_entry_t selected = {};
    for (uint8_t i = 0; i < s_runtime_config.schedule_count; ++i)
    {
        const app_fgt_schedule_entry_t &candidate = s_runtime_config.schedules[i];
        if (!candidate.enabled) continue;
        const time_t candidate_epoch = schedule_epoch(candidate, day_start);
        if (candidate_epoch > now_utc || candidate_epoch <= last_executed_schedule_utc) continue;
        if (!found || candidate_epoch > selected_epoch)
        {
            found = true;
            selected = candidate;
            selected_epoch = candidate_epoch;
        }
    }
    if (!found) return false;
    *schedule_out = selected;
    *schedule_epoch_utc_out = selected_epoch;
    return true;
}

uint32_t app_fgt_runtime_config_seconds_until_next_schedule(time_t now_utc)
{
    if (!content_is_valid(s_runtime_config) || s_runtime_config.schedule_count == 0) return s_runtime_config.sleep_sec;
    const time_t day_start = local_day_start(now_utc);
    bool found = false;
    time_t selected_epoch = 0;
    for (uint8_t day = 0; day <= 1; ++day)
    {
        const time_t candidate_day = day_start + static_cast<time_t>(day) * 86400;
        for (uint8_t i = 0; i < s_runtime_config.schedule_count; ++i)
        {
            const app_fgt_schedule_entry_t &schedule = s_runtime_config.schedules[i];
            if (!schedule.enabled) continue;
            const time_t candidate = schedule_epoch(schedule, candidate_day);
            if (candidate <= now_utc) continue;
            if (!found || candidate < selected_epoch)
            {
                found = true;
                selected_epoch = candidate;
            }
        }
        if (found) break;
    }
    return found ? static_cast<uint32_t>(selected_epoch - now_utc) : s_runtime_config.sleep_sec;
}
