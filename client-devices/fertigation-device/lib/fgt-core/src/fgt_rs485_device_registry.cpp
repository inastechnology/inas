#include "fgt_rs485_device_registry.h"

#include <string.h>

namespace fgt
{

namespace
{

bool terminated_nonempty_string(const char *value, size_t capacity)
{
    return value != nullptr &&
           value[0] != '\0' &&
           memchr(value, '\0', capacity) != nullptr;
}

bool supported_baud(uint32_t baud)
{
    return baud == 2400 || baud == 4800 || baud == 9600;
}

} // namespace

bool rs485_device_config_valid(const Rs485DeviceConfig &device)
{
    if (device.slave_id == 0 || device.slave_id > 247 ||
        !supported_baud(device.baud) ||
        (device.function_code != 0x03 &&
         device.function_code != 0x04) ||
        device.register_count == 0 ||
        device.register_count > 32 ||
        device.scale <= 0.0F ||
        !terminated_nonempty_string(device.name, sizeof(device.name)) ||
        memchr(device.location, '\0', sizeof(device.location)) == nullptr)
    {
        return false;
    }

    switch (device.type)
    {
    case Rs485DeviceType::soil:
        return device.register_count == 7;
    case Rs485DeviceType::par:
        return device.register_count == 1;
    }
    return false;
}

bool rs485_registry_valid(const Rs485DeviceRegistry &registry)
{
    if (registry.count > kMaxRs485Devices)
    {
        return false;
    }
    for (size_t i = 0; i < registry.count; ++i)
    {
        if (!rs485_device_config_valid(registry.devices[i]) ||
            rs485_registry_find_address(
                registry,
                registry.devices[i].baud,
                registry.devices[i].slave_id,
                static_cast<int>(i)) >= 0)
        {
            return false;
        }
    }
    return true;
}

Rs485RegistryResult rs485_registry_add(
    Rs485DeviceRegistry &registry,
    const Rs485DeviceConfig &device)
{
    if (!rs485_device_config_valid(device))
    {
        return Rs485RegistryResult::invalid;
    }
    if (registry.count >= kMaxRs485Devices)
    {
        return Rs485RegistryResult::full;
    }
    if (rs485_registry_find_address(
            registry, device.baud, device.slave_id) >= 0)
    {
        return Rs485RegistryResult::duplicate_address;
    }
    registry.devices[registry.count++] = device;
    return Rs485RegistryResult::ok;
}

Rs485RegistryResult rs485_registry_update(
    Rs485DeviceRegistry &registry,
    size_t index,
    const Rs485DeviceConfig &device)
{
    if (index >= registry.count)
    {
        return Rs485RegistryResult::not_found;
    }
    if (!rs485_device_config_valid(device))
    {
        return Rs485RegistryResult::invalid;
    }
    if (rs485_registry_find_address(
            registry,
            device.baud,
            device.slave_id,
            static_cast<int>(index)) >= 0)
    {
        return Rs485RegistryResult::duplicate_address;
    }
    registry.devices[index] = device;
    return Rs485RegistryResult::ok;
}

Rs485RegistryResult rs485_registry_remove(
    Rs485DeviceRegistry &registry,
    size_t index)
{
    if (index >= registry.count)
    {
        return Rs485RegistryResult::not_found;
    }
    for (size_t i = index; i + 1 < registry.count; ++i)
    {
        registry.devices[i] = registry.devices[i + 1];
    }
    --registry.count;
    registry.devices[registry.count] = Rs485DeviceConfig{};
    return Rs485RegistryResult::ok;
}

int rs485_registry_find_address(
    const Rs485DeviceRegistry &registry,
    uint32_t baud,
    uint8_t slave_id,
    int excluded_index)
{
    for (size_t i = 0; i < registry.count; ++i)
    {
        if (static_cast<int>(i) != excluded_index &&
            registry.devices[i].baud == baud &&
            registry.devices[i].slave_id == slave_id)
        {
            return static_cast<int>(i);
        }
    }
    return -1;
}

const char *rs485_registry_result_name(Rs485RegistryResult result)
{
    switch (result)
    {
    case Rs485RegistryResult::ok:
        return "ok";
    case Rs485RegistryResult::invalid:
        return "invalid";
    case Rs485RegistryResult::duplicate_address:
        return "duplicate_address";
    case Rs485RegistryResult::full:
        return "full";
    case Rs485RegistryResult::not_found:
        return "not_found";
    case Rs485RegistryResult::storage_error:
        return "storage_error";
    }
    return "invalid";
}

} // namespace fgt
