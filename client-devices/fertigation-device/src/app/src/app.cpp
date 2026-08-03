#include "app.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <string.h>
#include <time.h>

#include "app_debug_log.h"
#include "app_def.h"
#include "app_device.h"
#include "app_fgt_journal.h"
#include "app_fgt_commissioning.h"
#include "app_fgt_rs485_devices.h"
#include "app_fgt_runtime_config.h"
#include "app_network.h"
#include "fgt_state_machine.h"
#include "hal_battery_monitor.h"
#include "hal_direct_gpio.h"
#include "hal_power_switch.h"
#include "hal_rs485_bus.h"
#include "hal_rs485_sensor_protocol.h"

static constexpr uint32_t kScheduleDueGraceSec = 15UL * 60UL;
static constexpr uint32_t kControlTickMs = 20;
static constexpr uint16_t kWaterOutput = 1U << 0;
static constexpr uint16_t kNutrientAOutput = 1U << 1;
static constexpr uint16_t kNutrientBOutput = 1U << 2;
static constexpr uint16_t kMixerOutput = 1U << 3;
static constexpr uint16_t kIrrigationOutput = 1U << 4;
static constexpr uint16_t kActuatorOutputs = kWaterOutput | kNutrientAOutput | kNutrientBOutput | kMixerOutput | kIrrigationOutput;
static constexpr uint16_t kTankEmptyInput = 1U << 8;
static constexpr uint16_t kTankFullInput = 1U << 9;
static constexpr uint16_t kLeakInput = 1U << 10;
static constexpr uint16_t kEmergencyInput = 1U << 11;
static constexpr uint16_t kSafetyInputs = kTankEmptyInput | kTankFullInput | kLeakInput | kEmergencyInput;

static hal_direct_gpio_t s_io = {};
static hal_battery_monitor_t s_battery_monitor = {};
static hal_power_switch_t s_sensor_power = {};
static bool s_rs485_ready = false;
static uint32_t s_rs485_baud = 0;

struct FgtConfiguredRs485Sample
{
    bool attempted = false;
    bool bus_ready = false;
    bool ok = false;
    hal_rs485_soil_sample_t soil = {};
    hal_rs485_par_sample_t par = {};
};

struct FgtSensorSample
{
    bool battery_ok = false;
    hal_battery_sample_t battery = {};
    bool power_requested = false;
    bool power_ok = false;
    hal_rs485_soil_sample_t soil = {};
    hal_rs485_par_sample_t par = {};
    bool saved_registry_used = false;
    uint8_t configured_count = 0;
    FgtConfiguredRs485Sample configured[fgt::kMaxRs485Devices] = {};
};

struct FgtCycleState
{
    bool config_valid = false;
    bool batch_due = false;
    bool batch_started = false;
    bool batch_completed = false;
    bool batch_skipped = false;
    bool recovery_required = false;
    bool journal_error = false;
    bool output_error = false;
    const char *skip_reason = "none";
    time_t schedule_epoch_utc = 0;
    uint32_t batch_id = 0;
    fgt::Inputs inputs = {};
    fgt::Snapshot state = {};
    FgtSensorSample sensors = {};
};

static void force_actuators_off()
{
    hal_direct_gpio_all_outputs_off(&s_io);
}

static uint16_t output_mask(const fgt::Outputs &outputs)
{
    uint16_t mask = 0;
    if (outputs.water_inlet) mask |= kWaterOutput;
    if (outputs.nutrient_a) mask |= kNutrientAOutput;
    if (outputs.nutrient_b) mask |= kNutrientBOutput;
    if (outputs.mixer) mask |= kMixerOutput;
    if (outputs.irrigation) mask |= kIrrigationOutput;
    return mask;
}

static bool apply_outputs(const fgt::Outputs &outputs)
{
    // Master OFF creates a break-before-make interval at every transition and
    // prevents a transient A+B overlap even when I2C is delayed.
    const uint16_t requested = output_mask(outputs);
    if ((requested & kNutrientAOutput) != 0 && (requested & kNutrientBOutput) != 0)
    {
        hal_direct_gpio_all_outputs_off(&s_io);
        return false;
    }
    if (!hal_direct_gpio_write_outputs(&s_io, kActuatorOutputs, requested))
    {
        hal_direct_gpio_all_outputs_off(&s_io);
        return false;
    }
    return true;
}

