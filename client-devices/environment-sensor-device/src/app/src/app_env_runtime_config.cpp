#include "app_env_runtime_config.h"

#include <ArduinoJson.h>
#include <LittleFS.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "app_utils.h"

#define APP_ENV_RUNTIME_CONFIG_FILE "/.env_runtime_config"
#define APP_ENV_RUNTIME_CONFIG_STORE_MAGIC 0x454E5643UL
#define APP_ENV_RUNTIME_CONFIG_STORE_VERSION 1

static app_env_runtime_config_t s_runtime_config;
static app_env_metric_calibration_t s_fallback_metric = {false, 1.0f, 0.0f};

typedef struct
{
    uint32_t magic;
    uint16_t version;
    uint16_t config_size;
    app_env_runtime_config_t config;
    uint32_t crc32;
} app_env_runtime_config_store_t;

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
    if (sleep_sec < APP_ENV_MIN_SLEEP_SEC)
    {
        return APP_ENV_MIN_SLEEP_SEC;
    }
    if (sleep_sec > APP_ENV_MAX_SLEEP_SEC)
    {
        return APP_ENV_MAX_SLEEP_SEC;
    }
    return sleep_sec;
}

static uint32_t sanitize_ota_check_interval(uint32_t interval_sec)
{
    if (interval_sec < APP_ENV_MIN_OTA_CHECK_INTERVAL_SEC)
    {
        return APP_ENV_MIN_OTA_CHECK_INTERVAL_SEC;
    }
    if (interval_sec > APP_ENV_MAX_OTA_CHECK_INTERVAL_SEC)
    {
        return APP_ENV_MAX_OTA_CHECK_INTERVAL_SEC;
    }
    return interval_sec;
}

static bool calibration_mode_is_valid(const char *mode)
{
    return strcmp(mode, APP_ENV_CALIBRATION_MODE_NORMAL) == 0 ||
           strcmp(mode, APP_ENV_CALIBRATION_MODE_CAPTURE_REFERENCE) == 0 ||
           strcmp(mode, APP_ENV_CALIBRATION_MODE_RESET) == 0;
}

bool app_env_metric_is_supported(const char *metric)
{
    return metric != nullptr &&
           (strcmp(metric, APP_ENV_METRIC_PAR) == 0 ||
            strcmp(metric, APP_ENV_METRIC_SOIL_MOISTURE) == 0 ||
            strcmp(metric, APP_ENV_METRIC_SOIL_TEMPERATURE) == 0 ||
            strcmp(metric, APP_ENV_METRIC_SOIL_EC) == 0 ||
            strcmp(metric, APP_ENV_METRIC_SOIL_PH) == 0 ||
            strcmp(metric, APP_ENV_METRIC_SOIL_N) == 0 ||
            strcmp(metric, APP_ENV_METRIC_SOIL_P) == 0 ||
            strcmp(metric, APP_ENV_METRIC_SOIL_K) == 0);
}

static app_env_metric_calibration_t default_metric_calibration(float scale = 1.0f)
{
    app_env_metric_calibration_t calibration = {};
    calibration.calibrated = false;
    calibration.scale = scale;
    calibration.offset = 0.0f;
    return calibration;
}

static app_env_calibration_config_t default_calibration()
{
    app_env_calibration_config_t calibration = {};
    copy_string(calibration.mode, sizeof(calibration.mode), APP_ENV_CALIBRATION_MODE_NORMAL);
    copy_string(calibration.target, sizeof(calibration.target), APP_ENV_METRIC_PAR);
    calibration.reference_value = 0.0f;
    calibration.par_umol_m2_s = default_metric_calibration(APP_ENV_PAR_SCALE);
    calibration.soil_moisture_percent = default_metric_calibration();
    calibration.soil_temperature_c = default_metric_calibration();
    calibration.soil_ec_us_cm = default_metric_calibration();
    calibration.soil_ph = default_metric_calibration();
    calibration.soil_n_mg_kg = default_metric_calibration();
    calibration.soil_p_mg_kg = default_metric_calibration();
    calibration.soil_k_mg_kg = default_metric_calibration();
    return calibration;
}

