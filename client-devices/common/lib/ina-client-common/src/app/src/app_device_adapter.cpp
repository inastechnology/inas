#include "app_device_adapter.h"

static AppDeviceAdapter *s_device_adapter = nullptr;

void app_device_adapter_set(AppDeviceAdapter *adapter)
{
    s_device_adapter = adapter;
}

AppDeviceAdapter *app_device_adapter_get()
{
    return s_device_adapter;
}

bool app_device_adapter_apply_runtime_config_json(const uint8_t *payload, size_t length)
{
    return s_device_adapter != nullptr &&
           s_device_adapter->apply_runtime_config_json(payload, length);
}

bool app_device_adapter_has_valid_runtime_config()
{
    return s_device_adapter != nullptr &&
           s_device_adapter->has_valid_runtime_config();
}

bool app_device_adapter_is_runtime_config_received()
{
    return s_device_adapter != nullptr &&
           s_device_adapter->is_runtime_config_received();
}
