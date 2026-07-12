#include "app.h"

#include <Arduino.h>
#include <string.h>

#include "app_def.h"
#include "app_device.h"
#include "app_network.h"
#include "app_soi_runtime_config.h"

struct SoilMoistureSample
{
    bool ok = false;
    uint16_t raw = 0;
    uint8_t percent = 0;
    bool calibration_required = false;
    bool calibration_capture_applied = false;
    bool calibration_capture_duplicate = false;
    bool calibration_capture_error = false;
    const char *calibration_capture = "none";
};

static uint16_t read_moisture_raw_average(uint8_t sample_count, uint16_t interval_ms)
{
    uint32_t sum = 0;
    const uint8_t samples = sample_count == 0 ? 1 : sample_count;
    for (uint8_t i = 0; i < samples; ++i)
    {
        sum += analogRead(APP_SOI_MOISTURE_PIN);
        if (interval_ms > 0 && i + 1 < samples)
        {
            delay(interval_ms);
        }
    }
    return static_cast<uint16_t>(sum / samples);
}

static uint8_t moisture_percent_from_raw(uint16_t raw, uint16_t dry_raw, uint16_t wet_raw)
{
    if (dry_raw <= wet_raw)
    {
        return 0;
    }
    const uint16_t constrained_raw = constrain(raw, wet_raw, dry_raw);
    const long percent = map(constrained_raw,
                             dry_raw,
                             wet_raw,
                             0,
                             100);
    return static_cast<uint8_t>(constrain(percent, 0, 100));
}

class SoilSensorDevice : public AppDevice
{
public:
    bool apply_runtime_config_json(const uint8_t *payload, size_t length) override
    {
        return app_soi_runtime_config_apply_json(payload, length);
    }

    bool has_valid_runtime_config() const override
    {
        return app_soi_runtime_config_is_valid();
    }

    bool is_runtime_config_received() const override
    {
        return app_soi_runtime_config_is_received();
    }

protected:
    const char *device_name() const override
    {
        return "INA Soil Sensor";
    }

    bool on_initialize() override
    {
        app_soi_runtime_config_init();
        analogSetPinAttenuation(APP_SOI_MOISTURE_PIN, ADC_11db);
        analogReadResolution(12);
        const app_soi_soil_calibration_config_t &calibration = app_soi_runtime_config_get().soil_calibration;
        Serial.printf("SOI moisture sensor initialized: pin=%d calibrated=%s dry=%u wet=%u samples=%u interval=%u ms\n",
                      APP_SOI_MOISTURE_PIN,
                      calibration.calibrated ? "true" : "false",
                      static_cast<unsigned int>(calibration.dry_raw),
                      static_cast<unsigned int>(calibration.wet_raw),
                      static_cast<unsigned int>(calibration.sample_count),
                      static_cast<unsigned int>(calibration.sample_interval_ms));
        return true;
    }

    void prepare_runtime_config_request() override
    {
        app_soi_runtime_config_mark_waiting();
    }

    void on_runtime_config_ready(bool config_received) override
    {
        const app_soi_runtime_config_t &runtime_config = app_soi_runtime_config_get();
        const app_soi_soil_calibration_config_t &calibration = runtime_config.soil_calibration;
        Serial.printf("Runtime config ready: received=%s valid=%s\n",
                      config_received ? "true" : "false",
                      runtime_config.valid ? "true" : "false");
        Serial.printf("SOI calibration: calibrated=%s mode=%s dry=%u wet=%u min_delta=%u sample_count=%u interval=%u\n",
                      calibration.calibrated ? "true" : "false",
                      calibration.mode,
                      static_cast<unsigned int>(calibration.dry_raw),
                      static_cast<unsigned int>(calibration.wet_raw),
                      static_cast<unsigned int>(calibration.min_delta_raw),
                      static_cast<unsigned int>(calibration.sample_count),
                      static_cast<unsigned int>(calibration.sample_interval_ms));
    }

    const char *runtime_ntp_server() const override
    {
        return app_soi_runtime_config_get().ntp_server;
    }

    int32_t runtime_timezone_offset_sec() const override
    {
        return app_soi_runtime_config_get().timezone_offset_sec;
    }

    AppDeviceCycleResult run_device_cycle(const AppDeviceWakeContext &context) override
    {
        (void)context;
        const app_soi_runtime_config_t &runtime_config = app_soi_runtime_config_get();
        const app_soi_soil_calibration_config_t &calibration = runtime_config.soil_calibration;

        m_sample = {};
        m_sample.raw = read_moisture_raw_average(calibration.sample_count, calibration.sample_interval_ms);
        apply_calibration_mode(m_sample.raw);

        const app_soi_soil_calibration_config_t &updated_calibration = app_soi_runtime_config_get().soil_calibration;
        m_sample.percent = moisture_percent_from_raw(m_sample.raw,
                                                     updated_calibration.dry_raw,
                                                     updated_calibration.wet_raw);
        m_sample.ok = true;
        m_sample.calibration_required = !updated_calibration.calibrated;

        AppDeviceCycleResult result = {};
        result.next_sleep_sec = app_soi_runtime_config_get().sleep_sec;
        result.publish_debug_log = false;
        return result;
    }

