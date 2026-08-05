#include "app_fgt_rs485_devices.h"

#include <Arduino.h>
#include <LittleFS.h>
#include <memory>
#include <new>

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
const char *s_last_storage_error = "none";

uint32_t store_crc(const RegistryStore &store)
{
    return AppUtils::crc32(
        reinterpret_cast<const uint8_t *>(&store),
        sizeof(store) - sizeof(store.crc32));
}

bool read_store(const char *path,
                RegistryStore *store_out,
                bool *legacy_soil_profile_migrated = nullptr)
{
    if (legacy_soil_profile_migrated != nullptr)
    {
        *legacy_soil_profile_migrated = false;
    }
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
    *store_out = RegistryStore{};
    const size_t read_size =
        file.read(
            reinterpret_cast<uint8_t *>(store_out),
            sizeof(*store_out));
    file.close();
    if (read_size != sizeof(*store_out) ||
        store_out->magic != kRegistryMagic ||
        store_out->version != kRegistryStoreVersion ||
        store_out->registry_size != sizeof(store_out->registry) ||
        store_out->crc32 != store_crc(*store_out))
    {
        return false;
    }
    const bool migrated =
        fgt::rs485_registry_normalize_legacy_soil_register_counts(
            store_out->registry);
    if (!fgt::rs485_registry_valid(store_out->registry))
    {
        return false;
    }
    if (legacy_soil_profile_migrated != nullptr)
    {
        *legacy_soil_profile_migrated = migrated;
    }
    return true;
}

bool write_store(const fgt::Rs485DeviceRegistry &registry)
{
    if (!fgt::rs485_registry_valid(registry))
    {
        s_last_storage_error = "invalid_registry";
        return false;
    }

    std::unique_ptr<RegistryStore> store(
        new (std::nothrow) RegistryStore{});
    if (!store)
    {
        s_last_storage_error = "allocation_failed";
        return false;
    }
    store->magic = kRegistryMagic;
    store->version = kRegistryStoreVersion;
    store->registry_size = sizeof(store->registry);
    store->registry = registry;
    store->crc32 = store_crc(*store);
    const uint32_t expected_crc = store->crc32;

    LittleFS.remove(kRegistryTempFile);
    File file = LittleFS.open(kRegistryTempFile, "w");
    if (!file)
    {
        s_last_storage_error = "temp_open_failed";
        return false;
    }
    const size_t written =
        file.write(
            reinterpret_cast<const uint8_t *>(store.get()),
            sizeof(*store));
    file.flush();
    file.close();
    if (written != sizeof(*store))
    {
        s_last_storage_error = "temp_write_failed";
        LittleFS.remove(kRegistryTempFile);
        return false;
    }

    const bool had_current = LittleFS.exists(kRegistryFile);
    if (had_current)
    {
        LittleFS.remove(kRegistryBackupFile);
        if (!LittleFS.rename(
                kRegistryFile,
                kRegistryBackupFile))
        {
            s_last_storage_error = "backup_rename_failed";
            LittleFS.remove(kRegistryTempFile);
            return false;
        }
    }
    if (!LittleFS.rename(kRegistryTempFile, kRegistryFile))
    {
        s_last_storage_error = "commit_rename_failed";
        if (had_current &&
            !LittleFS.rename(
                kRegistryBackupFile,
                kRegistryFile))
        {
            s_last_storage_error =
                "commit_rollback_failed";
        }
        LittleFS.remove(kRegistryTempFile);
        return false;
    }

    if (!read_store(kRegistryFile, store.get()) ||
        store->crc32 != expected_crc)
    {
        s_last_storage_error = "readback_verification_failed";
        LittleFS.remove(kRegistryFile);
        if (had_current &&
            !LittleFS.rename(
                kRegistryBackupFile,
                kRegistryFile))
        {
            s_last_storage_error =
                "readback_rollback_failed";
        }
        return false;
    }

    LittleFS.remove(kRegistryBackupFile);
    s_last_storage_error = "none";
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

    std::unique_ptr<RegistryStore> store(
        new (std::nothrow) RegistryStore{});
    if (!store)
    {
        s_has_saved_registry = false;
        s_last_storage_error = "allocation_failed";
        Serial.println(
            "FGT RS485 device registry allocation failed.");
        return;
    }
    bool legacy_soil_profile_migrated = false;
    if (read_store(
            kRegistryFile,
            store.get(),
            &legacy_soil_profile_migrated))
    {
        s_registry = store->registry;
        s_has_saved_registry = true;
        if (legacy_soil_profile_migrated)
        {
            write_store(s_registry);
            Serial.println(
                "Migrated FGT soil sensor registry to the 3-register moisture/temperature/EC profile.");
        }
    }
    else if (read_store(kRegistryBackupFile, store.get()))
    {
        s_registry = store->registry;
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

const char *app_fgt_rs485_devices_last_storage_error()
{
    return s_last_storage_error;
}

size_t app_fgt_rs485_devices_registry_size()
{
    return sizeof(RegistryStore);
}

const fgt::Rs485DeviceRegistry &app_fgt_rs485_devices_get()
{
    return s_registry;
}

fgt::Rs485RegistryResult app_fgt_rs485_devices_add(
    const fgt::Rs485DeviceConfig &device)
{
    s_last_storage_error = "none";
    std::unique_ptr<fgt::Rs485DeviceRegistry> next(
        new (std::nothrow) fgt::Rs485DeviceRegistry{});
    if (!next)
    {
        s_last_storage_error = "allocation_failed";
        return fgt::Rs485RegistryResult::storage_error;
    }
    *next = s_registry;
    const fgt::Rs485RegistryResult result =
        fgt::rs485_registry_add(*next, device);
    return result == fgt::Rs485RegistryResult::ok
               ? commit_registry(*next)
               : result;
}

fgt::Rs485RegistryResult app_fgt_rs485_devices_update(
    size_t index,
    const fgt::Rs485DeviceConfig &device)
{
    s_last_storage_error = "none";
    std::unique_ptr<fgt::Rs485DeviceRegistry> next(
        new (std::nothrow) fgt::Rs485DeviceRegistry{});
    if (!next)
    {
        s_last_storage_error = "allocation_failed";
        return fgt::Rs485RegistryResult::storage_error;
    }
    *next = s_registry;
    const fgt::Rs485RegistryResult result =
        fgt::rs485_registry_update(*next, index, device);
    return result == fgt::Rs485RegistryResult::ok
               ? commit_registry(*next)
               : result;
}

fgt::Rs485RegistryResult app_fgt_rs485_devices_remove(size_t index)
{
    s_last_storage_error = "none";
    std::unique_ptr<fgt::Rs485DeviceRegistry> next(
        new (std::nothrow) fgt::Rs485DeviceRegistry{});
    if (!next)
    {
        s_last_storage_error = "allocation_failed";
        return fgt::Rs485RegistryResult::storage_error;
    }
    *next = s_registry;
    const fgt::Rs485RegistryResult result =
        fgt::rs485_registry_remove(*next, index);
    return result == fgt::Rs485RegistryResult::ok
               ? commit_registry(*next)
               : result;
}
