#include "fgt_timed_output_sequence.h"

#include <limits.h>

namespace fgt
{

static uint32_t elapsed_since(uint32_t now_ms, uint32_t started_ms)
{
    return now_ms - started_ms;
}

static bool output_program_enabled(const TimedOutputProgram &program)
{
    return program.on_ms > 0 && program.repeat_count > 0;
}

uint32_t timed_program_duration_ms(const TimedProgram &program)
{
    uint64_t total = 0;
    for (uint8_t i = 0; i < kTimedOutputCount; ++i)
    {
        const TimedOutputProgram &output = program.outputs[i];
        if (!output_program_enabled(output)) continue;
        total += static_cast<uint64_t>(output.on_ms) * output.repeat_count;
        total += static_cast<uint64_t>(output.off_ms) * (output.repeat_count - 1U);
        if (total > UINT32_MAX) return UINT32_MAX;
    }
    return static_cast<uint32_t>(total);
}

bool timed_program_valid(const TimedProgram &program)
{
    if (program.max_sequence_ms == 0) return false;
    bool any_enabled = false;
    for (uint8_t i = 0; i < kTimedOutputCount; ++i)
    {
        const TimedOutputProgram &output = program.outputs[i];
        if (output.on_ms > kTimedOutputMaxIntervalMs ||
            output.off_ms > kTimedOutputMaxIntervalMs ||
            output.repeat_count > kTimedOutputMaxRepeats)
        {
            return false;
        }
        const bool fully_disabled = output.on_ms == 0 && output.repeat_count == 0;
        if (!fully_disabled && !output_program_enabled(output)) return false;
        any_enabled = any_enabled || output_program_enabled(output);
    }
    const uint32_t duration_ms = timed_program_duration_ms(program);
    return any_enabled && duration_ms != UINT32_MAX && duration_ms <= program.max_sequence_ms;
}

const char *timed_output_name(TimedOutput output)
{
    switch (output)
    {
    case TimedOutput::water_inlet: return "water_inlet";
    case TimedOutput::nutrient_a: return "nutrient_a";
    case TimedOutput::nutrient_b: return "nutrient_b";
    case TimedOutput::mixer: return "mixer";
    case TimedOutput::irrigation: return "irrigation";
    }
    return "unknown";
}

const char *timed_phase_name(TimedPhase phase)
{
    switch (phase)
    {
    case TimedPhase::idle: return "idle";
    case TimedPhase::output_on: return "timed_output_on";
    case TimedPhase::output_off: return "timed_output_off";
    case TimedPhase::complete: return "complete";
    case TimedPhase::fault: return "fault";
    }
    return "unknown";
}

bool TimedOutputSequence::start(const TimedProgram &program, const Inputs &inputs, uint32_t now_ms)
{
    m_program = program;
    m_phase = TimedPhase::idle;
    m_fault = Fault::none;
    m_outputs = {};
    m_output_index = 0;
    m_repeat_number = 0;
    m_sequence_started_ms = now_ms;
    m_phase_started_ms = now_ms;

    if (!timed_program_valid(program))
    {
        fail(Fault::invalid_recipe, now_ms);
        return false;
    }
    if (!check_global_safety(inputs, now_ms)) return false;
    if (!select_next_output(0, now_ms))
    {
        fail(Fault::invalid_recipe, now_ms);
        return false;
    }
    return true;
}

TimedSnapshot TimedOutputSequence::tick(const Inputs &inputs, uint32_t now_ms)
{
    if (!active()) return snapshot(now_ms);
    if (!check_global_safety(inputs, now_ms)) return snapshot(now_ms);

    const TimedOutputProgram &output = m_program.outputs[m_output_index];
    if (m_phase == TimedPhase::output_on && phase_elapsed(now_ms) >= output.on_ms)
    {
        if (m_repeat_number < output.repeat_count)
        {
            enter(output.off_ms > 0 ? TimedPhase::output_off : TimedPhase::output_on, now_ms);
        }
        else if (!select_next_output(static_cast<uint8_t>(m_output_index + 1U), now_ms))
        {
            enter(TimedPhase::complete, now_ms);
        }
    }
    else if (m_phase == TimedPhase::output_off && phase_elapsed(now_ms) >= output.off_ms)
    {
        enter(TimedPhase::output_on, now_ms);
    }
    if (active() && sequence_elapsed(now_ms) > m_program.max_sequence_ms)
    {
        fail(Fault::batch_timeout, now_ms);
    }
    return snapshot(now_ms);
}

TimedSnapshot TimedOutputSequence::snapshot(uint32_t now_ms) const
{
    TimedSnapshot result = {};
    result.phase = m_phase;
    result.fault = m_fault;
    result.outputs = m_outputs;
    result.active_output = static_cast<TimedOutput>(m_output_index);
    result.repeat_number = m_repeat_number;
    result.phase_elapsed_ms = phase_elapsed(now_ms);
    result.sequence_elapsed_ms = sequence_elapsed(now_ms);
    return result;
}

bool TimedOutputSequence::active() const
{
    return m_phase == TimedPhase::output_on || m_phase == TimedPhase::output_off;
}

bool TimedOutputSequence::select_next_output(uint8_t first_index, uint32_t now_ms)
{
    for (uint8_t i = first_index; i < kTimedOutputCount; ++i)
    {
        if (!output_program_enabled(m_program.outputs[i])) continue;
        m_output_index = i;
        m_repeat_number = 1;
        // Selecting a new output is not another repetition of the previous
        // output. apply_outputs() still provides the physical break-before-make.
        m_phase = TimedPhase::idle;
        enter(TimedPhase::output_on, now_ms);
        return true;
    }
    return false;
}

bool TimedOutputSequence::check_global_safety(const Inputs &inputs, uint32_t now_ms)
{
    if (!inputs.io_ok) fail(Fault::io_failure, now_ms);
    else if (inputs.leak_detected) fail(Fault::leak_detected, now_ms);
    else if (inputs.emergency_stop) fail(Fault::emergency_stop, now_ms);
    return m_phase != TimedPhase::fault;
}

void TimedOutputSequence::enter(TimedPhase phase, uint32_t now_ms)
{
    if (m_phase == TimedPhase::output_off && phase == TimedPhase::output_on)
    {
        ++m_repeat_number;
    }
    else if (m_phase == TimedPhase::output_on && phase == TimedPhase::output_on)
    {
        ++m_repeat_number;
    }
    m_phase = phase;
    m_phase_started_ms = now_ms;
    update_outputs();
}

void TimedOutputSequence::fail(Fault fault, uint32_t now_ms)
{
    m_fault = fault;
    m_phase = TimedPhase::fault;
    m_phase_started_ms = now_ms;
    m_outputs = {};
}

void TimedOutputSequence::update_outputs()
{
    m_outputs = {};
    if (m_phase != TimedPhase::output_on) return;
    switch (static_cast<TimedOutput>(m_output_index))
    {
    case TimedOutput::water_inlet: m_outputs.water_inlet = true; break;
    case TimedOutput::nutrient_a: m_outputs.nutrient_a = true; break;
    case TimedOutput::nutrient_b: m_outputs.nutrient_b = true; break;
    case TimedOutput::mixer: m_outputs.mixer = true; break;
    case TimedOutput::irrigation: m_outputs.irrigation = true; break;
    }
}

uint32_t TimedOutputSequence::phase_elapsed(uint32_t now_ms) const
{
    if (m_phase == TimedPhase::idle) return 0;
    return elapsed_since(now_ms, m_phase_started_ms);
}

uint32_t TimedOutputSequence::sequence_elapsed(uint32_t now_ms) const
{
    if (m_phase == TimedPhase::idle) return 0;
    return elapsed_since(now_ms, m_sequence_started_ms);
}

} // namespace fgt