static fgt::Inputs read_physical_inputs()
{
    fgt::Inputs inputs = {};
    inputs.io_ok = true;
    return inputs;
}

static bool ensure_rs485_baud(uint32_t baud)
{
    if (s_rs485_ready && s_rs485_baud == baud)
    {
        return true;
    }
    hal_rs485_bus_deinit();
    hal_rs485_modbus_config_t config =
        hal_rs485_modbus_default_config();
    config.baud = baud;
    s_rs485_ready = hal_rs485_bus_init(&config);
    s_rs485_baud = s_rs485_ready ? baud : 0;
    return s_rs485_ready;
}

class FertigationDevice : public AppDevice
{
public:
    bool apply_runtime_config_json(const uint8_t *payload, size_t length) override
    {
        return app_fgt_runtime_config_apply_json(payload, length);
    }

    bool has_valid_runtime_config() const override
    {
        return app_fgt_runtime_config_is_valid();
    }

    bool is_runtime_config_received() const override
    {
        return app_fgt_runtime_config_is_received();
    }

protected:
    const char *device_name() const override
    {
        return "INA Fertigation";
    }

    bool on_initialize() override
    {
        app_fgt_runtime_config_init();
        app_fgt_rs485_devices_init();
        app_fgt_journal_init();

        const bool io_ready = hal_direct_gpio_open(&s_io);
        force_actuators_off();

        const bool battery_ready = hal_battery_monitor_open(&s_battery_monitor);
        const hal_power_switch_config_t power_config = hal_power_switch_default_config();
        const bool power_ready = hal_power_switch_open(&s_sensor_power, &power_config);
        const hal_rs485_modbus_config_t rs485_config = hal_rs485_modbus_default_config();
        s_rs485_ready = hal_rs485_bus_init(&rs485_config);
        s_rs485_baud = s_rs485_ready ? rs485_config.baud : 0;
        return io_ready && battery_ready && power_ready && s_rs485_ready;
    }

    void prepare_runtime_config_request() override
    {
        app_fgt_runtime_config_mark_waiting();
    }

    void on_runtime_config_ready(bool config_received) override
    {
        (void)config_received;
        const app_fgt_runtime_config_t &config = app_fgt_runtime_config_get();
        Serial.printf("FGT config: valid=%s enabled=%s schedules=%u water=%lu initial=%lu A=%lu B=%lu rinse=%lu recovery_ack=%lu local_rs485=%s devices=%u\n",
                      config.valid ? "true" : "false",
                      config.enabled ? "true" : "false",
                      static_cast<unsigned int>(config.schedule_count),
                      static_cast<unsigned long>(config.recipe.total_water_ml),
                      static_cast<unsigned long>(config.recipe.initial_water_ml),
                      static_cast<unsigned long>(config.recipe.nutrient_a_ml),
                      static_cast<unsigned long>(config.recipe.nutrient_b_ml),
                      static_cast<unsigned long>(config.recipe.rinse_water_ml),
                      static_cast<unsigned long>(config.recovery_ack),
                      app_fgt_rs485_devices_has_saved_registry()
                          ? "true"
                          : "false",
                      static_cast<unsigned int>(
                          app_fgt_rs485_devices_get().count));
    }

    const char *runtime_ntp_server() const override
    {
        return app_fgt_runtime_config_get().ntp_server;
    }

    int32_t runtime_timezone_offset_sec() const override
    {
        return app_fgt_runtime_config_get().timezone_offset_sec;
    }