static app_env_runtime_config_t default_runtime_config()
{
    app_env_runtime_config_t config = {};
    config.valid = true;
    config.received_from_mqtt = false;
    copy_string(config.ntp_server, sizeof(config.ntp_server), "pool.ntp.org");
    config.timezone_offset_sec = 32400;
    config.ota_check_interval_sec = APP_ENV_DEFAULT_OTA_CHECK_INTERVAL_SEC;
    config.sleep_sec = sanitize_sleep_sec(APP_ENV_SLEEP_SEC);
    config.par.enabled = APP_ENV_PAR_ENABLED;
    config.par.modbus_slave_id = APP_ENV_PAR_MODBUS_SLAVE_ID;
    config.par.modbus_function = APP_ENV_PAR_MODBUS_FUNCTION;
    config.par.register_address = APP_ENV_PAR_REGISTER;
    config.soil.enabled = APP_ENV_SOIL_RS485_ENABLED;
    config.soil.modbus_slave_id = APP_ENV_SOIL_MODBUS_SLAVE_ID;
    config.soil.modbus_function = APP_ENV_SOIL_MODBUS_FUNCTION;
    config.soil.start_register = APP_ENV_SOIL_MODBUS_START_REGISTER;
    config.calibration = default_calibration();
    return config;
}

static void parse_metric_calibration(JsonObjectConst parent,
                                     const char *metric,
                                     app_env_metric_calibration_t &calibration)
{
    if (!parent[metric].is<JsonObjectConst>())
    {
        return;
    }
    JsonObjectConst metric_json = parent[metric].as<JsonObjectConst>();
    if (metric_json["calibrated"].is<bool>())
    {
        calibration.calibrated = metric_json["calibrated"].as<bool>();
    }
    if (metric_json["scale"].is<float>() || metric_json["scale"].is<int>())
    {
        calibration.scale = constrain(metric_json["scale"].as<float>(), 0.0001f, 100000.0f);
    }
    if (metric_json["offset"].is<float>() || metric_json["offset"].is<int>())
    {
        calibration.offset = constrain(metric_json["offset"].as<float>(), -100000.0f, 100000.0f);
    }
}

static app_env_metric_calibration_t *mutable_metric_calibration(app_env_calibration_config_t &calibration,
                                                                const char *metric)
{
    if (strcmp(metric, APP_ENV_METRIC_PAR) == 0)
    {
        return &calibration.par_umol_m2_s;
    }
    if (strcmp(metric, APP_ENV_METRIC_SOIL_MOISTURE) == 0)
    {
        return &calibration.soil_moisture_percent;
    }
    if (strcmp(metric, APP_ENV_METRIC_SOIL_TEMPERATURE) == 0)
    {
        return &calibration.soil_temperature_c;
    }
    if (strcmp(metric, APP_ENV_METRIC_SOIL_EC) == 0)
    {
        return &calibration.soil_ec_us_cm;
    }
    if (strcmp(metric, APP_ENV_METRIC_SOIL_PH) == 0)
    {
        return &calibration.soil_ph;
    }
    if (strcmp(metric, APP_ENV_METRIC_SOIL_N) == 0)
    {
        return &calibration.soil_n_mg_kg;
    }
    if (strcmp(metric, APP_ENV_METRIC_SOIL_P) == 0)
    {
        return &calibration.soil_p_mg_kg;
    }
    if (strcmp(metric, APP_ENV_METRIC_SOIL_K) == 0)
    {
        return &calibration.soil_k_mg_kg;
    }
    return nullptr;
}

const app_env_metric_calibration_t &app_env_runtime_config_metric_calibration(const app_env_runtime_config_t &config,
                                                                              const char *metric)
{
    app_env_metric_calibration_t *calibration = mutable_metric_calibration(
        const_cast<app_env_calibration_config_t &>(config.calibration),
        metric);
    return calibration != nullptr ? *calibration : s_fallback_metric;
}

void app_env_runtime_config_init()
{
    s_runtime_config = default_runtime_config();
    if (app_env_runtime_config_load_saved())
    {
        Serial.printf("Loaded ENV runtime config: sleep=%lu par=%s soil=%s mode=%s target=%s\n",
                      static_cast<unsigned long>(s_runtime_config.sleep_sec),
                      s_runtime_config.par.enabled ? "true" : "false",
                      s_runtime_config.soil.enabled ? "true" : "false",
                      s_runtime_config.calibration.mode,
                      s_runtime_config.calibration.target);
    }
}

void app_env_runtime_config_mark_waiting()
{
    s_runtime_config.received_from_mqtt = false;
}

