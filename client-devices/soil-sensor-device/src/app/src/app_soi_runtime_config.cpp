#include "app_soi_runtime_config.h"

#include <ArduinoJson.h>
#include <LittleFS.h>
#include <stdio.h>
#include <string.h>

#include "app_utils.h"

#define APP_SOI_RUNTIME_CONFIG_FILE "/.soi_runtime_config"
#define APP_SOI_RUNTIME_CONFIG_STORE_MAGIC 0x534F4943UL
#define APP_SOI_RUNTIME_CONFIG_STORE_VERSION 1

static app_soi_runtime_config_t s_runtime_config;

typedef struct
{
    uint32_t magic;
    uint16_t version;
    uint16_t config_size;
    app_soi_runtime_config_t config;
    uint32_t crc32;
} app_soi_runtime_config_store_t;

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
    if (sleep_sec < APP_SOI_MIN_SLEEP_SEC)
    {
        return APP_SOI_MIN_SLEEP_SEC;
    }
    if (sleep_sec > APP_SOI_MAX_SLEEP_SEC)
    {
        return APP_SOI_MAX_SLEEP_SEC;
    }
    return sleep_sec;
}

static uint32_t sanitize_ota_check_interval(uint32_t interval_sec)
{
    if (interval_sec < APP_SOI_MIN_OTA_CHECK_INTERVAL_SEC)
    {
        return APP_SOI_MIN_OTA_CHECK_INTERVAL_SEC;
    }
    if (interval_sec > APP_SOI_MAX_OTA_CHECK_INTERVAL_SEC)
    {
        return APP_SOI_MAX_OTA_CHECK_INTERVAL_SEC;
    }
    return interval_sec;
}

static bool calibration_values_are_valid(uint16_t dry_raw, uint16_t wet_raw, uint16_t min_delta_raw)
{
    return dry_raw > wet_raw && static_cast<uint16_t>(dry_raw - wet_raw) >= min_delta_raw;
}

static bool calibration_mode_is_valid(const char *mode)
{
    return strcmp(mode, APP_SOI_CALIBRATION_MODE_NORMAL) == 0 ||
           strcmp(mode, APP_SOI_CALIBRATION_MODE_CAPTURE_DRY) == 0 ||
           strcmp(mode, APP_SOI_CALIBRATION_MODE_CAPTURE_WET) == 0 ||
           strcmp(mode, APP_SOI_CALIBRATION_MODE_RESET) == 0;
}

static app_soi_soil_calibration_config_t default_soil_calibration()
{
    app_soi_soil_calibration_config_t calibration = {};
    calibration.calibrated = false;
    copy_string(calibration.mode, sizeof(calibration.mode), APP_SOI_CALIBRATION_MODE_NORMAL);
    calibration.dry_raw = APP_SOI_MOISTURE_DRY_RAW;
    calibration.wet_raw = APP_SOI_MOISTURE_WET_RAW;
    calibration.min_delta_raw = 80;
    calibration.drift_tolerance_raw = 120;
    calibration.sample_count = APP_SOI_MOISTURE_SAMPLE_COUNT;
    calibration.sample_interval_ms = APP_SOI_MOISTURE_SAMPLE_INTERVAL_MS;
    return calibration;
}

static app_soi_runtime_config_t default_runtime_config()
{
    app_soi_runtime_config_t config = {};
    config.valid = true;
    config.received_from_mqtt = false;
    copy_string(config.ntp_server, sizeof(config.ntp_server), "pool.ntp.org");
    config.timezone_offset_sec = 32400;
    config.ota_check_interval_sec = APP_SOI_DEFAULT_OTA_CHECK_INTERVAL_SEC;
    config.sleep_sec = sanitize_sleep_sec(APP_SOI_SLEEP_SEC);
    config.soil_calibration = default_soil_calibration();
    return config;
}

void app_soi_runtime_config_init()
{
    s_runtime_config = default_runtime_config();

    if (app_soi_runtime_config_load_saved())
    {
        Serial.printf("Loaded SOI runtime config: sleep=%lu ota=%lu calibrated=%s dry=%u wet=%u mode=%s\n",
                      static_cast<unsigned long>(s_runtime_config.sleep_sec),
                      static_cast<unsigned long>(s_runtime_config.ota_check_interval_sec),
                      s_runtime_config.soil_calibration.calibrated ? "true" : "false",
                      static_cast<unsigned int>(s_runtime_config.soil_calibration.dry_raw),
                      static_cast<unsigned int>(s_runtime_config.soil_calibration.wet_raw),
                      s_runtime_config.soil_calibration.mode);
    }
}

void app_soi_runtime_config_mark_waiting()
{
    s_runtime_config.received_from_mqtt = false;
}