    AppDeviceCycleResult run_device_cycle(const AppDeviceWakeContext &context) override
    {
        AppDeviceCycleResult result = {};
        const app_fgt_runtime_config_t &config = app_fgt_runtime_config_get();
        m_cycle = {};
        m_cycle.config_valid = app_fgt_runtime_config_is_valid();
        force_actuators_off();
        read_sensors();
        m_cycle.inputs = read_physical_inputs();

        const app_fgt_journal_state_t &journal = app_fgt_journal_get();
        // A corrupt journal may hide an interrupted nutrient batch. Treat it
        // exactly like an unfinished batch until a safe, explicit recovery ack.
        m_cycle.recovery_required = !journal.valid || journal.in_progress;
        m_cycle.journal_error = !journal.valid;
        if (m_cycle.recovery_required && config.recovery_ack != journal.recovery_ack &&
            m_cycle.inputs.io_ok && m_cycle.inputs.tank_empty && !m_cycle.inputs.tank_full &&
            !m_cycle.inputs.leak_detected && !m_cycle.inputs.emergency_stop)
        {
            if (app_fgt_journal_acknowledge_recovery(config.recovery_ack))
            {
                m_cycle.recovery_required = false;
            }
        }

        app_fgt_schedule_entry_t due_schedule = {};
        const time_t now_utc = time(nullptr);
        time_t due_epoch = 0;
        const time_t last_executed = app_fgt_journal_get().schedule_epoch_utc;
        m_cycle.batch_due = config.enabled && context.time_synced && !m_cycle.recovery_required &&
                            app_fgt_runtime_config_find_due_schedule(now_utc, last_executed, &due_schedule, &due_epoch);
        m_cycle.schedule_epoch_utc = due_epoch;

        if (m_cycle.batch_due && now_utc - due_epoch > static_cast<time_t>(kScheduleDueGraceSec))
        {
            m_cycle.batch_skipped = true;
            m_cycle.skip_reason = "schedule_too_old";
            m_cycle.batch_id = static_cast<uint32_t>(due_epoch);
            if (!app_fgt_journal_mark_started(due_epoch, m_cycle.batch_id) || !app_fgt_journal_mark_finished())
            {
                m_cycle.journal_error = true;
            }
            m_cycle.batch_due = false;
        }
        else if (m_cycle.batch_due && context.ota_update_attempted)
        {
            m_cycle.batch_skipped = true;
            m_cycle.skip_reason = "ota_update_attempted";
        }
        else if (m_cycle.batch_due)
        {
            run_batch(config, due_epoch);
        }
        else if (m_cycle.recovery_required)
        {
            m_cycle.batch_skipped = true;
            m_cycle.skip_reason = "recovery_required";
        }

        force_actuators_off();
        if (hal_power_switch_enabled(&s_sensor_power)) hal_power_switch_set(&s_sensor_power, false);
        read_sensors();
        m_cycle.inputs = read_physical_inputs();

        const time_t finish_utc = time(nullptr);
        if (context.time_synced && config.valid)
        {
            result.next_sleep_sec = min(config.sleep_sec,
                                        min(app_fgt_runtime_config_seconds_until_next_schedule(finish_utc),
                                            config.ota_check_interval_sec));
        }
        else
        {
            result.next_sleep_sec = context.network_retry_sleep_sec;
        }
        result.publish_debug_log = config.valid && config.debug_log_on_wake;
        return result;
    }

