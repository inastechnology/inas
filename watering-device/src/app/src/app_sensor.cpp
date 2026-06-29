#include "Arduino.h"
#include "app_def.h"
#include "app_config.h"
#include "app_network.h"
#include "app_sensor.h"

#include "hal_temperature.h"
#include "hal_tds.h"

void app_sensor_init()
{
    hal_tds_init();
    hal_temperature_init();
}
void app_sensor_deinit()
{
    hal_tds_deinit();
}

bool app_sensor_report(uint32_t seqId)
{
    float temperature = hal_temperature_get();
    float tds = 0.0;
    if (temperature <= -1000.0)
    {
        Serial.println("Failed to read temperature, using default value 25.0");
        tds = hal_tds_read(25.0);
    }
    else
    {
        tds = hal_tds_read(temperature);
    }

    char buf[256];
    snprintf(buf, sizeof(buf), "{\"temp\":%.2f,\"tds\":%.2f}", temperature, tds);
    Serial.println("Sensor Data:");
    Serial.println(buf);
    if (app_network_send(APP_MSG_TYPE_STATUS, (uint8_t *)buf, strlen(buf), seqId) == false)
    {
        Serial.println("Failed to send sensor data");
        return false;
    }

    return true;
}