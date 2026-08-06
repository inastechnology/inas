#include <unity.h>
#include <string.h>

#include "fgt_commissioning_interlock.h"
#include "fgt_firmware_manifest_validator.h"
#include "fgt_rs485_device_registry.h"
#include "fgt_sensor_diagnostics.h"
#include "fgt_state_machine.h"
#include "fgt_timed_output_sequence.h"

using namespace fgt;

static Recipe short_recipe()
{
    Recipe recipe;
    recipe.initial_fill_ms = 100;
    recipe.pre_mix_ms = 100;
    recipe.nutrient_a_ml = 1;
    recipe.nutrient_b_ml = 1;
    recipe.nutrient_a_rate_ml_min = 600;
    recipe.nutrient_b_rate_ml_min = 600;
    recipe.mix_after_a_ms = 100;
    recipe.mix_after_b_ms = 100;
    recipe.final_fill_ms = 100;
    recipe.final_mix_ms = 100;
    recipe.irrigation_max_ms = 100;
    recipe.rinse_water_ml = 1;
    recipe.rinse_fill_ms = 100;
    recipe.rinse_mix_ms = 100;
    recipe.rinse_drain_max_ms = 100;
    return recipe;
}

static Limits short_limits()
{
    Limits limits;
    limits.max_batch_ms = 5000;
    return limits;
}

static Snapshot advance(StateMachine &machine, const Inputs &inputs, uint32_t &now, uint32_t duration)
{
    now += duration;
    return machine.tick(inputs, now);
}

static void assert_safe_pair(const Snapshot &snapshot)
{
    TEST_ASSERT_FALSE(snapshot.outputs.nutrient_a && snapshot.outputs.nutrient_b);
    if (snapshot.outputs.nutrient_a || snapshot.outputs.nutrient_b)
    {
        TEST_ASSERT_TRUE(snapshot.outputs.mixer);
    }
}

static void test_recipe_validation_and_duration_rounding()
{
    Recipe recipe = short_recipe();
    Limits limits = short_limits();
    TEST_ASSERT_TRUE(recipe_valid(recipe, limits));
    TEST_ASSERT_EQUAL_UINT32(100, dose_duration_ms(1, 600));
    recipe.initial_fill_ms = 0;
    TEST_ASSERT_FALSE(recipe_valid(recipe, limits));
}

static void test_nominal_time_calibrated_batch()
{
    StateMachine machine;
    Inputs inputs;
    Recipe recipe = short_recipe();
    Limits limits = short_limits();
    uint32_t now = 0;

    TEST_ASSERT_TRUE(machine.start(recipe, limits, inputs, now));
    TEST_ASSERT_EQUAL(Phase::initial_fill, machine.snapshot(now).phase);

    const uint32_t durations[] = {
        recipe.initial_fill_ms,
        recipe.pre_mix_ms,
        dose_duration_ms(recipe.nutrient_a_ml, recipe.nutrient_a_rate_ml_min),
        recipe.mix_after_a_ms,
        dose_duration_ms(recipe.nutrient_b_ml, recipe.nutrient_b_rate_ml_min),
        recipe.mix_after_b_ms,
        recipe.final_fill_ms,
        recipe.final_mix_ms,
        recipe.irrigation_max_ms,
        recipe.rinse_fill_ms,
        recipe.rinse_mix_ms,
        recipe.rinse_drain_max_ms,
    };
    const Phase phases[] = {
        Phase::pre_mix,
        Phase::dose_a,
        Phase::mix_after_a,
        Phase::dose_b,
        Phase::mix_after_b,
        Phase::final_fill,
        Phase::final_mix,
        Phase::irrigation,
        Phase::rinse_fill,
        Phase::rinse_mix,
        Phase::rinse_drain,
        Phase::complete,
    };

    for (size_t i = 0; i < sizeof(durations) / sizeof(durations[0]); ++i)
    {
        const Snapshot snapshot = advance(machine, inputs, now, durations[i]);
        TEST_ASSERT_EQUAL(phases[i], snapshot.phase);
        assert_safe_pair(snapshot);
    }
    TEST_ASSERT_FALSE(machine.active());
}

