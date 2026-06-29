#pragma once

#include <Arduino.h>
#include <stdio.h>
#include <string.h>

#include "hal_config.h"
#include "app_def.h"
#include "app_utils.h"

#define APP_CONFIG_MAGIC 0x011AD1CE
#define DEVICE_ID_PREFIX "INADS-"
#define APP_UNIQUE_ID_SIZE (36)
#define DEVICE_ID_LEN (sizeof(DEVICE_ID_PREFIX) - 1 + APP_UNIQUE_ID_SIZE + 1)

#pragma pack(push, 1)
class AppConfig
{
public:
    // Magic number
    uint32_t magic = APP_CONFIG_MAGIC;
    // Device ID e.g. INADS-{PICO_UNIQUE_BOARD_ID}
    char device_id[DEVICE_ID_LEN];
    // SSID
    char ssid[256];
    // Password
    char password[256];
    // MQTT Broker
    char mqtt_broker[256];
    // MQTT Port
    uint16_t mqtt_port;
    // MQTT Username
    char mqtt_username[256];
    // MQTT Password
    char mqtt_password[256];
    // CRC32
    uint32_t crc32;

    AppConfig()
    {
        memset(this, 0, sizeof(AppConfig));
    }

    /// @brief Initialize the configuration
    /// @note Please call this function before using the configuration
    /// @return void
    void init()
    {
        // load the configuration from flash
        if (false == load())
        {
            Serial.printf("Configuration has not been initialized.\n");
            // if not, set the default values
            set_default();

            // save device identity and blank setup defaults to flash
            save();
        }
        show();
    }

    /// @brief Set the default values
    /// @return void
    void set_default()
    {
        // initialize memory
        memset(this, 0, sizeof(AppConfig));

        // set magic number
        magic = APP_CONFIG_MAGIC;

        // write the default values
        std::string uuid = AppUtils().generate_uuid_v4();

        sprintf(device_id, "INADS-%s", uuid.c_str());
        Serial.printf("Generate Device ID: %s\n", device_id);

        apply_network_defaults();

        // set crc32
        crc32 = AppUtils().crc32((const uint8_t *)this, sizeof(AppConfig) - sizeof(uint32_t));
    }

    /// @brief Restore build-time defaults while keeping the device identity when possible
    /// @return void
    void reset_to_factory_defaults()
    {
        char current_device_id[DEVICE_ID_LEN];
        memset(current_device_id, 0, sizeof(current_device_id));
        if (strncmp(device_id, DEVICE_ID_PREFIX, strlen(DEVICE_ID_PREFIX)) == 0)
        {
            strncpy(current_device_id, device_id, sizeof(current_device_id) - 1);
        }

        set_default();

        if (strlen(current_device_id) > 0)
        {
            strncpy(device_id, current_device_id, sizeof(device_id) - 1);
            device_id[sizeof(device_id) - 1] = '\0';
        }

        crc32 = AppUtils().crc32((const uint8_t *)this, sizeof(AppConfig) - sizeof(uint32_t));
    }

    /// @brief Clear saved Wi-Fi / MQTT connection settings while preserving device identity
    /// @return void
    void clear_connection_settings()
    {
        ssid[0] = '\0';
        password[0] = '\0';
        mqtt_broker[0] = '\0';
        mqtt_port = APP_MQTT_BROKER_PORT;
        mqtt_username[0] = '\0';
        mqtt_password[0] = '\0';
        crc32 = AppUtils().crc32((const uint8_t *)this, sizeof(AppConfig) - sizeof(uint32_t));
    }

