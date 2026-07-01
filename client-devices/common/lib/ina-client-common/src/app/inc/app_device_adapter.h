#pragma once

#include <stddef.h>
#include <stdint.h>

class AppDeviceAdapter
{
public:
    virtual ~AppDeviceAdapter() = default;

    virtual bool apply_runtime_config_json(const uint8_t *payload, size_t length) = 0;
    virtual bool has_valid_runtime_config() const = 0;
    virtual bool is_runtime_config_received() const = 0;
};

void app_device_adapter_set(AppDeviceAdapter *adapter);
AppDeviceAdapter *app_device_adapter_get();
bool app_device_adapter_apply_runtime_config_json(const uint8_t *payload, size_t length);
bool app_device_adapter_has_valid_runtime_config();
bool app_device_adapter_is_runtime_config_received();