static void test_zero_nutrients_and_rinse_skip_optional_phases()
{
    StateMachine machine;
    Inputs inputs;
    Recipe recipe = short_recipe();
    recipe.nutrient_a_ml = 0;
    recipe.nutrient_b_ml = 0;
    recipe.rinse_water_ml = 0;
    Limits limits = short_limits();
    uint32_t now = 0;

    TEST_ASSERT_TRUE(machine.start(recipe, limits, inputs, now));
    TEST_ASSERT_EQUAL(Phase::pre_mix, advance(machine, inputs, now, recipe.initial_fill_ms).phase);
    TEST_ASSERT_EQUAL(Phase::mix_after_a, advance(machine, inputs, now, recipe.pre_mix_ms).phase);
    TEST_ASSERT_EQUAL(Phase::mix_after_b, advance(machine, inputs, now, recipe.mix_after_a_ms).phase);
    TEST_ASSERT_EQUAL(Phase::final_fill, advance(machine, inputs, now, recipe.mix_after_b_ms).phase);
    TEST_ASSERT_EQUAL(Phase::final_mix, advance(machine, inputs, now, recipe.final_fill_ms).phase);
    TEST_ASSERT_EQUAL(Phase::irrigation, advance(machine, inputs, now, recipe.final_mix_ms).phase);
    TEST_ASSERT_EQUAL(Phase::complete, advance(machine, inputs, now, recipe.irrigation_max_ms).phase);
}

static void test_global_faults_turn_everything_off()
{
    Recipe recipe = short_recipe();
    Limits limits = short_limits();
    Inputs inputs;
    StateMachine machine;
    uint32_t now = 0;

    TEST_ASSERT_TRUE(machine.start(recipe, limits, inputs, now));
    inputs.emergency_stop = true;
    Snapshot snapshot = advance(machine, inputs, now, 1);
    TEST_ASSERT_EQUAL(Phase::fault, snapshot.phase);
    TEST_ASSERT_EQUAL(Fault::emergency_stop, snapshot.fault);
    TEST_ASSERT_FALSE(snapshot.outputs.water_inlet);
    TEST_ASSERT_FALSE(snapshot.outputs.nutrient_a);
    TEST_ASSERT_FALSE(snapshot.outputs.nutrient_b);
    TEST_ASSERT_FALSE(snapshot.outputs.mixer);
    TEST_ASSERT_FALSE(snapshot.outputs.irrigation);
}

static void test_batch_timeout_turns_everything_off()
{
    Recipe recipe = short_recipe();
    Limits limits = short_limits();
    limits.max_batch_ms = 50;
    Inputs inputs;
    StateMachine machine;

    TEST_ASSERT_TRUE(machine.start(recipe, limits, inputs, 0));
    const Snapshot snapshot = machine.tick(inputs, 50);
    TEST_ASSERT_EQUAL(Phase::fault, snapshot.phase);
    TEST_ASSERT_EQUAL(Fault::batch_timeout, snapshot.fault);
    TEST_ASSERT_FALSE(machine.active());
}

static TimedProgram nutrient_a_two_minute_program()
{
    TimedProgram program;
    program.outputs[static_cast<uint8_t>(TimedOutput::nutrient_a)].on_ms = 120000;
    program.outputs[static_cast<uint8_t>(TimedOutput::nutrient_a)].repeat_count = 1;
    return program;
}

static void test_timed_output_runs_only_nutrient_a_for_two_minutes()
{
    TimedProgram program = nutrient_a_two_minute_program();
    TimedOutputSequence sequence;
    Inputs inputs;

    TEST_ASSERT_TRUE(timed_program_valid(program));
    TEST_ASSERT_EQUAL_UINT32(120000, timed_program_duration_ms(program));
    TEST_ASSERT_TRUE(sequence.start(program, inputs, 100));

    TimedSnapshot snapshot = sequence.snapshot(100);
    TEST_ASSERT_EQUAL(TimedPhase::output_on, snapshot.phase);
    TEST_ASSERT_EQUAL(TimedOutput::nutrient_a, snapshot.active_output);
    TEST_ASSERT_TRUE(snapshot.outputs.nutrient_a);
    TEST_ASSERT_FALSE(snapshot.outputs.water_inlet);
    TEST_ASSERT_FALSE(snapshot.outputs.nutrient_b);
    TEST_ASSERT_FALSE(snapshot.outputs.mixer);
    TEST_ASSERT_FALSE(snapshot.outputs.irrigation);

    snapshot = sequence.tick(inputs, 120099);
    TEST_ASSERT_TRUE(snapshot.outputs.nutrient_a);
    snapshot = sequence.tick(inputs, 120100);
    TEST_ASSERT_EQUAL(TimedPhase::complete, snapshot.phase);
    TEST_ASSERT_FALSE(sequence.active());
    TEST_ASSERT_FALSE(snapshot.outputs.nutrient_a);
}