bool app_env_runtime_config_apply_json(const uint8_t *payload, size_t length)
{
    if (payload == nullptr || length == 0)
    {
        return false;
    }

    JsonDocument doc;
    const DeserializationError error = deserializeJson(doc, payload, length);
    if (error)
    {
        Serial.printf("Failed to parse ENV runtime config JSON: %s\n", error.c_str());
        return false;
    }

    app_env_runtime_config_t next = s_runtime_config;
    next.received_from_mqtt = true;

    const char *ntp_server = doc["ntp_server"] | next.ntp_server;
    copy_string(next.ntp_server, sizeof(next.ntp_server), ntp_server);
    next.timezone_offset_sec = doc["timezone_offset_sec"] | next.timezone_offset_sec;

    long ota_check_interval_sec = doc["ota_check_interval_sec"] | static_cast<long>(next.ota_check_interval_sec);
    next.ota_check_interval_sec = sanitize_ota_check_interval(static_cast<uint32_t>(max(0L, ota_check_interval_sec)));

    long sleep_sec = doc["sleep_sec"] | static_cast<long>(next.sleep_sec);
    next.sleep_sec = sanitize_sleep_sec(static_cast<uint32_t>(max(0L, sleep_sec)));

    if (doc["env_sensors"].is<JsonObjectConst>())
    {
        JsonObjectConst env_sensors = doc["env_sensors"].as<JsonObjectConst>();
        if (env_sensors["par"].is<JsonObjectConst>())
        {
            JsonObjectConst par = env_sensors["par"].as<JsonObjectConst>();
            next.par.enabled = par["enabled"] | next.par.enabled;
            next.par.modbus_slave_id = static_cast<uint8_t>(constrain(par["modbus_slave_id"] | next.par.modbus_slave_id, 1, 247));
            next.par.modbus_function = static_cast<uint8_t>(constrain(par["modbus_function"] | next.par.modbus_function, 3, 4));
            next.par.register_address = static_cast<uint16_t>(constrain(par["register"] | next.par.register_address, 0, 65535));
        }
        if (env_sensors["soil"].is<JsonObjectConst>())
        {
            JsonObjectConst soil = env_sensors["soil"].as<JsonObjectConst>();
            next.soil.enabled = soil["enabled"] | next.soil.enabled;
            next.soil.modbus_slave_id = static_cast<uint8_t>(constrain(soil["modbus_slave_id"] | next.soil.modbus_slave_id, 1, 247));
            next.soil.modbus_function = static_cast<uint8_t>(constrain(soil["modbus_function"] | next.soil.modbus_function, 3, 4));
            next.soil.start_register = static_cast<uint16_t>(constrain(soil["start_register"] | next.soil.start_register, 0, 65535));
        }
    }

    if (doc["env_calibration"].is<JsonObjectConst>())
    {
        JsonObjectConst calibration_json = doc["env_calibration"].as<JsonObjectConst>();
        app_env_calibration_config_t calibration = next.calibration;

        const char *mode = calibration_json["mode"] | calibration.mode;
        if (mode != nullptr && calibration_mode_is_valid(mode))
        {
            copy_string(calibration.mode, sizeof(calibration.mode), mode);
        }

        const char *request_id = calibration_json["request_id"] | calibration.request_id;
        copy_string(calibration.request_id, sizeof(calibration.request_id), request_id);

        const char *target = calibration_json["target"] | calibration.target;
        if (app_env_metric_is_supported(target))
        {
            copy_string(calibration.target, sizeof(calibration.target), target);
        }

        if (calibration_json["reference_value"].is<float>() || calibration_json["reference_value"].is<int>())
        {
            calibration.reference_value = constrain(calibration_json["reference_value"].as<float>(), -100000.0f, 100000.0f);
        }

        parse_metric_calibration(calibration_json, APP_ENV_METRIC_PAR, calibration.par_umol_m2_s);
        parse_metric_calibration(calibration_json, APP_ENV_METRIC_SOIL_MOISTURE, calibration.soil_moisture_percent);
        parse_metric_calibration(calibration_json, APP_ENV_METRIC_SOIL_TEMPERATURE, calibration.soil_temperature_c);
        parse_metric_calibration(calibration_json, APP_ENV_METRIC_SOIL_EC, calibration.soil_ec_us_cm);
        parse_metric_calibration(calibration_json, APP_ENV_METRIC_SOIL_PH, calibration.soil_ph);
        parse_metric_calibration(calibration_json, APP_ENV_METRIC_SOIL_N, calibration.soil_n_mg_kg);
        parse_metric_calibration(calibration_json, APP_ENV_METRIC_SOIL_P, calibration.soil_p_mg_kg);
        parse_metric_calibration(calibration_json, APP_ENV_METRIC_SOIL_K, calibration.soil_k_mg_kg);

        if (strcmp(calibration.mode, APP_ENV_CALIBRATION_MODE_RESET) == 0)
        {
            calibration = default_calibration();
        }

        next.calibration = calibration;
    }

    next.valid = true;
    s_runtime_config = next;
    app_env_runtime_config_save_current();
    Serial.printf("ENV runtime config updated: sleep=%lu par=%s soil=%s mode=%s target=%s\n",
                  static_cast<unsigned long>(s_runtime_config.sleep_sec),
                  s_runtime_config.par.enabled ? "true" : "false",
                  s_runtime_config.soil.enabled ? "true" : "false",
                  s_runtime_config.calibration.mode,
                  s_runtime_config.calibration.target);
    return true;
}