    /// @brief Apply build-time network defaults (Wi-Fi / MQTT)
    /// @return void
    void apply_network_defaults()
    {
        strcpy(ssid, APP_WIFI_SSID);
        Serial.printf("Set default Wi-Fi SSID: %s\n", strlen(ssid) > 0 ? ssid : "(empty)");

        strcpy(password, APP_WIFI_PASS);
        Serial.printf("Set default Wi-Fi Password: %s (len=%u)\n",
                      strlen(password) > 0 ? "[SET]" : "(empty)",
                      static_cast<unsigned int>(strlen(password)));

        strcpy(mqtt_broker, APP_MQTT_BROKER_ADDR);
        Serial.printf("Set default MQTT Broker: %s\n", strlen(mqtt_broker) > 0 ? mqtt_broker : "(empty)");

        mqtt_port = APP_MQTT_BROKER_PORT;
        Serial.printf("Set MQTT Port: %d\n", mqtt_port);

        strcpy(mqtt_username, APP_MQTT_USERNAME);
        Serial.printf("Set default MQTT Username: %s\n", strlen(mqtt_username) > 0 ? mqtt_username : "(empty)");

        strcpy(mqtt_password, APP_MQTT_PASSWORD);
        Serial.printf("Set default MQTT Password: %s (len=%u)\n",
                      strlen(mqtt_password) > 0 ? "[SET]" : "(empty)",
                      static_cast<unsigned int>(strlen(mqtt_password)));
    }

    /// @brief Save the configuration to rom
    /// @return void
    void save()
    {
        HAL_config_save((const uint8_t *)this, sizeof(AppConfig));
    }

    /// @brief Load the configuration from rom
    /// @return bool - true if the configuration has been initialized
    bool load()
    {
        if (!HAL_config_load((uint8_t *)this, sizeof(AppConfig)))
        {
            return false;
        }

        if (!validate())
        {
            Serial.printf("Saved configuration is invalid.\n");
            return false;
        }

        return true;
    }

    bool validate()
    {
        // validate the configuration
        if (magic != APP_CONFIG_MAGIC)
        {
            Serial.printf("Invalid config: magic mismatch actual=0x%08X expected=0x%08X\n", magic, APP_CONFIG_MAGIC);
            return false;
        }

        if (strlen(device_id) == 0)
        {
            Serial.println("Invalid config: device_id is empty");
            return false;
        }

        if (mqtt_port == 0)
        {
            Serial.println("Invalid config: mqtt_port is 0");
            return false;
        }

        const bool hasMqttUsername = strlen(mqtt_username) > 0;
        const bool hasMqttPassword = strlen(mqtt_password) > 0;
        if (hasMqttUsername != hasMqttPassword)
        {
            Serial.printf("Invalid config: MQTT auth mismatch username=%s password=%s\n",
                          hasMqttUsername ? "set" : "empty",
                          hasMqttPassword ? "set" : "empty");
            return false;
        }

        // validate the CRC32
        const uint32_t expected_crc32 = AppUtils().crc32((const uint8_t *)this, sizeof(AppConfig) - sizeof(uint32_t));
        if (crc32 != expected_crc32)
        {
            Serial.printf("Invalid config: CRC mismatch actual=0x%08X expected=0x%08X\n", crc32, expected_crc32);
            return false;
        }

        return true;
    }

    bool is_network_configured()
    {
        return strlen(ssid) > 0 &&
               strlen(password) > 0 &&
               strlen(mqtt_broker) > 0 &&
               mqtt_port > 0;
    }

    /// @brief Show the configuration
    /// @return void
    void show()
    {
        const bool has_wifi_password = strlen(password) > 0;
        const bool has_mqtt_password = strlen(mqtt_password) > 0;

        Serial.println("===== Saved Configuration =====");
        Serial.printf("Device ID: %s\n", device_id);
        Serial.printf("Wi-Fi SSID: %s\n", strlen(ssid) > 0 ? ssid : "(empty)");
        Serial.printf("Wi-Fi Password: %s (len=%u)\n",
                      has_wifi_password ? "[SET]" : "(empty)",
                      static_cast<unsigned int>(strlen(password)));
        Serial.printf("MQTT Broker: %s\n", strlen(mqtt_broker) > 0 ? mqtt_broker : "(empty)");
        Serial.printf("MQTT Port: %d\n", mqtt_port);
        Serial.printf("MQTT Username: %s\n", strlen(mqtt_username) > 0 ? mqtt_username : "(empty)");
        Serial.printf("MQTT Password: %s (len=%u)\n",
                      has_mqtt_password ? "[SET]" : "(empty)",
                      static_cast<unsigned int>(strlen(mqtt_password)));
        Serial.printf("Network Configured: %s\n", is_network_configured() ? "yes" : "no");
        Serial.printf("CRC32: 0x%08X\n", crc32);
        Serial.println("================================");
    }
};
#pragma pack(pop)

extern AppConfig appConfig;
