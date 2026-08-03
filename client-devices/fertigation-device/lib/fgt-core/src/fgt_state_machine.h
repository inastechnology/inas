#pragma once

#include <stdint.h>

namespace fgt
{

enum class Phase : uint8_t
{
    idle,
    initial_fill,
    pre_mix,
    dose_a,
    mix_after_a,
    dose_b,
    mix_after_b,
    final_fill,
    final_mix,
    irrigation,
    rinse_fill,
    rinse_mix,
    rinse_drain,
    complete,
    fault,
};

enum class Fault : uint8_t
{
    none,
    invalid_recipe,
    tank_not_empty,
    io_failure,
    leak_detected,
    emergency_stop,
    water_no_flow,
    unexpected_full,
    tank_empty_during_mix,
    fill_timeout,
    irrigation_timeout,
    rinse_drain_timeout,
    batch_timeout,
};

struct Recipe
{
    // Main nutrient-batch water. Rinse water is delivered afterward, so the
    // planned irrigation total is total_water_ml + rinse_water_ml.
    uint32_t total_water_ml = 4500;
    uint32_t initial_water_ml = 1250;
    uint32_t initial_fill_ms = 75000;
    uint32_t final_fill_ms = 195000;
    uint32_t nutrient_a_ml = 10;
    uint32_t nutrient_b_ml = 10;
    uint32_t nutrient_a_rate_ml_min = 100;
    uint32_t nutrient_b_rate_ml_min = 100;
    uint32_t pre_mix_ms = 10000;
    uint32_t mix_after_a_ms = 30000;
    uint32_t mix_after_b_ms = 60000;
    uint32_t final_mix_ms = 120000;
    uint32_t irrigation_max_ms = 300000;
    uint32_t rinse_water_ml = 500;
    uint32_t rinse_fill_ms = 30000;
    uint32_t rinse_mix_ms = 30000;
    uint32_t rinse_drain_max_ms = 60000;
};

struct Limits
{
    uint32_t max_total_water_ml = 10000;
    uint32_t max_nutrient_ml = 100;
    uint32_t water_no_flow_timeout_ms = 15000;
    uint32_t max_fill_ms = 300000;
    uint32_t max_batch_ms = 1800000;
    uint32_t volume_tolerance_ml = 100;
};

struct Inputs
{
    bool io_ok = true;
    bool tank_empty = true;
    bool tank_full = false;
    bool leak_detected = false;
    bool emergency_stop = false;
    uint32_t inlet_water_ml = 0;
};

struct Outputs
{
    bool water_inlet = false;
    bool nutrient_a = false;
    bool nutrient_b = false;
    bool mixer = false;
    bool irrigation = false;
};

struct Snapshot
{
    Phase phase = Phase::idle;
    Fault fault = Fault::none;
    Outputs outputs = {};
    uint32_t phase_elapsed_ms = 0;
    uint32_t batch_elapsed_ms = 0;
    uint32_t inlet_water_ml = 0;
    uint32_t target_water_ml = 0;
};

bool recipe_valid(const Recipe &recipe, const Limits &limits);
uint32_t dose_duration_ms(uint32_t amount_ml, uint32_t rate_ml_min);
const char *phase_name(Phase phase);
const char *fault_name(Fault fault);

class StateMachine
{
public:
    bool start(const Recipe &recipe, const Limits &limits, const Inputs &inputs, uint32_t now_ms);
    Snapshot tick(const Inputs &inputs, uint32_t now_ms);
    bool reset(const Inputs &inputs);
    Snapshot snapshot(uint32_t now_ms) const;
    bool active() const;

private:
    Recipe m_recipe = {};
    Limits m_limits = {};
    Phase m_phase = Phase::idle;
    Fault m_fault = Fault::none;
    Outputs m_outputs = {};
    uint32_t m_batch_started_ms = 0;
    uint32_t m_phase_started_ms = 0;
    uint32_t m_batch_flow_baseline_ml = 0;
    uint32_t m_fill_flow_baseline_ml = 0;
    uint32_t m_last_flow_ml = 0;
    uint32_t m_last_flow_progress_ms = 0;

    void enter(Phase phase, uint32_t now_ms, const Inputs &inputs);
    void fail(Fault fault, uint32_t now_ms);
    uint32_t phase_elapsed(uint32_t now_ms) const;
    uint32_t batch_elapsed(uint32_t now_ms) const;
    uint32_t batch_water_ml(const Inputs &inputs) const;
    uint32_t fill_water_ml(const Inputs &inputs) const;
    bool check_global_safety(const Inputs &inputs, uint32_t now_ms);
    bool check_fill_progress(const Inputs &inputs, uint32_t now_ms);
    bool full_too_early(uint32_t delivered_ml, uint32_t target_ml) const;
    void update_outputs();
};

} // namespace fgt