static void test_timed_output_repeats_on_off_pattern()
{
    TimedProgram program;
    TimedOutputProgram &irrigation =
        program.outputs[static_cast<uint8_t>(TimedOutput::irrigation)];
    irrigation.on_ms = 2000;
    irrigation.off_ms = 1000;
    irrigation.repeat_count = 3;
    TimedOutputSequence sequence;
    Inputs inputs;

    TEST_ASSERT_EQUAL_UINT32(8000, timed_program_duration_ms(program));
    TEST_ASSERT_TRUE(sequence.start(program, inputs, 0));
    TEST_ASSERT_EQUAL_UINT8(1, sequence.snapshot(0).repeat_number);

    TimedSnapshot snapshot = sequence.tick(inputs, 2000);
    TEST_ASSERT_EQUAL(TimedPhase::output_off, snapshot.phase);
    TEST_ASSERT_FALSE(snapshot.outputs.irrigation);
    snapshot = sequence.tick(inputs, 3000);
    TEST_ASSERT_EQUAL(TimedPhase::output_on, snapshot.phase);
    TEST_ASSERT_EQUAL_UINT8(2, snapshot.repeat_number);
    TEST_ASSERT_TRUE(snapshot.outputs.irrigation);
    snapshot = sequence.tick(inputs, 5000);
    TEST_ASSERT_EQUAL(TimedPhase::output_off, snapshot.phase);
    snapshot = sequence.tick(inputs, 6000);
    TEST_ASSERT_EQUAL_UINT8(3, snapshot.repeat_number);
    snapshot = sequence.tick(inputs, 8000);
    TEST_ASSERT_EQUAL(TimedPhase::complete, snapshot.phase);
}

static void test_timed_output_runs_programs_sequentially()
{
    TimedProgram program;
    program.outputs[static_cast<uint8_t>(TimedOutput::nutrient_a)] = {100, 0, 1};
    program.outputs[static_cast<uint8_t>(TimedOutput::nutrient_b)] = {100, 0, 1};
    TimedOutputSequence sequence;
    Inputs inputs;

    TEST_ASSERT_TRUE(sequence.start(program, inputs, 0));
    TimedSnapshot snapshot = sequence.tick(inputs, 100);
    TEST_ASSERT_TRUE(snapshot.outputs.nutrient_b);
    TEST_ASSERT_FALSE(snapshot.outputs.nutrient_a);
    TEST_ASSERT_FALSE(snapshot.outputs.nutrient_a && snapshot.outputs.nutrient_b);
    snapshot = sequence.tick(inputs, 200);
    TEST_ASSERT_EQUAL(TimedPhase::complete, snapshot.phase);
}

static void test_timed_output_rejects_invalid_or_oversized_programs()
{
    TimedProgram program;
    TEST_ASSERT_FALSE(timed_program_valid(program));
    program = nutrient_a_two_minute_program();
    program.outputs[0] = {1000, 0, 0};
    TEST_ASSERT_TRUE(timed_program_valid(program));
    program.outputs[0] = {0, 0, 1};
    TEST_ASSERT_FALSE(timed_program_valid(program));
    program.outputs[0] = {0, 0, 0};
    program.outputs[0] = {kTimedOutputMaxIntervalMs + 1UL, 0, 1};
    TEST_ASSERT_FALSE(timed_program_valid(program));
    program.outputs[0] = {1, 0, kTimedOutputMaxRepeats};
    TEST_ASSERT_TRUE(timed_program_valid(program));
    program.outputs[0] = {1, 0, static_cast<uint8_t>(kTimedOutputMaxRepeats + 1U)};
    TEST_ASSERT_FALSE(timed_program_valid(program));
}

