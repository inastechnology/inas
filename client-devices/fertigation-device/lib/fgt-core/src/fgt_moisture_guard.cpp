#include "fgt_moisture_guard.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

namespace fgt
{

bool moisture_guard_config_valid(const MoistureGuardConfig &config)
{
    if (config.threshold_percent > 100) return false;
    if (config.source == MoistureSource::first || config.source == MoistureSource::average)
        return config.sensor_slave_id == 0 && config.sensor_baud == 0;
    return config.source == MoistureSource::sensor &&
           config.sensor_slave_id >= 1 && config.sensor_slave_id <= 247 &&
           (config.sensor_baud == 2400 || config.sensor_baud == 4800 || config.sensor_baud == 9600);
}

bool parse_moisture_source(const char *value, MoistureGuardConfig &config)
{
    if (value == nullptr || strlen(value) > 15) return false;
    MoistureGuardConfig next = config;
    next.sensor_slave_id = 0;
    next.sensor_baud = 0;
    if (strcmp(value, "first") == 0) next.source = MoistureSource::first;
    else if (strcmp(value, "average") == 0) next.source = MoistureSource::average;
    else
    {
        unsigned int baud = 0, slave = 0;
        char extra = 0;
        if (sscanf(value, "sensor:%u:%u%c", &baud, &slave, &extra) != 2 || slave > 247) return false;
        next.source = MoistureSource::sensor;
        next.sensor_baud = baud;
        next.sensor_slave_id = static_cast<uint8_t>(slave);
        char canonical[32];
        format_moisture_source(next, canonical, sizeof(canonical));
        if (strcmp(value, canonical) != 0) return false;
    }
    if (!moisture_guard_config_valid(next)) return false;
    config = next;
    return true;
}

void format_moisture_source(const MoistureGuardConfig &config, char *out, size_t size)
{
    if (config.source == MoistureSource::sensor)
        snprintf(out, size, "sensor:%lu:%u", static_cast<unsigned long>(config.sensor_baud), config.sensor_slave_id);
    else
        snprintf(out, size, "%s", config.source == MoistureSource::average ? "average" : "first");
}

MoistureReading select_moisture_reading(const MoistureGuardConfig &config,
                                      const MoistureSample *samples, size_t count)
{
    MoistureReading result;
    if (!moisture_guard_config_valid(config) || samples == nullptr || count > 8) return result;
    bool all_valid = true;
    float sum = 0;
    for (size_t i = 0; i < count; ++i)
    {
        const auto &sample = samples[i];
        if (!sample.enabled) continue;
        if (config.source == MoistureSource::sensor &&
            (sample.baud != config.sensor_baud || sample.slave_id != config.sensor_slave_id)) continue;
        ++result.sensor_count;
        const bool valid = moisture_sample_valid(sample.ok, sample.percent);
        all_valid = all_valid && valid;
        if (valid) sum += sample.percent;
        if (config.source == MoistureSource::first) break;
    }
    result.ok = result.sensor_count > 0 && all_valid &&
                (config.source != MoistureSource::sensor || result.sensor_count == 1);
    if (result.ok) result.percent = sum / result.sensor_count;
    return result;
}

bool moisture_sample_valid(bool read_ok, float moisture_percent)
{
    return read_ok && isfinite(moisture_percent) &&
           moisture_percent >= 0.0f && moisture_percent <= 100.0f;
}

MoistureGuardDecision decide_moisture_guard(const MoistureGuardConfig &config,
                                           bool read_ok, float moisture_percent)
{
    if (!config.enabled) return MoistureGuardDecision::allow;
    if (!moisture_guard_config_valid(config)) return MoistureGuardDecision::skip_invalid_config;
    // Missing feedback must not deprive plants of their scheduled irrigation.
    if (!moisture_sample_valid(read_ok, moisture_percent)) return MoistureGuardDecision::allow;
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
