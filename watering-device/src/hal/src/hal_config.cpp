#include "hal_config.h"
#include <cstring>
#include <LittleFS.h>

/// @brief Save the configuration to rom
/// @return void
void HAL_config_save(const uint8_t *data, size_t size)
{
    File file = LittleFS.open("/.config", "w");
    if (!file)
    {
        Serial.println("File open failed");
        return;
    }

    size_t write_size = file.write(data, size);
    if (write_size != size)
    {
        Serial.println("File write failed");
        return;
    }

    file.close();
}

bool HAL_config_exists()
{
    return LittleFS.exists("/.config");
}

/// @brief Load the configuration from flash
/// @return bool - true if the configuration is valid
bool HAL_config_load(uint8_t *data, size_t size)
{
    // is exist .config file?
    if (!HAL_config_exists())
    {
        Serial.println(".config file does not exist");
        return false;
    }

    File file = LittleFS.open("/.config", "r");
    if (!file)
    {
        Serial.println("File open failed");
        return false;
    }

    size_t read_size = file.read(data, size);
    if (read_size != size)
    {
        Serial.println("File read failed");
        file.close();
        return false;
    }

    file.close();
    return true;
}