static void test_timed_output_fault_turns_everything_off()
{
    TimedProgram program = nutrient_a_two_minute_program();
    TimedOutputSequence sequence;
    Inputs inputs;

    TEST_ASSERT_TRUE(sequence.start(program, inputs, 0));
    inputs.emergency_stop = true;
    const TimedSnapshot snapshot = sequence.tick(inputs, 1);
    TEST_ASSERT_EQUAL(TimedPhase::fault, snapshot.phase);
    TEST_ASSERT_EQUAL(Fault::emergency_stop, snapshot.fault);
    TEST_ASSERT_FALSE(snapshot.outputs.water_inlet);
    TEST_ASSERT_FALSE(snapshot.outputs.nutrient_a);
    TEST_ASSERT_FALSE(snapshot.outputs.nutrient_b);
    TEST_ASSERT_FALSE(snapshot.outputs.mixer);
    TEST_ASSERT_FALSE(snapshot.outputs.irrigation);
}

static void test_commissioning_allows_only_one_output()
{
    CommissioningInterlock interlock(3000, 30000);

    TEST_ASSERT_EQUAL(CommissioningSwitchResult::ok,
                      interlock.request_on(0, 5000, 100));
    TEST_ASSERT_EQUAL(CommissioningSwitchResult::output_already_active,
                      interlock.request_on(1, 5000, 200));

    const CommissioningSwitchSnapshot active = interlock.snapshot(1100);
    TEST_ASSERT_EQUAL_INT8(0, active.active_channel);
    TEST_ASSERT_EQUAL_UINT32(4000, active.active_remaining_ms);
}

static void test_commissioning_guard_period_starts_after_off()
{
    CommissioningInterlock interlock(3000, 30000);

    TEST_ASSERT_EQUAL(CommissioningSwitchResult::ok,
                      interlock.request_on(0, 5000, 100));
    TEST_ASSERT_TRUE(interlock.request_off(1000));
    TEST_ASSERT_EQUAL(CommissioningSwitchResult::guard_period_active,
                      interlock.request_on(1, 5000, 3999));
    TEST_ASSERT_EQUAL(CommissioningSwitchResult::ok,
                      interlock.request_on(1, 5000, 4000));
}

static void test_commissioning_auto_off_and_duration_limits()
{
    CommissioningInterlock interlock(3000, 30000);

    TEST_ASSERT_EQUAL(CommissioningSwitchResult::invalid_channel,
                      interlock.request_on(5, 1000, 0));
    TEST_ASSERT_EQUAL(CommissioningSwitchResult::invalid_duration,
                      interlock.request_on(0, 0, 0));
    TEST_ASSERT_EQUAL(CommissioningSwitchResult::invalid_duration,
                      interlock.request_on(0, 30001, 0));
    TEST_ASSERT_EQUAL(CommissioningSwitchResult::ok,
                      interlock.request_on(4, 1000, 0));
    TEST_ASSERT_FALSE(interlock.tick(999));
    TEST_ASSERT_TRUE(interlock.tick(1000));

    const CommissioningSwitchSnapshot stopped = interlock.snapshot(1000);
    TEST_ASSERT_EQUAL_INT8(-1, stopped.active_channel);
    TEST_ASSERT_EQUAL_UINT32(3000, stopped.guard_remaining_ms);
}

static void test_sensor_identification_prefers_soil_signature()
{
    SensorIdentification identification =
        identify_commissioning_sensor(true, false, true, true);
    TEST_ASSERT_EQUAL(CommissioningSensorType::soil, identification.type);
    TEST_ASSERT_EQUAL(SensorIdentificationConfidence::high,
                      identification.confidence);

    identification =
        identify_commissioning_sensor(true, true, false, false);
    TEST_ASSERT_EQUAL(CommissioningSensorType::soil, identification.type);
    TEST_ASSERT_EQUAL(SensorIdentificationConfidence::medium,
                      identification.confidence);
}

static void test_sensor_identification_does_not_treat_zero_par_as_soil()
{
    SensorIdentification identification =
        identify_commissioning_sensor(false, false, false, false);
    TEST_ASSERT_EQUAL(CommissioningSensorType::par, identification.type);
    TEST_ASSERT_EQUAL(SensorIdentificationConfidence::high,
                      identification.confidence);

    identification =
        identify_commissioning_sensor(true, false, true, false);
    TEST_ASSERT_EQUAL(CommissioningSensorType::par, identification.type);
    TEST_ASSERT_EQUAL(SensorIdentificationConfidence::tentative,
                      identification.confidence);
}

