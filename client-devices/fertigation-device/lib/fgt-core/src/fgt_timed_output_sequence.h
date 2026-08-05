#pragma once

#include <stdint.h>

#include "fgt_state_machine.h"

namespace fgt
{

constexpr uint8_t kTimedOutputCount = 5;
constexpr uint8_t kTimedOutputMaxRepeats = 20;
constexpr uint32_t kTimedOutputMaxIntervalMs = 1800000UL;

enum class TimedOutput : uint8_t
{
    water_inlet = 0,
    nutrient_a = 1,
    nutrient_b = 2,
    mixer = 3,
    irrigation = 4,
};

enum class TimedPhase : uint8_t
{
    idle,
    output_on,
    output_off,
    complete,
    fault,
};

struct TimedOutputProgram
{
    uint32_t on_ms = 0;
    uint32_t off_ms = 0;
    uint8_t repeat_count = 0;
};

struct TimedProgram
{
    TimedOutputProgram outputs[kTimedOutputCount] = {};
    uint32_t max_sequence_ms = kTimedOutputMaxIntervalMs;
};

struct TimedSnapshot
{
    TimedPhase phase = TimedPhase::idle;
    Fault fault = Fault::none;
    Outputs outputs = {};
    TimedOutput active_output = TimedOutput::water_inlet;
    uint8_t repeat_number = 0;
    uint32_t phase_elapsed_ms = 0;
    uint32_t sequence_elapsed_ms = 0;
};

bool timed_program_valid(const TimedProgram &program);
uint32_t timed_program_duration_ms(const TimedProgram &program);
const char *timed_output_name(TimedOutput output);
const char *timed_phase_name(TimedPhase phase);

class TimedOutputSequence
{
public:
    bool start(const TimedProgram &program, const Inputs &inputs, uint32_t now_ms);
    TimedSnapshot tick(const Inputs &inputs, uint32_t now_ms);
    TimedSnapshot snapshot(uint32_t now_ms) const;
    bool active() const;

private:
    TimedProgram m_program = {};
    TimedPhase m_phase = TimedPhase::idle;
    Fault m_fault = Fault::none;
    Outputs m_outputs = {};
    uint8_t m_output_index = 0;
    uint8_t m_repeat_number = 0;
    uint32_t m_sequence_started_ms = 0;
    uint32_t m_phase_started_ms = 0;

    bool select_next_output(uint8_t first_index, uint32_t now_ms);
    bool check_global_safety(const Inputs &inputs, uint32_t now_ms);
    void enter(TimedPhase phase, uint32_t now_ms);
    void fail(Fault fault, uint32_t now_ms);
    void update_outputs();
    uint32_t phase_elapsed(uint32_t now_ms) const;
    uint32_t sequence_elapsed(uint32_t now_ms) const;
};

} // namespace fgt