    bool publish_device_status(const AppDeviceWakeContext &context,
                               const AppDeviceCycleResult &cycle_result) override
    {
        const app_fgt_runtime_config_t &config = app_fgt_runtime_config_get();
        const fgt::Rs485DeviceRegistry &registry =
            app_fgt_rs485_devices_get();
        bool soil_enabled = config.sensors.soil.enabled;
        bool par_enabled = config.sensors.par.enabled;
        uint8_t soil_id = config.sensors.soil.modbus_slave_id;
        uint8_t par_id = config.sensors.par.modbus_slave_id;
        if (m_cycle.sensors.saved_registry_used)
        {
            soil_enabled = false;
            par_enabled = false;
            bool soil_found = false;
            bool par_found = false;
            for (size_t i = 0; i < registry.count; ++i)
            {
                const fgt::Rs485DeviceConfig &device =
                    registry.devices[i];
                if (device.type == fgt::Rs485DeviceType::soil &&
                    (!soil_found ||
                     (!soil_enabled && device.enabled)))
                {
                    soil_found = true;
                    soil_enabled = device.enabled;
                    soil_id = device.slave_id;
                }
                else if (
                    device.type == fgt::Rs485DeviceType::par &&
                    (!par_found ||
                     (!par_enabled && device.enabled)))
                {
                    par_found = true;
                    par_enabled = device.enabled;
                    par_id = device.slave_id;
                }
            }
        }
        JsonDocument doc;
        doc["seq"] = context.seq_id;
        doc["device_kind"] = APP_DEVICE_KIND;
        doc["sensor_model"] = "FGT-AIO-12V-RS485";
        doc["firmware_version"] = APP_FIRMWARE_VERSION;
        doc["firmware_build_id"] = APP_FIRMWARE_BUILD_ID;
        doc["network_connected"] = context.network_connected;
        doc["runtime_config_valid"] = m_cycle.config_valid;
        doc["config_received"] = context.config_received;
        doc["time_synced"] = context.time_synced;
        doc["ota_update_attempted"] = context.ota_update_attempted;
        doc["next_sleep_sec"] = cycle_result.next_sleep_sec;
        doc["ota_check_interval_sec"] = config.ota_check_interval_sec;
        doc["schedule_count"] = config.schedule_count;
        doc["batch_due"] = m_cycle.batch_due;
        doc["batch_started"] = m_cycle.batch_started;
        doc["batch_completed"] = m_cycle.batch_completed;
        doc["batch_skipped"] = m_cycle.batch_skipped;
        doc["batch_skip_reason"] = m_cycle.skip_reason;
        doc["batch_id"] = m_cycle.batch_id;
        doc["schedule_epoch_utc"] = static_cast<int64_t>(m_cycle.schedule_epoch_utc);
        doc["recovery_required"] = m_cycle.recovery_required;
        doc["journal_error"] = m_cycle.journal_error;
        doc["output_error"] = m_cycle.output_error;
        doc["fgt_phase"] = fgt::phase_name(m_cycle.state.phase);
        doc["fgt_fault"] = fgt::fault_name(m_cycle.state.fault);
        doc["fgt_phase_elapsed_ms"] = m_cycle.state.phase_elapsed_ms;
        doc["fgt_batch_elapsed_ms"] = m_cycle.state.batch_elapsed_ms;
        doc["inlet_water_ml"] = m_cycle.inputs.inlet_water_ml;
        doc["target_water_ml"] = m_cycle.state.target_water_ml;
        doc["nutrient_batch_water_target_ml"] = config.recipe.total_water_ml;
        doc["rinse_water_target_ml"] = config.recipe.rinse_water_ml;
        doc["planned_irrigation_water_ml"] = config.recipe.total_water_ml + config.recipe.rinse_water_ml;
        doc["tank_empty"] = m_cycle.inputs.tank_empty;
        doc["tank_full"] = m_cycle.inputs.tank_full;
        doc["leak_detected"] = m_cycle.inputs.leak_detected;
        doc["emergency_stop"] = m_cycle.inputs.emergency_stop;
        doc["io_ok"] = m_cycle.inputs.io_ok;
        doc["water_inlet_on"] = m_cycle.state.outputs.water_inlet;
        doc["nutrient_a_on"] = m_cycle.state.outputs.nutrient_a;
        doc["nutrient_b_on"] = m_cycle.state.outputs.nutrient_b;
        doc["mixer_on"] = m_cycle.state.outputs.mixer;
        doc["irrigation_on"] = m_cycle.state.outputs.irrigation;
        doc["battery_voltage_ok"] = m_cycle.sensors.battery_ok;
        doc["battery_adc_mv"] = m_cycle.sensors.battery.adc_millivolts;
        doc["battery_voltage_v"] = m_cycle.sensors.battery.battery_volts;
        doc["sensor_12v_power_requested"] = m_cycle.sensors.power_requested;
        doc["sensor_12v_power_error"] = m_cycle.sensors.power_requested && !m_cycle.sensors.power_ok;
        doc["soil_rs485_enabled"] = soil_enabled;
        doc["soil_rs485_ok"] = m_cycle.sensors.soil.ok;
        doc["soil_rs485_modbus_slave_id"] = soil_id;
        doc["soil_moisture_percent"] = m_cycle.sensors.soil.moisture_percent;
        doc["soil_temperature_c"] = m_cycle.sensors.soil.temperature_c;
        doc["soil_ec_us_cm"] = m_cycle.sensors.soil.ec_us_cm;
        doc["soil_ph"] = m_cycle.sensors.soil.ph;
        doc["soil_n_mg_kg"] = m_cycle.sensors.soil.n_mg_kg;
        doc["soil_p_mg_kg"] = m_cycle.sensors.soil.p_mg_kg;
        doc["soil_k_mg_kg"] = m_cycle.sensors.soil.k_mg_kg;
        doc["par_enabled"] = par_enabled;
        doc["par_ok"] = m_cycle.sensors.par.ok;
        doc["par_modbus_slave_id"] = par_id;
        doc["par_umol_m2_s"] = m_cycle.sensors.par.par_umol_m2_s;
        doc["rs485_registry_saved"] =
            m_cycle.sensors.saved_registry_used;
        doc["rs485_device_count"] =
            m_cycle.sensors.configured_count;
        JsonArray rs485_devices =
            doc["rs485_devices"].to<JsonArray>();
        if (m_cycle.sensors.saved_registry_used)
        {
            for (size_t i = 0; i < registry.count; ++i)
            {
                const fgt::Rs485DeviceConfig &device =
                    registry.devices[i];
                const FgtConfiguredRs485Sample &sample =
                    m_cycle.sensors.configured[i];
                JsonObject item = rs485_devices.add<JsonObject>();
                item["index"] = i;
                item["enabled"] = device.enabled;
                item["type"] =
                    device.type == fgt::Rs485DeviceType::soil
                        ? "soil"
                        : "par";
                item["name"] = device.name;
                item["location"] = device.location;
                item["modbus_slave_id"] = device.slave_id;
                item["baud"] = device.baud;
                item["function_code"] = device.function_code;
                item["start_register"] = device.start_register;
                item["register_count"] = device.register_count;
                item["attempted"] = sample.attempted;
                item["bus_ready"] = sample.bus_ready;
                item["ok"] = sample.ok;
                if (device.type == fgt::Rs485DeviceType::soil)
                {
                    item["moisture_percent"] =
                        sample.soil.moisture_percent;
                    item["temperature_c"] =
                        sample.soil.temperature_c;
                    item["ec_us_cm"] = sample.soil.ec_us_cm;
                    item["ph"] = sample.soil.ph;
                    item["n_mg_kg"] = sample.soil.n_mg_kg;
                    item["p_mg_kg"] = sample.soil.p_mg_kg;
                    item["k_mg_kg"] = sample.soil.k_mg_kg;
                }
                else
                {
                    item["par_umol_m2_s"] =
                        sample.par.par_umol_m2_s;
                }
            }
        }

        String payload;
        payload.reserve(6144);
        const size_t length = serializeJson(doc, payload);
        if (length == 0 || length > 12288) return false;
        Serial.printf("Sending status: %s\n", payload.c_str());
        const bool sent = app_network_send(APP_MSG_TYPE_STATUS,
                                           reinterpret_cast<const uint8_t *>(payload.c_str()),
                                           length,
                                           context.seq_id);
        if (sent) app_network_flush(APP_MQTT_STATUS_PUBLISH_DRAIN_MS);
        return sent;
    }

private:
    FgtCycleState m_cycle = {};
    fgt::StateMachine m_machine;