bool app_soi_runtime_config_apply_json(const uint8_t *payload, size_t length)
{
    if (payload == nullptr || length == 0)
    {
        return false;
    }

    JsonDocument doc;
    const DeserializationError error = deserializeJson(doc, payload, length);
    if (error)
    {
        Serial.printf("Failed to parse SOI runtime config JSON: %s\n", error.c_str());
        return false;
    }

    app_soi_runtime_config_t next = s_runtime_config;
    next.received_from_mqtt = true;

    const char *ntp_server = doc["ntp_server"] | next.ntp_server;
    copy_string(next.ntp_server, sizeof(next.ntp_server), ntp_server);
    next.timezone_offset_sec = doc["timezone_offset_sec"] | next.timezone_offset_sec;

    long ota_check_interval_sec = doc["ota_check_interval_sec"] | static_cast<long>(next.ota_check_interval_sec);
    if (ota_check_interval_sec < 0)
    {
        ota_check_interval_sec = 0;
    }
    next.ota_check_interval_sec = sanitize_ota_check_interval(static_cast<uint32_t>(ota_check_interval_sec));

    long sleep_sec = doc["sleep_sec"] | static_cast<long>(next.sleep_sec);
    if (sleep_sec < 0)
    {
        sleep_sec = 0;
    }
    next.sleep_sec = sanitize_sleep_sec(static_cast<uint32_t>(sleep_sec));

    if (doc["soil_calibration"].is<JsonObjectConst>())
    {
        JsonObjectConst calibration_json = doc["soil_calibration"].as<JsonObjectConst>();
        app_soi_soil_calibration_config_t calibration = next.soil_calibration;

        const char *mode = calibration_json["mode"] | (calibration_json["calibration_mode"] | calibration.mode);
        if (mode != nullptr && calibration_mode_is_valid(mode))
        {
            copy_string(calibration.mode, sizeof(calibration.mode), mode);
        }

        const char *request_id = calibration_json["request_id"] | calibration.request_id;
        copy_string(calibration.request_id, sizeof(calibration.request_id), request_id);

        int min_delta_raw = calibration_json["min_delta_raw"] | calibration.min_delta_raw;
        calibration.min_delta_raw = static_cast<uint16_t>(constrain(min_delta_raw, 10, 2000));

        int drift_tolerance_raw = calibration_json["drift_tolerance_raw"] | calibration.drift_tolerance_raw;
        calibration.drift_tolerance_raw = static_cast<uint16_t>(constrain(drift_tolerance_raw, 10, 2000));

        int sample_count = calibration_json["sample_count"] | calibration.sample_count;
        calibration.sample_count = static_cast<uint8_t>(constrain(sample_count, 1, 100));

        int sample_interval_ms = calibration_json["sample_interval_ms"] | calibration.sample_interval_ms;
        calibration.sample_interval_ms = static_cast<uint16_t>(constrain(sample_interval_ms, 0, 1000));

        const bool has_manual_dry = calibration_json["dry_raw"].is<int>();
        const bool has_manual_wet = calibration_json["wet_raw"].is<int>();
        if (has_manual_dry)
        {
            int dry_raw = calibration_json["dry_raw"] | calibration.dry_raw;
            calibration.dry_raw = static_cast<uint16_t>(constrain(dry_raw, 1, 4095));
        }
        if (has_manual_wet)
        {
            int wet_raw = calibration_json["wet_raw"] | calibration.wet_raw;
            calibration.wet_raw = static_cast<uint16_t>(constrain(wet_raw, 0, 4094));
        }

        if (strcmp(calibration.mode, APP_SOI_CALIBRATION_MODE_RESET) == 0)
        {
            calibration = default_soil_calibration();
        }
        else
        {
            const bool values_valid = calibration_values_are_valid(calibration.dry_raw,
                                                                   calibration.wet_raw,
                                                                   calibration.min_delta_raw);
            if (calibration_json["calibrated"].is<bool>())
            {
                calibration.calibrated = calibration_json["calibrated"].as<bool>() && values_valid;
            }
            else if ((has_manual_dry || has_manual_wet) && values_valid)
            {
                calibration.calibrated = true;
            }
            if (!values_valid)
            {
                calibration.calibrated = false;
                Serial.println("SOI soil calibration values are not far enough apart; marked as uncalibrated");
            }
        }

        next.soil_calibration = calibration;
    }

    next.valid = true;
    s_runtime_config = next;
    app_soi_runtime_config_save_current();

    Serial.printf("SOI runtime config updated: sleep=%lu ota=%lu calibrated=%s mode=%s dry=%u wet=%u samples=%u interval=%u\n",
                  static_cast<unsigned long>(s_runtime_config.sleep_sec),
                  static_cast<unsigned long>(s_runtime_config.ota_check_interval_sec),
                  s_runtime_config.soil_calibration.calibrated ? "true" : "false",
                  s_runtime_config.soil_calibration.mode,
                  static_cast<unsigned int>(s_runtime_config.soil_calibration.dry_raw),
                  static_cast<unsigned int>(s_runtime_config.soil_calibration.wet_raw),
                  static_cast<unsigned int>(s_runtime_config.soil_calibration.sample_count),
                  static_cast<unsigned int>(s_runtime_config.soil_calibration.sample_interval_ms));
    return true;
}

