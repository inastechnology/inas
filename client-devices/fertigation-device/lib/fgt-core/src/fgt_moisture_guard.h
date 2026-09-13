#pragma once

#include <stdint.h>
#include <stddef.h>

namespace fgt
{

enum class MoistureSource : uint8_t { first = 0, sensor, average };

struct MoistureGuardConfig
{
    bool enabled = false;
    uint8_t threshold_percent = 40;
    MoistureSource source = MoistureSource::first;
    uint8_t sensor_slave_id = 0;
    uint32_t sensor_baud = 0;
};

struct MoistureSample
{
    uint32_t baud = 0;
    uint8_t slave_id = 0;
    bool enabled = false;
    bool ok = false;
    float percent = 0;
};

struct MoistureReading
{
    bool ok = false;
    float percent = 0;
    uint8_t sensor_count = 0;
};

bool moisture_guard_config_valid(const MoistureGuardConfig &config);
bool parse_moisture_source(const char *value, MoistureGuardConfig &config);
void format_moisture_source(const MoistureGuardConfig &config, char *out, size_t size);
MoistureReading select_moisture_reading(const MoistureGuardConfig &config,
                                      const MoistureSample *samples, size_t count);

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