    bool publish_device_status(const AppDeviceWakeContext &context,
                               const AppDeviceCycleResult &cycle_result) override
    {
        const app_soi_runtime_config_t &runtime_config = app_soi_runtime_config_get();
        const app_soi_soil_calibration_config_t &calibration = runtime_config.soil_calibration;
        char payload[1200];
        snprintf(payload,
                 sizeof(payload),
                 "{\"seq\":%lu,\"device_kind\":\"%s\",\"firmware_version\":\"%s\",\"firmware_build_id\":\"%s\",\"network_connected\":%s,\"runtime_config_valid\":%s,\"config_received\":%s,\"time_synced\":%s,\"ota_update_attempted\":%s,\"next_sleep_sec\":%lu,\"ota_check_interval_sec\":%lu,\"sensor_model\":\"Analog-Soil-Moisture\",\"soil_moisture_ok\":%s,\"soil_moisture_percent\":%u,\"last_soil_moisture\":%u,\"raw_soil_moisture\":%u,\"soil_moisture_estimated\":%s,\"soil_calibration_required\":%s,\"soil_calibration_calibrated\":%s,\"soil_calibration_mode\":\"%s\",\"soil_calibration_capture\":\"%s\",\"soil_calibration_applied\":%s,\"soil_calibration_duplicate\":%s,\"soil_calibration_error\":%s,\"soil_calibration_dry_raw\":%u,\"soil_calibration_wet_raw\":%u,\"soil_calibration_min_delta_raw\":%u,\"soil_calibration_sample_count\":%u,\"soil_calibration_sample_interval_ms\":%u}",
                 static_cast<unsigned long>(context.seq_id),
                 APP_DEVICE_KIND,
                 APP_FIRMWARE_VERSION,
                 APP_FIRMWARE_BUILD_ID,
                 context.network_connected ? "true" : "false",
                 runtime_config.valid ? "true" : "false",
                 context.config_received ? "true" : "false",
                 context.time_synced ? "true" : "false",
                 context.ota_update_attempted ? "true" : "false",
                 static_cast<unsigned long>(cycle_result.next_sleep_sec),
                 static_cast<unsigned long>(runtime_config.ota_check_interval_sec),
                 m_sample.ok ? "true" : "false",
                 static_cast<unsigned int>(m_sample.percent),
                 static_cast<unsigned int>(m_sample.percent),
                 static_cast<unsigned int>(m_sample.raw),
                 m_sample.calibration_required ? "true" : "false",
                 m_sample.calibration_required ? "true" : "false",
                 calibration.calibrated ? "true" : "false",
                 calibration.mode,
                 m_sample.calibration_capture,
                 m_sample.calibration_capture_applied ? "true" : "false",
                 m_sample.calibration_capture_duplicate ? "true" : "false",
                 m_sample.calibration_capture_error ? "true" : "false",
                 static_cast<unsigned int>(calibration.dry_raw),
                 static_cast<unsigned int>(calibration.wet_raw),
                 static_cast<unsigned int>(calibration.min_delta_raw),
                 static_cast<unsigned int>(calibration.sample_count),
                 static_cast<unsigned int>(calibration.sample_interval_ms));

        Serial.printf("Sending status: %s\n", payload);
        const bool sent = app_network_send(APP_MSG_TYPE_STATUS,
                                           reinterpret_cast<const uint8_t *>(payload),
                                           strlen(payload),
                                           context.seq_id);
        if (sent)
        {
            app_network_flush(APP_MQTT_STATUS_PUBLISH_DRAIN_MS);
        }
        return sent;
    }

private:
    SoilMoistureSample m_sample = {};

    void apply_calibration_mode(uint16_t raw)
    {
        const app_soi_soil_calibration_config_t &calibration = app_soi_runtime_config_get().soil_calibration;
        if (strcmp(calibration.mode, APP_SOI_CALIBRATION_MODE_CAPTURE_DRY) != 0 &&
            strcmp(calibration.mode, APP_SOI_CALIBRATION_MODE_CAPTURE_WET) != 0)
        {
            return;
        }

        const bool capture_dry = strcmp(calibration.mode, APP_SOI_CALIBRATION_MODE_CAPTURE_DRY) == 0;
        m_sample.calibration_capture = capture_dry ? "dry" : "wet";

        if (strlen(calibration.request_id) > 0 &&
            strcmp(calibration.request_id, calibration.last_request_id) == 0)
        {
            m_sample.calibration_capture_duplicate = true;
            app_soi_runtime_config_update_soil_calibration(calibration.dry_raw,
                                                           calibration.wet_raw,
                                                           calibration.calibrated,
                                                           calibration.request_id);
            return;
        }

        uint16_t dry_raw = calibration.dry_raw;
        uint16_t wet_raw = calibration.wet_raw;
        if (capture_dry)
        {
            dry_raw = raw;
        }
        else
        {
            wet_raw = raw;
        }

        const bool calibrated = dry_raw > wet_raw &&
                                static_cast<uint16_t>(dry_raw - wet_raw) >= calibration.min_delta_raw;
        if (!calibrated)
        {
            m_sample.calibration_capture_error = true;
            Serial.printf("SOI calibration capture is not valid: dry=%u wet=%u min_delta=%u\n",
                          static_cast<unsigned int>(dry_raw),
                          static_cast<unsigned int>(wet_raw),
                          static_cast<unsigned int>(calibration.min_delta_raw));
            app_soi_runtime_config_update_soil_calibration(calibration.dry_raw,
                                                           calibration.wet_raw,
                                                           calibration.calibrated,
                                                           calibration.request_id);
            return;
        }

        m_sample.calibration_capture_applied =
            app_soi_runtime_config_update_soil_calibration(dry_raw,
                                                           wet_raw,
                                                           calibrated,
                                                           calibration.request_id);
    }
};

static SoilSensorDevice s_device;

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
}

void app_loop()
{
    s_device.loop();
}
