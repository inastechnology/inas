#pragma once

#include <stdint.h>

#include "app_device_adapter.h"

struct AppDeviceInitializeOptions
{
    uint32_t serial_baud = 115200;
    bool setup_ap_enabled = true;
    bool start_network = true;
    bool print_littlefs_files = false;
    uint32_t config_fetch_timeout_ms = 15000;
    uint32_t ntp_sync_timeout_ms = 15000;
    uint32_t min_sleep_sec = 5;
    uint32_t network_retry_sleep_sec = 60;
};

struct AppDeviceWakeContext
{
    uint32_t seq_id = 0;
    bool woke_from_deep_sleep = false;
    bool network_connected = false;
    bool config_requested = false;
    bool config_received = false;
    bool time_synced = false;
    bool ota_update_attempted = false;
    uint32_t network_retry_sleep_sec = 60;
};

struct AppDeviceCycleResult
{
    uint32_t next_sleep_sec = 60;
    bool publish_debug_log = false;
};

class AppDevice : public AppDeviceAdapter
{
public:
    virtual ~AppDevice() = default;

    int initialize(const AppDeviceInitializeOptions &options = AppDeviceInitializeOptions());
    void loop();

protected:
    virtual const char *device_name() const = 0;
    virtual bool on_initialize() = 0;
    virtual void prepare_runtime_config_request() = 0;
    virtual void on_runtime_config_ready(bool config_received) = 0;
    virtual const char *runtime_ntp_server() const = 0;
    virtual int32_t runtime_timezone_offset_sec() const = 0;
    virtual AppDeviceCycleResult run_device_cycle(const AppDeviceWakeContext &context) = 0;
    virtual bool publish_device_status(const AppDeviceWakeContext &context,
                                       const AppDeviceCycleResult &cycle_result) = 0;

private:
    AppDeviceInitializeOptions m_options;
    bool m_network_started = false;

    void print_boot_settings() const;
    bool mount_littlefs() const;
    void print_littlefs_files() const;
    bool sync_time(const AppDeviceWakeContext &context) const;
    bool check_ota_update(uint32_t seq_id) const;
    void sleep(uint32_t sleep_sec) const;
};
