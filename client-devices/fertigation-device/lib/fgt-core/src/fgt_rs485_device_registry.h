#pragma once

#include <stddef.h>
#include <stdint.h>

namespace fgt
{

constexpr size_t kMaxRs485Devices = 8;
constexpr size_t kRs485DeviceNameSize = 64;
constexpr size_t kRs485DeviceLocationSize = 96;

enum class Rs485DeviceType : uint8_t
{
    soil,
    par,
};

struct Rs485DeviceConfig
{
    bool enabled = true;
    Rs485DeviceType type = Rs485DeviceType::soil;
    uint8_t slave_id = 1;
    uint32_t baud = 4800;
    uint8_t function_code = 0x03;
    uint16_t start_register = 0;
    uint8_t register_count = 1;
    float scale = 1.0F;
    char name[kRs485DeviceNameSize] = {};
    char location[kRs485DeviceLocationSize] = {};
};

struct Rs485DeviceRegistry
{
    uint8_t count = 0;
    Rs485DeviceConfig devices[kMaxRs485Devices] = {};
};

enum class Rs485RegistryResult : uint8_t
{
    ok,
    invalid,
    duplicate_address,
    full,
    not_found,
    storage_error,
};

bool rs485_device_config_valid(const Rs485DeviceConfig &device);
bool rs485_registry_valid(const Rs485DeviceRegistry &registry);
Rs485RegistryResult rs485_registry_add(
    Rs485DeviceRegistry &registry,
    const Rs485DeviceConfig &device);
Rs485RegistryResult rs485_registry_update(
    Rs485DeviceRegistry &registry,
    size_t index,
    const Rs485DeviceConfig &device);
Rs485RegistryResult rs485_registry_remove(
    Rs485DeviceRegistry &registry,
    size_t index);
int rs485_registry_find_address(
    const Rs485DeviceRegistry &registry,
    uint32_t baud,
    uint8_t slave_id,
    int excluded_index = -1);
const char *rs485_registry_result_name(Rs485RegistryResult result);

} // namespace fgt
