#pragma once

#include <stddef.h>

#include "fgt_rs485_device_registry.h"

void app_fgt_rs485_devices_init();
bool app_fgt_rs485_devices_has_saved_registry();
const fgt::Rs485DeviceRegistry &app_fgt_rs485_devices_get();
fgt::Rs485RegistryResult app_fgt_rs485_devices_add(
    const fgt::Rs485DeviceConfig &device);
fgt::Rs485RegistryResult app_fgt_rs485_devices_update(
    size_t index,
    const fgt::Rs485DeviceConfig &device);
fgt::Rs485RegistryResult app_fgt_rs485_devices_remove(size_t index);
