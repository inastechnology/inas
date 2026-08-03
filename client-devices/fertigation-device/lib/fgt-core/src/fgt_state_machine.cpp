#include "fgt_state_machine.h"

#include <limits.h>

namespace fgt
{

static uint32_t elapsed_since(uint32_t now_ms, uint32_t started_ms)
{
    return now_ms - started_ms;
}

uint32_t dose_duration_ms(uint32_t amount_ml, uint32_t rate_ml_min)
{
    if (amount_ml == 0)
    {
        return 0;
    }
    if (rate_ml_min == 0 || amount_ml > UINT32_MAX / 60000UL)
    {
        return UINT32_MAX;
    }
    const uint32_t numerator = amount_ml * 60000UL;
    return (numerator + rate_ml_min - 1UL) / rate_ml_min;
}

bool recipe_valid(const Recipe &recipe, const Limits &limits)
{
    if (limits.max_total_water_ml == 0 || limits.max_nutrient_ml == 0 ||
        limits.water_no_flow_timeout_ms == 0 || limits.max_fill_ms == 0 || limits.max_batch_ms == 0)
    {
        return false;
    }
    if (recipe.total_water_ml == 0 || recipe.total_water_ml > limits.max_total_water_ml ||
        recipe.initial_water_ml == 0 || recipe.initial_water_ml >= recipe.total_water_ml)
    {
        return false;
    }
    if (recipe.nutrient_a_ml > limits.max_nutrient_ml || recipe.nutrient_b_ml > limits.max_nutrient_ml)
    {
        return false;
    }
    if ((recipe.nutrient_a_ml > 0 && recipe.nutrient_a_rate_ml_min == 0) ||
        (recipe.nutrient_b_ml > 0 && recipe.nutrient_b_rate_ml_min == 0))
    {
        return false;
    }
    if (recipe.initial_fill_ms == 0 || recipe.final_fill_ms == 0 ||
        recipe.pre_mix_ms == 0 || recipe.final_mix_ms == 0 || recipe.irrigation_max_ms == 0)
    {
        return false;
    }
    if (recipe.rinse_water_ml > limits.max_total_water_ml ||
        (recipe.rinse_water_ml > 0 &&
         (recipe.rinse_fill_ms == 0 || recipe.rinse_mix_ms == 0 || recipe.rinse_drain_max_ms == 0)))
    {
        return false;
    }
    return dose_duration_ms(recipe.nutrient_a_ml, recipe.nutrient_a_rate_ml_min) != UINT32_MAX &&
           dose_duration_ms(recipe.nutrient_b_ml, recipe.nutrient_b_rate_ml_min) != UINT32_MAX;
}

const char *phase_name(Phase phase)
{
    switch (phase)
    {
    case Phase::idle: return "idle";
    case Phase::initial_fill: return "initial_fill";
    case Phase::pre_mix: return "pre_mix";
    case Phase::dose_a: return "dose_a";
    case Phase::mix_after_a: return "mix_after_a";
    case Phase::dose_b: return "dose_b";
    case Phase::mix_after_b: return "mix_after_b";
    case Phase::final_fill: return "final_fill";
    case Phase::final_mix: return "final_mix";
    case Phase::irrigation: return "irrigation";
    case Phase::rinse_fill: return "rinse_fill";
    case Phase::rinse_mix: return "rinse_mix";
    case Phase::rinse_drain: return "rinse_drain";
    case Phase::complete: return "complete";
    case Phase::fault: return "fault";
    }
    return "unknown";
}

const char *fault_name(Fault fault)
{
    switch (fault)
    {
    case Fault::none: return "none";
    case Fault::invalid_recipe: return "invalid_recipe";
    case Fault::tank_not_empty: return "tank_not_empty";
    case Fault::io_failure: return "io_failure";
    case Fault::leak_detected: return "leak_detected";
    case Fault::emergency_stop: return "emergency_stop";
    case Fault::water_no_flow: return "water_no_flow";
    case Fault::unexpected_full: return "unexpected_full";
    case Fault::tank_empty_during_mix: return "tank_empty_during_mix";
    case Fault::fill_timeout: return "fill_timeout";
    case Fault::irrigation_timeout: return "irrigation_timeout";
    case Fault::rinse_drain_timeout: return "rinse_drain_timeout";
    case Fault::batch_timeout: return "batch_timeout";
    }
    return "unknown";
}

bool StateMachine::start(const Recipe &recipe, const Limits &limits, const Inputs &inputs, uint32_t now_ms)
{
    m_recipe = recipe;
    m_limits = limits;
    m_batch_started_ms = now_ms;
    m_phase_started_ms = now_ms;
    m_batch_flow_baseline_ml = inputs.inlet_water_ml;
    m_fill_flow_baseline_ml = inputs.inlet_water_ml;
    m_last_flow_ml = inputs.inlet_water_ml;
    m_last_flow_progress_ms = now_ms;
    m_fault = Fault::none;
    m_outputs = {};

    if (!recipe_valid(recipe, limits))
    {
        fail(Fault::invalid_recipe, now_ms);
        return false;
    }
    enter(Phase::initial_fill, now_ms, inputs);
    return true;
}

Snapshot StateMachine::tick(const Inputs &inputs, uint32_t now_ms)
{
    if (!active())
    {
        return snapshot(now_ms);
    }
    if (!check_global_safety(inputs, now_ms))
    {
        return snapshot(now_ms);
    }

    switch (m_phase)
    {
    case Phase::initial_fill:
        if (phase_elapsed(now_ms) >= m_recipe.initial_fill_ms)
            enter(Phase::pre_mix, now_ms, inputs);
        break;
    case Phase::pre_mix:
        if (phase_elapsed(now_ms) >= m_recipe.pre_mix_ms)
            enter(m_recipe.nutrient_a_ml > 0 ? Phase::dose_a : Phase::mix_after_a, now_ms, inputs);
        break;
    case Phase::dose_a:
        if (phase_elapsed(now_ms) >= dose_duration_ms(m_recipe.nutrient_a_ml, m_recipe.nutrient_a_rate_ml_min))
            enter(Phase::mix_after_a, now_ms, inputs);
        break;
    case Phase::mix_after_a:
        if (phase_elapsed(now_ms) >= m_recipe.mix_after_a_ms)
            enter(m_recipe.nutrient_b_ml > 0 ? Phase::dose_b : Phase::mix_after_b, now_ms, inputs);
        break;
    case Phase::dose_b:
        if (phase_elapsed(now_ms) >= dose_duration_ms(m_recipe.nutrient_b_ml, m_recipe.nutrient_b_rate_ml_min))
            enter(Phase::mix_after_b, now_ms, inputs);
        break;
    case Phase::mix_after_b:
        if (phase_elapsed(now_ms) >= m_recipe.mix_after_b_ms)
            enter(Phase::final_fill, now_ms, inputs);
        break;
    case Phase::final_fill:
        if (phase_elapsed(now_ms) >= m_recipe.final_fill_ms)
            enter(Phase::final_mix, now_ms, inputs);
        break;
    case Phase::final_mix:
        if (phase_elapsed(now_ms) >= m_recipe.final_mix_ms)
            enter(Phase::irrigation, now_ms, inputs);
        break;
    case Phase::irrigation:
        if (phase_elapsed(now_ms) >= m_recipe.irrigation_max_ms)
            enter(m_recipe.rinse_water_ml > 0 ? Phase::rinse_fill : Phase::complete, now_ms, inputs);
        break;
    case Phase::rinse_fill:
        if (phase_elapsed(now_ms) >= m_recipe.rinse_fill_ms)
            enter(Phase::rinse_mix, now_ms, inputs);
        break;
    case Phase::rinse_mix:
        if (phase_elapsed(now_ms) >= m_recipe.rinse_mix_ms)
            enter(Phase::rinse_drain, now_ms, inputs);
        break;
    case Phase::rinse_drain:
        if (phase_elapsed(now_ms) >= m_recipe.rinse_drain_max_ms)
            enter(Phase::complete, now_ms, inputs);
        break;
    default:
        break;
    }

    return snapshot(now_ms);
}

bool StateMachine::reset(const Inputs &inputs)
{
    if (!inputs.io_ok || inputs.leak_detected || inputs.emergency_stop || !inputs.tank_empty || inputs.tank_full)
    {
        return false;
    }
    m_phase = Phase::idle;
    m_fault = Fault::none;
    m_outputs = {};
    return true;
}

Snapshot StateMachine::snapshot(uint32_t now_ms) const
{
    Snapshot result = {};
    result.phase = m_phase;
    result.fault = m_fault;
    result.outputs = m_outputs;
    result.phase_elapsed_ms = phase_elapsed(now_ms);
    result.batch_elapsed_ms = batch_elapsed(now_ms);
    result.inlet_water_ml = m_last_flow_ml - m_batch_flow_baseline_ml;
    if (m_phase == Phase::initial_fill) result.target_water_ml = m_recipe.initial_water_ml;
    else if (m_phase == Phase::final_fill) result.target_water_ml = m_recipe.total_water_ml;
    else if (m_phase == Phase::rinse_fill) result.target_water_ml = m_recipe.rinse_water_ml;
    else result.target_water_ml = m_recipe.total_water_ml;
    return result;
}

bool StateMachine::active() const
{
    return m_phase != Phase::idle && m_phase != Phase::complete && m_phase != Phase::fault;
}

void StateMachine::enter(Phase phase, uint32_t now_ms, const Inputs &inputs)
{
    m_phase = phase;
    m_phase_started_ms = now_ms;
    if (phase == Phase::initial_fill || phase == Phase::final_fill || phase == Phase::rinse_fill)
    {
        m_fill_flow_baseline_ml = inputs.inlet_water_ml;
        m_last_flow_ml = inputs.inlet_water_ml;
        m_last_flow_progress_ms = now_ms;
    }
    update_outputs();
}

void StateMachine::fail(Fault fault, uint32_t now_ms)
{
    m_fault = fault;
    m_phase = Phase::fault;
    m_phase_started_ms = now_ms;
    m_outputs = {};
}

uint32_t StateMachine::phase_elapsed(uint32_t now_ms) const
{
    return elapsed_since(now_ms, m_phase_started_ms);
}

uint32_t StateMachine::batch_elapsed(uint32_t now_ms) const
{
    if (m_phase == Phase::idle)
    {
        return 0;
    }
    return elapsed_since(now_ms, m_batch_started_ms);
}

uint32_t StateMachine::batch_water_ml(const Inputs &inputs) const
{
    return inputs.inlet_water_ml - m_batch_flow_baseline_ml;
}

uint32_t StateMachine::fill_water_ml(const Inputs &inputs) const
{
    return inputs.inlet_water_ml - m_fill_flow_baseline_ml;
}

bool StateMachine::check_global_safety(const Inputs &inputs, uint32_t now_ms)
{
    if (!inputs.io_ok) fail(Fault::io_failure, now_ms);
    else if (inputs.leak_detected) fail(Fault::leak_detected, now_ms);
    else if (inputs.emergency_stop) fail(Fault::emergency_stop, now_ms);
    else if (batch_elapsed(now_ms) >= m_limits.max_batch_ms) fail(Fault::batch_timeout, now_ms);
    return m_phase != Phase::fault;
}

bool StateMachine::check_fill_progress(const Inputs &inputs, uint32_t now_ms)
{
    if (inputs.inlet_water_ml != m_last_flow_ml)
    {
        m_last_flow_ml = inputs.inlet_water_ml;
        m_last_flow_progress_ms = now_ms;
    }
    if (elapsed_since(now_ms, m_last_flow_progress_ms) >= m_limits.water_no_flow_timeout_ms)
    {
        fail(Fault::water_no_flow, now_ms);
        return false;
    }
    return true;
}

bool StateMachine::full_too_early(uint32_t delivered_ml, uint32_t target_ml) const
{
    if (delivered_ml >= target_ml)
    {
        return false;
    }
    return target_ml - delivered_ml > m_limits.volume_tolerance_ml;
}

void StateMachine::update_outputs()
{
    m_outputs = {};
    switch (m_phase)
    {
    case Phase::initial_fill:
    case Phase::rinse_fill:
        m_outputs.water_inlet = true;
        break;
    case Phase::pre_mix:
    case Phase::mix_after_a:
    case Phase::mix_after_b:
    case Phase::final_mix:
    case Phase::rinse_mix:
        m_outputs.mixer = true;
        break;
    case Phase::dose_a:
        m_outputs.nutrient_a = true;
        m_outputs.mixer = true;
        break;
    case Phase::dose_b:
        m_outputs.nutrient_b = true;
        m_outputs.mixer = true;
        break;
    case Phase::final_fill:
        m_outputs.water_inlet = true;
        m_outputs.mixer = true;
        break;
    case Phase::irrigation:
    case Phase::rinse_drain:
        m_outputs.irrigation = true;
        break;
    default:
        break;
    }
}

} // namespace fgt
