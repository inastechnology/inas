#include "fgt_sensor_diagnostics.h"

namespace fgt
{

SensorIdentification identify_commissioning_sensor(
    bool soil_measurement_supported,
    bool soil_secondary_values_present,
    bool soil_signature_read,
    bool soil_signature_present,
    bool par_address_hint)
{
    // The FGT commissioning topology reserves Modbus address 3 for the PAR
    // sensor. Some SEN0641 revisions answer multi-register reads with non-zero
    // values, so those generic reads cannot override the configured address.
    if (par_address_hint)
    {
        return {
            CommissioningSensorType::par,
            SensorIdentificationConfidence::medium,
        };
    }
    if (!soil_measurement_supported)
    {
        return {
            CommissioningSensorType::par,
            SensorIdentificationConfidence::high,
        };
    }
    if (soil_signature_read && soil_signature_present)
    {
        return {
            CommissioningSensorType::soil,
            SensorIdentificationConfidence::high,
        };
    }
    if (soil_secondary_values_present)
    {
        return {
            CommissioningSensorType::soil,
            SensorIdentificationConfidence::medium,
        };
    }
    return {
        CommissioningSensorType::par,
        SensorIdentificationConfidence::tentative,
    };
}

bool soil_measurement_values_plausible(uint16_t raw_moisture,
                                       uint16_t raw_temperature,
                                       uint16_t raw_ec)
{
    const int16_t signed_temperature = static_cast<int16_t>(raw_temperature);
    return raw_moisture <= 1000 &&
           signed_temperature >= -400 &&
           signed_temperature <= 850 &&
           raw_ec <= 20000;
}

const char *sensor_identification_confidence_name(
    SensorIdentificationConfidence confidence)
{
    switch (confidence)
    {
    case SensorIdentificationConfidence::high:
        return "high";
    case SensorIdentificationConfidence::medium:
        return "medium";
    case SensorIdentificationConfidence::tentative:
        return "tentative";
    }
    return "tentative";
}

} // namespace fgt
