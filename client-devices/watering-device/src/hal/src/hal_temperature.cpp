
#include <OneWire.h>
#include <DallasTemperature.h>

#include "hal_temperature.h"

// GPIO where the DS18B20 is connected to
#define ONE_WIRE_BUS GPIO_NUM_7

// Setup a oneWire instance to communicate with any OneWire devices
static OneWire oneWire(ONE_WIRE_BUS);

void hal_temperature_init()
{
    // NOP
}

/// @brief Deinitialize the temperature sensor
/// @param type - The type of temperature to get
/// @return float - The temperature in the specified type. -1000 if error
/// @note The temperature is returned in the specified type
float hal_temperature_get(hal_temp_type_t type)
{
    // Pass our oneWire reference to Dallas Temperature sensor
    DallasTemperature sensors(&oneWire);
    sensors.begin();
    float temperature = 0.0;
    DallasTemperature::request_t result = sensors.requestTemperatures();
    delay(5000);
    if (!result.result)
    {
        Serial.println("Error: Could not read temperature data");
        return -1000;
    }
    switch (type)
    {
    case HAL_TEMP_C:
        temperature = sensors.getTempCByIndex(0);
        if (temperature == DEVICE_DISCONNECTED_C)
        {
            return -1000;
        }
        break;
    case HAL_TEMP_F:
        temperature = sensors.getTempFByIndex(0);
        if (temperature == DEVICE_DISCONNECTED_F)
        {
            return -1000;
        }
        break;
    default:
        return -1000;
    }
    delay(5000);

    return temperature;
}