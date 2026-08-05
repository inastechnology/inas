#pragma once

#include <stdint.h>

namespace fgt
{

enum class CommissioningSensorType : uint8_t
{
    soil,
    par,
};

enum class SensorIdentificationConfidence : uint8_t
{
    high,
    medium,
    tentative,
};

struct SensorIdentification
{
    CommissioningSensorType type = CommissioningSensorType::par;
    SensorIdentificationConfidence confidence =
        SensorIdentificationConfidence::tentative;
};

SensorIdentification identify_commissioning_sensor(
    bool soil_measurement_supported,
    bool soil_secondary_values_present,
    bool soil_signature_read,
    bool soil_signature_present,
    bool par_address_hint = false);

bool soil_measurement_values_plausible(uint16_t raw_moisture,
                                       uint16_t raw_temperature,
                                       uint16_t raw_ph);

const char *sensor_identification_confidence_name(
    SensorIdentificationConfidence confidence);

} // namespace fgt
