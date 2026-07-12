#include "app.h"

#include <Arduino.h>
#include <string.h>

#include "app_def.h"
#include "app_device.h"
#include "app_env_runtime_config.h"
#include "app_network.h"
#include "hal_rs485_modbus.h"

struct EnvironmentSensorSample
{
    bool par_ok = false;
    uint16_t raw_par = 0;
    float base_par_umol_m2_s = 0.0f;
    float par_umol_m2_s = 0.0f;

    bool soil_rs485_ok = false;
    uint16_t raw_soil_moisture = 0;
    uint16_t raw_soil_temperature = 0;
    uint16_t raw_soil_ec = 0;
    uint16_t raw_soil_ph = 0;
    uint16_t raw_soil_nitrogen = 0;
    uint16_t raw_soil_phosphorus = 0;
    uint16_t raw_soil_potassium = 0;
    float base_soil_moisture_percent = 0.0f;
    float base_soil_temperature_c = 0.0f;
    float base_soil_ec_us_cm = 0.0f;
    float base_soil_ph = 0.0f;
    float base_soil_n_mg_kg = 0.0f;
    float base_soil_p_mg_kg = 0.0f;
    float base_soil_k_mg_kg = 0.0f;
    float soil_moisture_percent = 0.0f;
    float soil_temperature_c = 0.0f;
    float soil_ec_us_cm = 0.0f;
    float soil_ph = 0.0f;
    float soil_n_mg_kg = 0.0f;
    float soil_p_mg_kg = 0.0f;
    float soil_k_mg_kg = 0.0f;

    bool calibration_capture_applied = false;
    bool calibration_capture_duplicate = false;
    bool calibration_capture_error = false;
};

static float scaled_tenths(uint16_t value)
{
    return static_cast<float>(value) / 10.0f;
}

static float scaled_signed_tenths(uint16_t value)
{
    return static_cast<float>(static_cast<int16_t>(value)) / 10.0f;
}

static float calibrated_value(float value, const app_env_metric_calibration_t &calibration)
{
    return value * calibration.scale + calibration.offset;
}

static bool soil_calibration_complete(const app_env_calibration_config_t &calibration)
{
    return calibration.soil_moisture_percent.calibrated &&
           calibration.soil_temperature_c.calibrated &&
           calibration.soil_ec_us_cm.calibrated &&
           calibration.soil_ph.calibrated &&
           calibration.soil_n_mg_kg.calibrated &&
           calibration.soil_p_mg_kg.calibrated &&
           calibration.soil_k_mg_kg.calibrated;
}

class EnvironmentSensorDevice : public AppDevice
{
public:
    bool apply_runtime_config_json(const uint8_t *payload, size_t length) override
    {
        return app_env_runtime_config_apply_json(payload, length);
    }

    bool has_valid_runtime_config() const override
    {
        return app_env_runtime_config_is_valid();
    }

    bool is_runtime_config_received() const override
    {
        return app_env_runtime_config_is_received();
    }

protected:
    const char *device_name() const override
    {
        return "INA Environment Sensor";
    }

    bool on_initialize() override
    {
        app_env_runtime_config_init();
        hal_rs485_modbus_config_t config = hal_rs485_modbus_default_config();
        return hal_rs485_modbus_init(&config);
    }

    void prepare_runtime_config_request() override
    {
        app_env_runtime_config_mark_waiting();
    }

    void on_runtime_config_ready(bool config_received) override
    {
        const app_env_runtime_config_t &config = app_env_runtime_config_get();
        Serial.printf("ENV runtime config ready: received=%s valid=%s sleep=%lu par=%s soil=%s mode=%s target=%s\n",
                      config_received ? "true" : "false",
                      config.valid ? "true" : "false",
                      static_cast<unsigned long>(config.sleep_sec),
                      config.par.enabled ? "true" : "false",
                      config.soil.enabled ? "true" : "false",
                      config.calibration.mode,
                      config.calibration.target);
    }