    void read_sensors()
    {
        const app_fgt_runtime_config_t &config = app_fgt_runtime_config_get();
        FgtSensorSample sample = {};
        sample.battery_ok =
            hal_battery_monitor_read(&s_battery_monitor, &sample.battery);
        sample.saved_registry_used =
            app_fgt_rs485_devices_has_saved_registry();
        const fgt::Rs485DeviceRegistry &registry =
            app_fgt_rs485_devices_get();
        sample.configured_count =
            sample.saved_registry_used ? registry.count : 0;
        if (sample.saved_registry_used)
        {
            for (size_t i = 0; i < registry.count; ++i)
            {
                sample.power_requested =
                    sample.power_requested ||
                    registry.devices[i].enabled;
            }
        }
        else
        {
            sample.power_requested =
                config.sensors.soil.enabled ||
                config.sensors.par.enabled;
        }
        if (!sample.power_requested)
        {
            sample.power_ok = true;
            m_cycle.sensors = sample;
            return;
        }
        sample.power_ok = hal_power_switch_enable_wait(&s_sensor_power, config.sensors.power_settle_ms);
        if (sample.power_ok && sample.saved_registry_used)
        {
            bool first_soil = true;
            bool first_par = true;
            for (size_t i = 0; i < registry.count; ++i)
            {
                const fgt::Rs485DeviceConfig &device =
                    registry.devices[i];
                FgtConfiguredRs485Sample &configured =
                    sample.configured[i];
                if (!device.enabled)
                {
                    continue;
                }
                configured.attempted = true;
                configured.bus_ready =
                    ensure_rs485_baud(device.baud);
                if (!configured.bus_ready)
                {
                    continue;
                }
                if (device.type == fgt::Rs485DeviceType::soil)
                {
                    const hal_rs485_soil_sensor_config_t sensor_config = {
                        true,
                        device.slave_id,
                        device.function_code,
                        device.start_register,
                    };
                    configured.ok = hal_rs485_soil_sensor_read(
                        &sensor_config, &configured.soil);
                    if (first_soil)
                    {
                        sample.soil = configured.soil;
                        first_soil = false;
                    }
                }
                else
                {
                    const hal_rs485_par_sensor_config_t sensor_config = {
                        true,
                        device.slave_id,
                        device.function_code,
                        device.start_register,
                        device.scale,
                    };
                    configured.ok = hal_rs485_par_sensor_read(
                        &sensor_config, &configured.par);
                    if (first_par)
                    {
                        sample.par = configured.par;
                        first_par = false;
                    }
                }
            }
        }
        else if (sample.power_ok &&
                 ensure_rs485_baud(APP_RS485_BAUD))
        {
            if (config.sensors.soil.enabled)
            {
                hal_rs485_soil_sensor_read(
                    &config.sensors.soil, &sample.soil);
            }
            if (config.sensors.par.enabled)
            {
                hal_rs485_par_sensor_read(
                    &config.sensors.par, &sample.par);
            }
        }
        hal_power_switch_set(&s_sensor_power, false);
        m_cycle.sensors = sample;
    }

