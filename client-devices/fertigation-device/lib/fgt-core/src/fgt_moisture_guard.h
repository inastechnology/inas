#pragma once

#include <stdint.h>

namespace fgt
{

struct MoistureGuardConfig
{
    bool enabled = false;
    uint8_t threshold_percent = 40;
};

enum class MoistureGuardDecision : uint8_t
{
    allow = 0,
    skip_wet,
    skip_unavailable,
    skip_invalid_config,
};

bool moisture_sample_valid(bool read_ok, float moisture_percent);
MoistureGuardDecision decide_moisture_guard(const MoistureGuardConfig &config,
                                           bool read_ok, float moisture_percent);
const char *moisture_guard_skip_reason(MoistureGuardDecision decision);

} // namespace fgt
