#include <unity.h>

#include "fgt_commissioning_interlock.h"
#include "fgt_state_machine.h"

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

int main(int argc, char **argv)
{
    UNITY_BEGIN();
    RUN_TEST(test_recipe_validation_and_duration_rounding);
    RUN_TEST(test_nominal_time_calibrated_batch);
    RUN_TEST(test_zero_nutrients_and_rinse_skip_optional_phases);
    RUN_TEST(test_global_faults_turn_everything_off);
    RUN_TEST(test_batch_timeout_turns_everything_off);
    RUN_TEST(test_commissioning_allows_only_one_output);
    RUN_TEST(test_commissioning_guard_period_starts_after_off);
    RUN_TEST(test_commissioning_auto_off_and_duration_limits);
    return UNITY_END();
}
