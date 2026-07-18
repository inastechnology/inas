#include <unity.h>

#include "fgt_state_machine.h"

using namespace fgt;

static Recipe short_recipe()
{
    Recipe recipe = {};
    recipe.total_water_ml = 1000;
    recipe.initial_water_ml = 400;
    recipe.nutrient_a_ml = 10;
    recipe.nutrient_b_ml = 10;
    recipe.nutrient_a_rate_ml_min = 600;
    recipe.nutrient_b_rate_ml_min = 600;
    recipe.pre_mix_ms = 100;
    recipe.mix_after_a_ms = 100;
    recipe.mix_after_b_ms = 100;
    recipe.final_mix_ms = 100;
    recipe.irrigation_max_ms = 1000;
    recipe.rinse_water_ml = 100;
    recipe.rinse_mix_ms = 100;
    recipe.rinse_drain_max_ms = 1000;
    return recipe;
}

static Limits short_limits()
{
    Limits limits = {};
    limits.max_total_water_ml = 2000;
    limits.max_nutrient_ml = 100;
    limits.water_no_flow_timeout_ms = 200;
    limits.max_fill_ms = 1000;
    limits.max_batch_ms = 10000;
    limits.volume_tolerance_ml = 20;
    return limits;
}

static void assert_all_off(const Outputs &outputs)
{
    TEST_ASSERT_FALSE(outputs.water_inlet);
    TEST_ASSERT_FALSE(outputs.nutrient_a);
    TEST_ASSERT_FALSE(outputs.nutrient_b);
    TEST_ASSERT_FALSE(outputs.mixer);
    TEST_ASSERT_FALSE(outputs.irrigation);
}

static void assert_output_invariants(const Outputs &outputs)
{
    TEST_ASSERT_FALSE(outputs.nutrient_a && outputs.nutrient_b);
    TEST_ASSERT_FALSE((outputs.nutrient_a || outputs.nutrient_b) && !outputs.mixer);
    TEST_ASSERT_FALSE(outputs.water_inlet && outputs.irrigation);
}

static void test_recipe_validation_and_dose_rounding()
{
    Recipe recipe = short_recipe();
    Limits limits = short_limits();
    TEST_ASSERT_TRUE(recipe_valid(recipe, limits));
    TEST_ASSERT_EQUAL_UINT32(1000, dose_duration_ms(10, 600));
    TEST_ASSERT_EQUAL_UINT32(6000, dose_duration_ms(10, 100));
    recipe.initial_water_ml = recipe.total_water_ml;
    TEST_ASSERT_FALSE(recipe_valid(recipe, limits));
    recipe = short_recipe();
    recipe.nutrient_a_rate_ml_min = 0;
    TEST_ASSERT_FALSE(recipe_valid(recipe, limits));
}

static void test_nominal_batch_and_rinse_path()
{
    StateMachine machine;
    Inputs input = {};
    uint32_t now = 1000;
    TEST_ASSERT_TRUE(machine.start(short_recipe(), short_limits(), input, now));
    TEST_ASSERT_EQUAL_STRING("initial_fill", phase_name(machine.snapshot(now).phase));
    TEST_ASSERT_TRUE(machine.snapshot(now).outputs.water_inlet);
    assert_output_invariants(machine.snapshot(now).outputs);

    input.inlet_water_ml = 400;
    input.tank_empty = false;
    now += 50;
    TEST_ASSERT_EQUAL(Phase::pre_mix, machine.tick(input, now).phase);
    assert_output_invariants(machine.snapshot(now).outputs);
    now += 100;
    TEST_ASSERT_EQUAL(Phase::dose_a, machine.tick(input, now).phase);
    Snapshot state = machine.snapshot(now);
    TEST_ASSERT_TRUE(state.outputs.mixer);
    TEST_ASSERT_TRUE(state.outputs.nutrient_a);
    TEST_ASSERT_FALSE(state.outputs.nutrient_b);
    assert_output_invariants(state.outputs);

    now += 1000;
    TEST_ASSERT_EQUAL(Phase::mix_after_a, machine.tick(input, now).phase);
    assert_output_invariants(machine.snapshot(now).outputs);
    now += 100;
    TEST_ASSERT_EQUAL(Phase::dose_b, machine.tick(input, now).phase);
    state = machine.snapshot(now);
    TEST_ASSERT_TRUE(state.outputs.mixer);
    TEST_ASSERT_FALSE(state.outputs.nutrient_a);
    TEST_ASSERT_TRUE(state.outputs.nutrient_b);
    assert_output_invariants(state.outputs);

    now += 1000;
    TEST_ASSERT_EQUAL(Phase::mix_after_b, machine.tick(input, now).phase);
    assert_output_invariants(machine.snapshot(now).outputs);
    now += 100;
    TEST_ASSERT_EQUAL(Phase::final_fill, machine.tick(input, now).phase);
    assert_output_invariants(machine.snapshot(now).outputs);
    input.inlet_water_ml = 1000;
    now += 50;
    TEST_ASSERT_EQUAL(Phase::final_mix, machine.tick(input, now).phase);
    assert_output_invariants(machine.snapshot(now).outputs);
    now += 100;
    TEST_ASSERT_EQUAL(Phase::irrigation, machine.tick(input, now).phase);
    assert_output_invariants(machine.snapshot(now).outputs);

    input.tank_empty = true;
    now += 50;
    TEST_ASSERT_EQUAL(Phase::rinse_fill, machine.tick(input, now).phase);
    assert_output_invariants(machine.snapshot(now).outputs);
    input.inlet_water_ml = 1100;
    input.tank_empty = false;
    now += 50;
    TEST_ASSERT_EQUAL(Phase::rinse_mix, machine.tick(input, now).phase);
    assert_output_invariants(machine.snapshot(now).outputs);
    now += 100;
    TEST_ASSERT_EQUAL(Phase::rinse_drain, machine.tick(input, now).phase);
    assert_output_invariants(machine.snapshot(now).outputs);
    input.tank_empty = true;
    now += 50;
    state = machine.tick(input, now);
    TEST_ASSERT_EQUAL(Phase::complete, state.phase);
    TEST_ASSERT_EQUAL(Fault::none, state.fault);
    assert_all_off(state.outputs);
}