bool app_env_runtime_config_load_saved()
{
    if (!LittleFS.exists(APP_ENV_RUNTIME_CONFIG_FILE))
    {
        return false;
    }

    File file = LittleFS.open(APP_ENV_RUNTIME_CONFIG_FILE, "r");
    if (!file)
    {
        return false;
    }

    app_env_runtime_config_store_t store = {};
    const size_t read_size = file.read(reinterpret_cast<uint8_t *>(&store), sizeof(store));
    file.close();
    if (read_size != sizeof(store) ||
        store.magic != APP_ENV_RUNTIME_CONFIG_STORE_MAGIC ||
        store.version != APP_ENV_RUNTIME_CONFIG_STORE_VERSION ||
        store.config_size != sizeof(app_env_runtime_config_t))
    {
        return false;
    }

    const uint32_t crc = AppUtils().crc32(reinterpret_cast<const uint8_t *>(&store.config), sizeof(store.config));
    if (crc != store.crc32)
    {
        Serial.println("Saved ENV runtime config CRC mismatch");
        return false;
    }

    if (!calibration_mode_is_valid(store.config.calibration.mode))
    {
        copy_string(store.config.calibration.mode,
                    sizeof(store.config.calibration.mode),
                    APP_ENV_CALIBRATION_MODE_NORMAL);
    }
    if (!app_env_metric_is_supported(store.config.calibration.target))
    {
        copy_string(store.config.calibration.target,
                    sizeof(store.config.calibration.target),
                    APP_ENV_METRIC_PAR);
    }
    s_runtime_config = store.config;
    s_runtime_config.valid = true;
    return true;
}

bool app_env_runtime_config_save_current()
{
    app_env_runtime_config_store_t store = {};
    store.magic = APP_ENV_RUNTIME_CONFIG_STORE_MAGIC;
    store.version = APP_ENV_RUNTIME_CONFIG_STORE_VERSION;
    store.config_size = sizeof(app_env_runtime_config_t);
    store.config = s_runtime_config;
    store.crc32 = AppUtils().crc32(reinterpret_cast<const uint8_t *>(&store.config), sizeof(store.config));

    File file = LittleFS.open(APP_ENV_RUNTIME_CONFIG_FILE, "w");
    if (!file)
    {
        return false;
    }
    const size_t written = file.write(reinterpret_cast<const uint8_t *>(&store), sizeof(store));
    file.close();
    return written == sizeof(store);
}

bool app_env_runtime_config_update_metric_calibration(const char *metric,
                                                      float scale,
                                                      float offset,
                                                      bool calibrated,
                                                      const char *last_request_id)
{
    app_env_metric_calibration_t *metric_calibration = mutable_metric_calibration(s_runtime_config.calibration, metric);
    if (metric_calibration == nullptr)
    {
        return false;
    }

    metric_calibration->scale = constrain(scale, 0.0001f, 100000.0f);
    metric_calibration->offset = constrain(offset, -100000.0f, 100000.0f);
    metric_calibration->calibrated = calibrated;
    copy_string(s_runtime_config.calibration.mode,
                sizeof(s_runtime_config.calibration.mode),
                APP_ENV_CALIBRATION_MODE_NORMAL);
    copy_string(s_runtime_config.calibration.request_id,
                sizeof(s_runtime_config.calibration.request_id),
                "");
    if (last_request_id != nullptr)
    {
        copy_string(s_runtime_config.calibration.last_request_id,
                    sizeof(s_runtime_config.calibration.last_request_id),
                    last_request_id);
    }
    return app_env_runtime_config_save_current();
}

bool app_env_runtime_config_is_valid()
{
    return s_runtime_config.valid;
}

bool app_env_runtime_config_is_received()
{
    return s_runtime_config.received_from_mqtt;
}

const app_env_runtime_config_t &app_env_runtime_config_get()
{
    return s_runtime_config;
}