    const char *runtime_ntp_server() const override
    {
        return app_env_runtime_config_get().ntp_server;
    }

    int32_t runtime_timezone_offset_sec() const override
    {
        return app_env_runtime_config_get().timezone_offset_sec;
    }

    AppDeviceCycleResult run_device_cycle(const AppDeviceWakeContext &context) override
    {
        (void)context;
        const app_env_runtime_config_t &config = app_env_runtime_config_get();
        m_sample = {};

        if (config.par.enabled)
        {
            uint16_t par_registers[1] = {};
            m_sample.par_ok = hal_rs485_modbus_read_registers(config.par.modbus_slave_id,
                                                              config.par.modbus_function,
                                                              config.par.register_address,
                                                              1,
                                                              par_registers,
                                                              1);
            if (m_sample.par_ok)
            {
                m_sample.raw_par = par_registers[0];
                m_sample.base_par_umol_m2_s = static_cast<float>(m_sample.raw_par);
            }
        }

        if (config.soil.enabled)
        {
            uint16_t soil_registers[7] = {};
            m_sample.soil_rs485_ok = hal_rs485_modbus_read_registers(config.soil.modbus_slave_id,
                                                                     config.soil.modbus_function,
                                                                     config.soil.start_register,
                                                                     7,
                                                                     soil_registers,
                                                                     7);
            if (m_sample.soil_rs485_ok)
            {
                m_sample.raw_soil_moisture = soil_registers[0];
                m_sample.raw_soil_temperature = soil_registers[1];
                m_sample.raw_soil_ec = soil_registers[2];
                m_sample.raw_soil_ph = soil_registers[3];
                m_sample.raw_soil_nitrogen = soil_registers[4];
                m_sample.raw_soil_phosphorus = soil_registers[5];
                m_sample.raw_soil_potassium = soil_registers[6];
                m_sample.base_soil_moisture_percent = scaled_tenths(m_sample.raw_soil_moisture);
                m_sample.base_soil_temperature_c = scaled_signed_tenths(m_sample.raw_soil_temperature);
                m_sample.base_soil_ec_us_cm = static_cast<float>(m_sample.raw_soil_ec);
                m_sample.base_soil_ph = scaled_tenths(m_sample.raw_soil_ph);
                m_sample.base_soil_n_mg_kg = static_cast<float>(m_sample.raw_soil_nitrogen);
                m_sample.base_soil_p_mg_kg = static_cast<float>(m_sample.raw_soil_phosphorus);
                m_sample.base_soil_k_mg_kg = static_cast<float>(m_sample.raw_soil_potassium);
            }
        }

        apply_calibration_mode();
        apply_calibrations();

        AppDeviceCycleResult result = {};
        result.next_sleep_sec = app_env_runtime_config_get().sleep_sec;
        result.publish_debug_log = false;
        return result;
    }

