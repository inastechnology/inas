#include "fgt_moisture_guard.h"

#include <math.h>

namespace fgt
{

bool moisture_sample_valid(bool read_ok, float moisture_percent)
{
    return read_ok && isfinite(moisture_percent) &&
           moisture_percent >= 0.0f && moisture_percent <= 100.0f;
}

MoistureGuardDecision decide_moisture_guard(const MoistureGuardConfig &config,
                                           bool read_ok, float moisture_percent)
{
    if (!config.enabled) return MoistureGuardDecision::allow;
    if (config.threshold_percent > 100) return MoistureGuardDecision::skip_invalid_config;
    if (!moisture_sample_valid(read_ok, moisture_percent)) return MoistureGuardDecision::skip_unavailable;
    return moisture_percent >= config.threshold_percent
               ? MoistureGuardDecision::skip_wet
               : MoistureGuardDecision::allow;
}

const char *moisture_guard_skip_reason(MoistureGuardDecision decision)
{
    switch (decision)
    {
    case MoistureGuardDecision::skip_wet: return "soil_moisture_high";
    case MoistureGuardDecision::skip_unavailable: return "soil_moisture_unavailable";
    case MoistureGuardDecision::skip_invalid_config: return "moisture_guard_invalid";
    default: return "none";
    }
}

} // namespace fgt