bool app_soi_runtime_config_load_saved()
{
    if (!LittleFS.exists(APP_SOI_RUNTIME_CONFIG_FILE))
    {
        Serial.println("Saved SOI runtime config does not exist");
        return false;
    }

    File file = LittleFS.open(APP_SOI_RUNTIME_CONFIG_FILE, "r");
    if (!file)
    {
        Serial.println("Failed to open saved SOI runtime config");
        return false;
    }

    app_soi_runtime_config_store_t store = {};
    const size_t read_size = file.read(reinterpret_cast<uint8_t *>(&store), sizeof(store));
    file.close();
    if (read_size != sizeof(store))
    {
        Serial.printf("Saved SOI runtime config size mismatch: %u/%u\n",
                      static_cast<unsigned int>(read_size),
                      static_cast<unsigned int>(sizeof(store)));
        return false;
    }
    if (store.magic != APP_SOI_RUNTIME_CONFIG_STORE_MAGIC ||
        store.version != APP_SOI_RUNTIME_CONFIG_STORE_VERSION ||
        store.config_size != sizeof(app_soi_runtime_config_t))
    {
        Serial.println("Saved SOI runtime config header is invalid");
        return false;
    }

    const uint32_t expected_crc = AppUtils().crc32(reinterpret_cast<const uint8_t *>(&store.config), sizeof(store.config));
    if (store.crc32 != expected_crc)
    {
        Serial.printf("Saved SOI runtime config CRC mismatch: actual=0x%08lX expected=0x%08lX\n",
                      static_cast<unsigned long>(store.crc32),
                      static_cast<unsigned long>(expected_crc));
        return false;
    }

    if (!calibration_mode_is_valid(store.config.soil_calibration.mode))
    {
        copy_string(store.config.soil_calibration.mode,
                    sizeof(store.config.soil_calibration.mode),
                    APP_SOI_CALIBRATION_MODE_NORMAL);
    }
    if (!calibration_values_are_valid(store.config.soil_calibration.dry_raw,
                                      store.config.soil_calibration.wet_raw,
                                      store.config.soil_calibration.min_delta_raw))
    {
        store.config.soil_calibration.calibrated = false;
    }
    store.config.sleep_sec = sanitize_sleep_sec(store.config.sleep_sec);
    store.config.ota_check_interval_sec = sanitize_ota_check_interval(store.config.ota_check_interval_sec);
    s_runtime_config = store.config;
    return true;
}

bool app_soi_runtime_config_save_current()
{
    app_soi_runtime_config_store_t store = {};
    store.magic = APP_SOI_RUNTIME_CONFIG_STORE_MAGIC;
    store.version = APP_SOI_RUNTIME_CONFIG_STORE_VERSION;
    store.config_size = sizeof(app_soi_runtime_config_t);
    store.config = s_runtime_config;
    store.crc32 = AppUtils().crc32(reinterpret_cast<const uint8_t *>(&store.config), sizeof(store.config));

    File file = LittleFS.open(APP_SOI_RUNTIME_CONFIG_FILE, "w");
    if (!file)
    {
        Serial.println("Failed to open SOI runtime config for write");
        return false;
    }
    const size_t write_size = file.write(reinterpret_cast<const uint8_t *>(&store), sizeof(store));
    file.close();
    if (write_size != sizeof(store))
    {
        Serial.println("Failed to write complete SOI runtime config");
        return false;
    }
    return true;
}

bool app_soi_runtime_config_update_soil_calibration(uint16_t dry_raw,
                                                    uint16_t wet_raw,
                                                    bool calibrated,
                                                    const char *last_request_id)
{
    app_soi_soil_calibration_config_t calibration = s_runtime_config.soil_calibration;
    calibration.dry_raw = dry_raw;
    calibration.wet_raw = wet_raw;
    calibration.calibrated = calibrated &&
                             calibration_values_are_valid(calibration.dry_raw,
                                                          calibration.wet_raw,
                                                          calibration.min_delta_raw);
    copy_string(calibration.mode, sizeof(calibration.mode), APP_SOI_CALIBRATION_MODE_NORMAL);
    copy_string(calibration.request_id, sizeof(calibration.request_id), "");
    if (last_request_id != nullptr && strlen(last_request_id) > 0)
    {
        copy_string(calibration.last_request_id, sizeof(calibration.last_request_id), last_request_id);
    }

    s_runtime_config.soil_calibration = calibration;
    return app_soi_runtime_config_save_current();
}

bool app_soi_runtime_config_is_valid()
{
    return s_runtime_config.valid;
}

bool app_soi_runtime_config_is_received()
{
    return s_runtime_config.received_from_mqtt;
}

const app_soi_runtime_config_t &app_soi_runtime_config_get()
{
    return s_runtime_config;
}