    void run_batch(const app_fgt_runtime_config_t &config, time_t due_epoch)
    {
        m_cycle.inputs = read_physical_inputs();
        const uint32_t started_ms = millis();
        if (!m_machine.start(config.recipe, config.limits, m_cycle.inputs, started_ms))
        {
            m_cycle.state = m_machine.snapshot(started_ms);
            m_cycle.batch_skipped = true;
            m_cycle.skip_reason = "preflight_failed";
            return;
        }

        m_cycle.batch_id = esp_random();
        if (!app_fgt_journal_mark_started(due_epoch, m_cycle.batch_id))
        {
            m_cycle.journal_error = true;
            m_cycle.batch_skipped = true;
            m_cycle.skip_reason = "journal_write_failed";
            force_actuators_off();
            return;
        }
        m_cycle.batch_started = true;
        m_cycle.schedule_epoch_utc = due_epoch;
        m_cycle.state = m_machine.snapshot(started_ms);

        if (!apply_outputs(m_cycle.state.outputs))
        {
            m_cycle.output_error = true;
            m_cycle.inputs.io_ok = false;
            m_cycle.state = m_machine.tick(m_cycle.inputs, millis());
        }

        while (m_machine.active())
        {
            app_network_loop();
            delay(kControlTickMs);
            m_cycle.inputs = read_physical_inputs();
            m_cycle.state = m_machine.tick(m_cycle.inputs, millis());
            if (!apply_outputs(m_cycle.state.outputs))
            {
                m_cycle.output_error = true;
                m_cycle.inputs.io_ok = false;
                m_cycle.state = m_machine.tick(m_cycle.inputs, millis());
            }
        }

        force_actuators_off();
        m_cycle.batch_completed = m_cycle.state.phase == fgt::Phase::complete;
        if (m_cycle.batch_completed)
        {
            if (!app_fgt_journal_mark_finished())
            {
                m_cycle.journal_error = true;
                m_cycle.batch_completed = false;
            }
        }
        else
        {
            m_cycle.recovery_required = true;
        }
    }
};

static FertigationDevice s_device;

int app_init()
{
    app_fgt_commissioning_register_setup_portal();
    AppDeviceInitializeOptions options;
    options.setup_ap_enabled = true;
    options.start_network = true;
    options.print_littlefs_files = false;
    return s_device.initialize(options);
}

void app_deinit()
{
    force_actuators_off();
    hal_direct_gpio_close(&s_io);
    hal_power_switch_close(&s_sensor_power);
    hal_rs485_bus_deinit();
    s_rs485_ready = false;
    s_rs485_baud = 0;
}

void app_loop()
{
    s_device.loop();
}