    bool publish_device_status(const AppDeviceWakeContext &context,
                               const AppDeviceCycleResult &cycle_result) override
    {
        const app_env_runtime_config_t &config = app_env_runtime_config_get();
        const bool par_calibrated = config.calibration.par_umol_m2_s.calibrated;
        const bool soil_calibrated = soil_calibration_complete(config.calibration);
        const bool calibration_required = (config.par.enabled && !par_calibrated) ||
                                          (config.soil.enabled && !soil_calibrated);

        char payload[2000];
        snprintf(payload,
                 sizeof(payload),
                 "{\"seq\":%lu,\"device_kind\":\"%s\",\"firmware_version\":\"%s\",\"firmware_build_id\":\"%s\",\"network_connected\":%s,\"runtime_config_valid\":%s,\"config_received\":%s,\"time_synced\":%s,\"ota_update_attempted\":%s,\"next_sleep_sec\":%lu,\"ota_check_interval_sec\":%lu,\"sensor_model\":\"RS485-12V-ENV\",\"par_enabled\":%s,\"par_ok\":%s,\"par_modbus_slave_id\":%u,\"par_umol_m2_s\":%.1f,\"raw_par\":%u,\"soil_rs485_enabled\":%s,\"soil_rs485_ok\":%s,\"soil_rs485_modbus_slave_id\":%u,\"soil_moisture_percent\":%.1f,\"soil_temperature_c\":%.1f,\"soil_ec_us_cm\":%.1f,\"soil_ph\":%.2f,\"soil_n_mg_kg\":%.1f,\"soil_p_mg_kg\":%.1f,\"soil_k_mg_kg\":%.1f,\"raw_soil_moisture\":%u,\"raw_soil_temperature\":%u,\"raw_soil_ec\":%u,\"raw_soil_ph\":%u,\"raw_soil_nitrogen\":%u,\"raw_soil_phosphorus\":%u,\"raw_soil_potassium\":%u,\"env_calibration_required\":%s,\"env_calibration_mode\":\"%s\",\"env_calibration_target\":\"%s\",\"env_calibration_applied\":%s,\"env_calibration_duplicate\":%s,\"env_calibration_error\":%s,\"env_par_calibrated\":%s,\"env_soil_calibrated\":%s}",
                 static_cast<unsigned long>(context.seq_id),
                 APP_DEVICE_KIND,
                 APP_FIRMWARE_VERSION,
                 APP_FIRMWARE_BUILD_ID,
                 context.network_connected ? "true" : "false",
                 config.valid ? "true" : "false",
                 context.config_received ? "true" : "false",
                 context.time_synced ? "true" : "false",
                 context.ota_update_attempted ? "true" : "false",
                 static_cast<unsigned long>(cycle_result.next_sleep_sec),
                 static_cast<unsigned long>(config.ota_check_interval_sec),
                 config.par.enabled ? "true" : "false",
                 m_sample.par_ok ? "true" : "false",
                 static_cast<unsigned int>(config.par.modbus_slave_id),
                 m_sample.par_umol_m2_s,
                 static_cast<unsigned int>(m_sample.raw_par),
                 config.soil.enabled ? "true" : "false",
                 m_sample.soil_rs485_ok ? "true" : "false",
                 static_cast<unsigned int>(config.soil.modbus_slave_id),
                 m_sample.soil_moisture_percent,
                 m_sample.soil_temperature_c,
                 m_sample.soil_ec_us_cm,
                 m_sample.soil_ph,
                 m_sample.soil_n_mg_kg,
                 m_sample.soil_p_mg_kg,
                 m_sample.soil_k_mg_kg,
                 static_cast<unsigned int>(m_sample.raw_soil_moisture),
                 static_cast<unsigned int>(m_sample.raw_soil_temperature),
                 static_cast<unsigned int>(m_sample.raw_soil_ec),
                 static_cast<unsigned int>(m_sample.raw_soil_ph),
                 static_cast<unsigned int>(m_sample.raw_soil_nitrogen),
                 static_cast<unsigned int>(m_sample.raw_soil_phosphorus),
                 static_cast<unsigned int>(m_sample.raw_soil_potassium),
                 calibration_required ? "true" : "false",
                 config.calibration.mode,
                 config.calibration.target,
                 m_sample.calibration_capture_applied ? "true" : "false",
                 m_sample.calibration_capture_duplicate ? "true" : "false",
                 m_sample.calibration_capture_error ? "true" : "false",
                 par_calibrated ? "true" : "false",
                 soil_calibrated ? "true" : "false");

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
    EnvironmentSensorSample m_sample = {};

    void apply_calibrations()
    {
        const app_env_runtime_config_t &config = app_env_runtime_config_get();
        m_sample.par_umol_m2_s = calibrated_value(m_sample.base_par_umol_m2_s, config.calibration.par_umol_m2_s);
        m_sample.soil_moisture_percent = calibrated_value(m_sample.base_soil_moisture_percent, config.calibration.soil_moisture_percent);
        m_sample.soil_temperature_c = calibrated_value(m_sample.base_soil_temperature_c, config.calibration.soil_temperature_c);
        m_sample.soil_ec_us_cm = calibrated_value(m_sample.base_soil_ec_us_cm, config.calibration.soil_ec_us_cm);
        m_sample.soil_ph = calibrated_value(m_sample.base_soil_ph, config.calibration.soil_ph);
        m_sample.soil_n_mg_kg = calibrated_value(m_sample.base_soil_n_mg_kg, config.calibration.soil_n_mg_kg);
        m_sample.soil_p_mg_kg = calibrated_value(m_sample.base_soil_p_mg_kg, config.calibration.soil_p_mg_kg);
        m_sample.soil_k_mg_kg = calibrated_value(m_sample.base_soil_k_mg_kg, config.calibration.soil_k_mg_kg);
    }

    bool base_value_for_metric(const char *metric, float &value) const
    {
        if (strcmp(metric, APP_ENV_METRIC_PAR) == 0)
        {
            value = m_sample.base_par_umol_m2_s;
            return m_sample.par_ok;
        }
        if (strcmp(metric, APP_ENV_METRIC_SOIL_MOISTURE) == 0)
        {
            value = m_sample.base_soil_moisture_percent;
            return m_sample.soil_rs485_ok;
        }
        if (strcmp(metric, APP_ENV_METRIC_SOIL_TEMPERATURE) == 0)
        {
            value = m_sample.base_soil_temperature_c;
            return m_sample.soil_rs485_ok;
        }
        if (strcmp(metric, APP_ENV_METRIC_SOIL_EC) == 0)
        {
            value = m_sample.base_soil_ec_us_cm;
            return m_sample.soil_rs485_ok;
        }
        if (strcmp(metric, APP_ENV_METRIC_SOIL_PH) == 0)
        {
            value = m_sample.base_soil_ph;
            return m_sample.soil_rs485_ok;
        }
        if (strcmp(metric, APP_ENV_METRIC_SOIL_N) == 0)
        {
            value = m_sample.base_soil_n_mg_kg;
            return m_sample.soil_rs485_ok;
        }
        if (strcmp(metric, APP_ENV_METRIC_SOIL_P) == 0)
        {
            value = m_sample.base_soil_p_mg_kg;
            return m_sample.soil_rs485_ok;
        }
        if (strcmp(metric, APP_ENV_METRIC_SOIL_K) == 0)
        {
            value = m_sample.base_soil_k_mg_kg;
            return m_sample.soil_rs485_ok;
        }
        return false;
    }

    void apply_calibration_mode()
    {
        const app_env_runtime_config_t &config = app_env_runtime_config_get();
        if (strcmp(config.calibration.mode, APP_ENV_CALIBRATION_MODE_CAPTURE_REFERENCE) != 0)
        {
            return;
        }

        if (strlen(config.calibration.request_id) > 0 &&
            strcmp(config.calibration.request_id, config.calibration.last_request_id) == 0)
        {
            const app_env_metric_calibration_t &current = app_env_runtime_config_metric_calibration(config, config.calibration.target);
            m_sample.calibration_capture_duplicate = true;
            app_env_runtime_config_update_metric_calibration(config.calibration.target,
                                                             current.scale,
                                                             current.offset,
                                                             current.calibrated,
                                                             config.calibration.request_id);
            return;
        }

        float base_value = 0.0f;
        if (!base_value_for_metric(config.calibration.target, base_value))
        {
            m_sample.calibration_capture_error = true;
            Serial.printf("ENV calibration target is not available: target=%s\n", config.calibration.target);
            return;
        }

        const app_env_metric_calibration_t &current = app_env_runtime_config_metric_calibration(config, config.calibration.target);
        const float offset = config.calibration.reference_value - (base_value * current.scale);
        m_sample.calibration_capture_applied =
            app_env_runtime_config_update_metric_calibration(config.calibration.target,
                                                             current.scale,
                                                             offset,
                                                             true,
                                                             config.calibration.request_id);
    }
};

static EnvironmentSensorDevice s_device;

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