static void test_start_rejects_nonempty_tank()
{
    StateMachine machine;
    Inputs input = {};
    input.tank_empty = false;
    TEST_ASSERT_FALSE(machine.start(short_recipe(), short_limits(), input, 0));
    Snapshot state = machine.snapshot(0);
    TEST_ASSERT_EQUAL(Phase::fault, state.phase);
    TEST_ASSERT_EQUAL(Fault::tank_not_empty, state.fault);
    assert_all_off(state.outputs);
}

static void test_no_flow_fault_turns_everything_off()
{
    StateMachine machine;
    Inputs input = {};
    TEST_ASSERT_TRUE(machine.start(short_recipe(), short_limits(), input, 0));
    Snapshot state = machine.tick(input, 200);
    TEST_ASSERT_EQUAL(Fault::water_no_flow, state.fault);
    assert_all_off(state.outputs);
}

static void test_leak_and_io_failures_are_global()
{
    StateMachine machine;
    Inputs input = {};
    TEST_ASSERT_TRUE(machine.start(short_recipe(), short_limits(), input, 0));
    input.leak_detected = true;
    Snapshot state = machine.tick(input, 1);
    TEST_ASSERT_EQUAL(Fault::leak_detected, state.fault);
    assert_all_off(state.outputs);

    input = {};
    TEST_ASSERT_TRUE(machine.reset(input));
    TEST_ASSERT_TRUE(machine.start(short_recipe(), short_limits(), input, 10));
    input.io_ok = false;
    state = machine.tick(input, 11);
    TEST_ASSERT_EQUAL(Fault::io_failure, state.fault);
    assert_all_off(state.outputs);
}

static void test_early_full_and_empty_during_mix_fault()
{
    StateMachine machine;
    Inputs input = {};
    TEST_ASSERT_TRUE(machine.start(short_recipe(), short_limits(), input, 0));
    input.inlet_water_ml = 100;
    input.tank_full = true;
    Snapshot state = machine.tick(input, 10);
    TEST_ASSERT_EQUAL(Fault::unexpected_full, state.fault);

    input = {};
    TEST_ASSERT_TRUE(machine.reset(input));
    TEST_ASSERT_TRUE(machine.start(short_recipe(), short_limits(), input, 20));
    input.inlet_water_ml = 400;
    input.tank_empty = false;
    TEST_ASSERT_EQUAL(Phase::pre_mix, machine.tick(input, 30).phase);
    input.tank_empty = true;
    state = machine.tick(input, 31);
    TEST_ASSERT_EQUAL(Fault::tank_empty_during_mix, state.fault);
    assert_all_off(state.outputs);
}

static void test_irrigation_timeout_and_reset_guard()
{
    StateMachine machine;
    Inputs input = {};
    uint32_t now = 0;
    TEST_ASSERT_TRUE(machine.start(short_recipe(), short_limits(), input, now));
    input.inlet_water_ml = 400;
    input.tank_empty = false;
    machine.tick(input, now += 10);
    machine.tick(input, now += 100);
    machine.tick(input, now += 1000);
    machine.tick(input, now += 100);
    machine.tick(input, now += 1000);
    machine.tick(input, now += 100);
    input.inlet_water_ml = 1000;
    machine.tick(input, now += 10);
    TEST_ASSERT_EQUAL(Phase::irrigation, machine.tick(input, now += 100).phase);
    Snapshot state = machine.tick(input, now += 1000);
    TEST_ASSERT_EQUAL(Fault::irrigation_timeout, state.fault);
    assert_all_off(state.outputs);

    input.tank_empty = false;
    TEST_ASSERT_FALSE(machine.reset(input));
    input.tank_empty = true;
    TEST_ASSERT_TRUE(machine.reset(input));
    TEST_ASSERT_EQUAL(Phase::idle, machine.snapshot(now).phase);
}