static void test_sensor_identification_uses_reserved_par_address_hint()
{
    const SensorIdentification identification =
        identify_commissioning_sensor(
            true, true, true, true, true);
    TEST_ASSERT_EQUAL(CommissioningSensorType::par, identification.type);
    TEST_ASSERT_EQUAL(SensorIdentificationConfidence::medium,
                      identification.confidence);
}

static void test_soil_measurement_plausibility()
{
    TEST_ASSERT_TRUE(soil_measurement_values_plausible(352, 241, 640));
    TEST_ASSERT_TRUE(soil_measurement_values_plausible(
        0, static_cast<uint16_t>(static_cast<int16_t>(-100)), 0));
    TEST_ASSERT_FALSE(soil_measurement_values_plausible(1001, 241, 640));
    TEST_ASSERT_FALSE(soil_measurement_values_plausible(352, 851, 640));
    TEST_ASSERT_FALSE(soil_measurement_values_plausible(352, 241, 20001));
}

static Rs485DeviceConfig registry_device(
    Rs485DeviceType type,
    uint8_t slave_id,
    uint32_t baud,
    const char *name)
{
    Rs485DeviceConfig device = {};
    device.enabled = true;
    device.type = type;
    device.slave_id = slave_id;
    device.baud = baud;
    device.function_code = 0x03;
    device.start_register = 0;
    device.register_count =
        type == Rs485DeviceType::soil ? kSoilRegisterCount : 1;
    device.scale = 1.0F;
    strncpy(device.name, name, sizeof(device.name) - 1);
    strncpy(device.location, "RS485 branch 1",
            sizeof(device.location) - 1);
    return device;
}

static void test_rs485_registry_rejects_duplicate_bus_address()
{
    Rs485DeviceRegistry registry = {};
    TEST_ASSERT_EQUAL(
        Rs485RegistryResult::ok,
        rs485_registry_add(
            registry,
            registry_device(
                Rs485DeviceType::soil, 1, 4800, "soil")));
    TEST_ASSERT_EQUAL(
        Rs485RegistryResult::duplicate_address,
        rs485_registry_add(
            registry,
            registry_device(
                Rs485DeviceType::par, 1, 4800, "par")));
    TEST_ASSERT_EQUAL(
        Rs485RegistryResult::ok,
        rs485_registry_add(
            registry,
            registry_device(
                Rs485DeviceType::par, 1, 9600, "par")));
    TEST_ASSERT_TRUE(rs485_registry_valid(registry));
}

static void test_rs485_registry_updates_and_removes_devices()
{
    Rs485DeviceRegistry registry = {};
    TEST_ASSERT_EQUAL(
        Rs485RegistryResult::ok,
        rs485_registry_add(
            registry,
            registry_device(
                Rs485DeviceType::soil, 1, 4800, "soil")));
    TEST_ASSERT_EQUAL(
        Rs485RegistryResult::ok,
        rs485_registry_add(
            registry,
            registry_device(
                Rs485DeviceType::par, 2, 4800, "par")));

    Rs485DeviceConfig updated = registry.devices[0];
    updated.slave_id = 3;
    TEST_ASSERT_EQUAL(
        Rs485RegistryResult::ok,
        rs485_registry_update(registry, 0, updated));
    TEST_ASSERT_EQUAL_INT(
        0, rs485_registry_find_address(registry, 4800, 3));
    TEST_ASSERT_EQUAL(
        Rs485RegistryResult::ok,
        rs485_registry_remove(registry, 0));
    TEST_ASSERT_EQUAL_UINT8(1, registry.count);
    TEST_ASSERT_EQUAL_UINT8(2, registry.devices[0].slave_id);
    TEST_ASSERT_TRUE(rs485_registry_valid(registry));
}

static void test_rs485_registry_migrates_legacy_seven_register_soil_profile()
{
    Rs485DeviceRegistry registry = {};
    registry.count = 1;
    registry.devices[0] = registry_device(
        Rs485DeviceType::soil, 1, 4800, "soil");
    registry.devices[0].register_count = kLegacySoilRegisterCount;

    TEST_ASSERT_FALSE(rs485_registry_valid(registry));
    TEST_ASSERT_TRUE(
        rs485_registry_normalize_legacy_soil_register_counts(registry));
    TEST_ASSERT_EQUAL_UINT8(
        kSoilRegisterCount,
        registry.devices[0].register_count);
    TEST_ASSERT_TRUE(rs485_registry_valid(registry));
    TEST_ASSERT_FALSE(
        rs485_registry_normalize_legacy_soil_register_counts(registry));
}

