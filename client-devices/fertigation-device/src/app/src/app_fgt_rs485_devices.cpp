#include "app_fgt_rs485_devices.h"

#include <Arduino.h>
#include <LittleFS.h>

#include "app_utils.h"

namespace
{

constexpr const char *kRegistryFile = "/.fgt_rs485_devices";
constexpr const char *kRegistryTempFile = "/.fgt_rs485_devices.tmp";
constexpr const char *kRegistryBackupFile = "/.fgt_rs485_devices.bak";
constexpr uint32_t kRegistryMagic = 0x46475253UL;
constexpr uint16_t kRegistryStoreVersion = 1;

struct RegistryStore
{
    uint32_t magic = 0;
    uint16_t version = 0;
    uint16_t registry_size = 0;
    fgt::Rs485DeviceRegistry registry = {};
    uint32_t crc32 = 0;
};

fgt::Rs485DeviceRegistry s_registry = {};
bool s_initialized = false;
bool s_has_saved_registry = false;

uint32_t store_crc(const RegistryStore &store)
{
    return AppUtils::crc32(
        reinterpret_cast<const uint8_t *>(&store),
        sizeof(store) - sizeof(store.crc32));
}

bool read_store(const char *path, RegistryStore *store_out)
{
    if (path == nullptr || store_out == nullptr ||
        !LittleFS.exists(path))
    {
        return false;
    }
    File file = LittleFS.open(path, "r");
    if (!file)
    {
        return false;
    }
    RegistryStore store = {};
    const size_t read_size =
        file.read(reinterpret_cast<uint8_t *>(&store), sizeof(store));
    file.close();
    if (read_size != sizeof(store) ||
        store.magic != kRegistryMagic ||
        store.version != kRegistryStoreVersion ||
        store.registry_size != sizeof(store.registry) ||
        store.crc32 != store_crc(store) ||
        !fgt::rs485_registry_valid(store.registry))
    {
        return false;
    }
    *store_out = store;
    return true;
}

bool write_store(const fgt::Rs485DeviceRegistry &registry)
{
    if (!fgt::rs485_registry_valid(registry))
    {
        return false;
    }

    RegistryStore store = {};
    store.magic = kRegistryMagic;
    store.version = kRegistryStoreVersion;
    store.registry_size = sizeof(store.registry);
    store.registry = registry;
    store.crc32 = store_crc(store);

    LittleFS.remove(kRegistryTempFile);
    File file = LittleFS.open(kRegistryTempFile, "w");
    if (!file)
    {
        return false;
    }
    const size_t written =
        file.write(reinterpret_cast<const uint8_t *>(&store), sizeof(store));
    file.flush();
    file.close();
    if (written != sizeof(store))
    {
        LittleFS.remove(kRegistryTempFile);
        return false;
    }

    LittleFS.remove(kRegistryBackupFile);
    const bool had_current = LittleFS.exists(kRegistryFile);
    if (had_current &&
        !LittleFS.rename(kRegistryFile, kRegistryBackupFile))
    {
        LittleFS.remove(kRegistryTempFile);
        return false;
    }
    if (!LittleFS.rename(kRegistryTempFile, kRegistryFile))
    {
        if (had_current)
        {
            LittleFS.rename(kRegistryBackupFile, kRegistryFile);
        }
        LittleFS.remove(kRegistryTempFile);
        return false;
    }
    LittleFS.remove(kRegistryBackupFile);
    return true;
}

fgt::Rs485RegistryResult commit_registry(
    const fgt::Rs485DeviceRegistry &next)
{
    if (!write_store(next))
    {
        return fgt::Rs485RegistryResult::storage_error;
    }
    s_registry = next;
    s_has_saved_registry = true;
    return fgt::Rs485RegistryResult::ok;
}

} // namespace

void app_fgt_rs485_devices_init()
{
    if (s_initialized)
    {
        return;
    }
    s_initialized = true;
    s_registry = fgt::Rs485DeviceRegistry{};

    RegistryStore store = {};
    if (read_store(kRegistryFile, &store))
    {
        s_registry = store.registry;
        s_has_saved_registry = true;
    }
    else if (read_store(kRegistryBackupFile, &store))
    {
        s_registry = store.registry;
        s_has_saved_registry = true;
        write_store(s_registry);
        Serial.println(
            "Recovered FGT RS485 device registry from backup.");
    }
    else
    {
        s_has_saved_registry = false;
    }

    Serial.printf(
        "FGT RS485 device registry: saved=%s devices=%u\n",
        s_has_saved_registry ? "true" : "false",
        static_cast<unsigned int>(s_registry.count));
}

bool app_fgt_rs485_devices_has_saved_registry()
{
    return s_has_saved_registry;
}

const fgt::Rs485DeviceRegistry &app_fgt_rs485_devices_get()
{
    return s_registry;
}

fgt::Rs485RegistryResult app_fgt_rs485_devices_add(
    const fgt::Rs485DeviceConfig &device)
{
    fgt::Rs485DeviceRegistry next = s_registry;
    const fgt::Rs485RegistryResult result =
        fgt::rs485_registry_add(next, device);
    return result == fgt::Rs485RegistryResult::ok
               ? commit_registry(next)
               : result;
}

fgt::Rs485RegistryResult app_fgt_rs485_devices_update(
    size_t index,
    const fgt::Rs485DeviceConfig &device)
{
    fgt::Rs485DeviceRegistry next = s_registry;
    const fgt::Rs485RegistryResult result =
        fgt::rs485_registry_update(next, index, device);
    return result == fgt::Rs485RegistryResult::ok
               ? commit_registry(next)
               : result;
}

fgt::Rs485RegistryResult app_fgt_rs485_devices_remove(size_t index)
{
    fgt::Rs485DeviceRegistry next = s_registry;
    const fgt::Rs485RegistryResult result =
        fgt::rs485_registry_remove(next, index);
    return result == fgt::Rs485RegistryResult::ok
               ? commit_registry(next)
               : result;
}