static void test_emergency_and_whole_batch_timeout_are_global()
{
    StateMachine machine;
    Inputs input = {};
    TEST_ASSERT_TRUE(machine.start(short_recipe(), short_limits(), input, 0));
    input.emergency_stop = true;
    Snapshot state = machine.tick(input, 1);
    TEST_ASSERT_EQUAL(Fault::emergency_stop, state.fault);
    assert_all_off(state.outputs);

    input = {};
    TEST_ASSERT_TRUE(machine.reset(input));
    Limits limits = short_limits();
    limits.max_batch_ms = 50;
    TEST_ASSERT_TRUE(machine.start(short_recipe(), limits, input, 100));
    input.inlet_water_ml = 1;
    state = machine.tick(input, 150);
    TEST_ASSERT_EQUAL(Fault::batch_timeout, state.fault);
    assert_all_off(state.outputs);
}

static void test_fill_timeout_is_distinct_from_no_flow_timeout()
{
    StateMachine machine;
    Inputs input = {};
    Limits limits = short_limits();
    limits.max_fill_ms = 100;
    limits.water_no_flow_timeout_ms = 500;
    TEST_ASSERT_TRUE(machine.start(short_recipe(), limits, input, 0));
    Snapshot state = machine.tick(input, 100);
    TEST_ASSERT_EQUAL(Fault::fill_timeout, state.fault);
    assert_all_off(state.outputs);
}

static void test_full_sensor_within_tolerance_advances_fill()
{
    StateMachine machine;
    Inputs input = {};
    TEST_ASSERT_TRUE(machine.start(short_recipe(), short_limits(), input, 0));
    input.inlet_water_ml = 385;
    input.tank_empty = false;
    input.tank_full = true;
    Snapshot state = machine.tick(input, 10);
    TEST_ASSERT_EQUAL(Phase::pre_mix, state.phase);
    TEST_ASSERT_EQUAL(Fault::none, state.fault);
    assert_output_invariants(state.outputs);
}

static void test_rinse_drain_timeout_stops_irrigation()
{
    StateMachine machine;
    Inputs input = {};
    Recipe recipe = short_recipe();
    recipe.nutrient_a_ml = 0;
    recipe.nutrient_b_ml = 0;
    recipe.mix_after_a_ms = 0;
    recipe.mix_after_b_ms = 0;
    recipe.rinse_drain_max_ms = 50;
    uint32_t now = 0;
    TEST_ASSERT_TRUE(machine.start(recipe, short_limits(), input, now));
    input.inlet_water_ml = 400;
    input.tank_empty = false;
    machine.tick(input, now += 10);
    machine.tick(input, now += 100);
    machine.tick(input, now += 1);
    machine.tick(input, now += 1);
    input.inlet_water_ml = 1000;
    machine.tick(input, now += 10);
    machine.tick(input, now += 100);
    input.tank_empty = true;
    TEST_ASSERT_EQUAL(Phase::rinse_fill, machine.tick(input, now += 1).phase);
    input.inlet_water_ml = 1100;
    input.tank_empty = false;
    machine.tick(input, now += 10);
    TEST_ASSERT_EQUAL(Phase::rinse_drain, machine.tick(input, now += 100).phase);
    Snapshot state = machine.tick(input, now += 50);
    TEST_ASSERT_EQUAL(Fault::rinse_drain_timeout, state.fault);
    assert_all_off(state.outputs);
}

static void test_names_are_stable()
{
    TEST_ASSERT_EQUAL_STRING("dose_a", phase_name(Phase::dose_a));
    TEST_ASSERT_EQUAL_STRING("rinse_drain", phase_name(Phase::rinse_drain));
    TEST_ASSERT_EQUAL_STRING("emergency_stop", fault_name(Fault::emergency_stop));
    TEST_ASSERT_EQUAL_STRING("batch_timeout", fault_name(Fault::batch_timeout));
}

int main(int, char **)
{
    UNITY_BEGIN();
    RUN_TEST(test_recipe_validation_and_dose_rounding);
    RUN_TEST(test_nominal_batch_and_rinse_path);
    RUN_TEST(test_start_rejects_nonempty_tank);
    RUN_TEST(test_no_flow_fault_turns_everything_off);
    RUN_TEST(test_leak_and_io_failures_are_global);
    RUN_TEST(test_early_full_and_empty_during_mix_fault);
    RUN_TEST(test_irrigation_timeout_and_reset_guard);
    RUN_TEST(test_emergency_and_whole_batch_timeout_are_global);
    RUN_TEST(test_fill_timeout_is_distinct_from_no_flow_timeout);
    RUN_TEST(test_full_sensor_within_tolerance_advances_fill);
    RUN_TEST(test_rinse_drain_timeout_stops_irrigation);
    RUN_TEST(test_names_are_stable);
    return UNITY_END();
}