static void test_firmware_manifest_scanner_accepts_split_chunks()
{
    const char image[] =
        "\xE9"
        "binary-prefix-INAS_FW_MANIFEST_V1_BEGIN\n"
        "schema=1\n"
        "project=fertigation-device\n"
        "device_kind=FGT\n"
        "version=0.1.0\n"
        "target=seeed_xiao_esp32c6\n"
        "framework=arduino\n"
        "INAS_FW_MANIFEST_V1_END-binary-suffix";
    FirmwareManifestScanner scanner;
    const size_t chunk_lengths[] = {7, 19, 3, 31, 11, 1000};
    size_t offset = 0;
    for (size_t i = 0;
         i < sizeof(chunk_lengths) / sizeof(chunk_lengths[0]) &&
         offset < sizeof(image) - 1;
         ++i)
    {
        const size_t remaining =
            sizeof(image) - 1 - offset;
        const size_t length =
            chunk_lengths[i] < remaining
                ? chunk_lengths[i]
                : remaining;
        scanner.feed(
            reinterpret_cast<const uint8_t *>(image + offset),
            length);
        offset += length;
    }

    TEST_ASSERT_TRUE(scanner.complete());
    TEST_ASSERT_FALSE(scanner.overflowed());
    TEST_ASSERT_TRUE(scanner.matches(
        "fertigation-device",
        "FGT",
        "seeed_xiao_esp32c6",
        "arduino"));
    TEST_ASSERT_FALSE(scanner.matches(
        "fertigation-device",
        "FGT",
        "esp32s3",
        "arduino"));
}

static void test_firmware_manifest_scanner_rejects_missing_manifest()
{
    const uint8_t image[] = {
        0xE9, 0x01, 0x02, 0x03, 0x04};
    FirmwareManifestScanner scanner;
    scanner.feed(image, sizeof(image));

    TEST_ASSERT_FALSE(scanner.complete());
    TEST_ASSERT_FALSE(scanner.matches(
        "fertigation-device",
        "FGT",
        "seeed_xiao_esp32c6",
        "arduino"));
}

int main(int argc, char **argv)
{
    UNITY_BEGIN();
    RUN_TEST(test_recipe_validation_and_duration_rounding);
    RUN_TEST(test_nominal_time_calibrated_batch);
    RUN_TEST(test_zero_nutrients_and_rinse_skip_optional_phases);
    RUN_TEST(test_global_faults_turn_everything_off);
    RUN_TEST(test_batch_timeout_turns_everything_off);
    RUN_TEST(test_timed_output_runs_only_nutrient_a_for_two_minutes);
    RUN_TEST(test_timed_output_repeats_on_off_pattern);
    RUN_TEST(test_timed_output_runs_programs_sequentially);
    RUN_TEST(test_timed_output_rejects_invalid_or_oversized_programs);
    RUN_TEST(test_timed_output_fault_turns_everything_off);
    RUN_TEST(test_commissioning_allows_only_one_output);
    RUN_TEST(test_commissioning_guard_period_starts_after_off);
    RUN_TEST(test_commissioning_auto_off_and_duration_limits);
    RUN_TEST(test_sensor_identification_prefers_soil_signature);
    RUN_TEST(test_sensor_identification_does_not_treat_zero_par_as_soil);
    RUN_TEST(test_sensor_identification_uses_reserved_par_address_hint);
    RUN_TEST(test_soil_measurement_plausibility);
    RUN_TEST(test_rs485_registry_rejects_duplicate_bus_address);
    RUN_TEST(test_rs485_registry_updates_and_removes_devices);
    RUN_TEST(test_rs485_registry_migrates_legacy_seven_register_soil_profile);
    RUN_TEST(test_firmware_manifest_scanner_accepts_split_chunks);
    RUN_TEST(test_firmware_manifest_scanner_rejects_missing_manifest);
    return UNITY_END();
}
