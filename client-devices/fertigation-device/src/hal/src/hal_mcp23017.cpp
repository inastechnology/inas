#include "hal_mcp23017.h"

#include <Arduino.h>
#include <Wire.h>

#ifndef APP_FGT_I2C_SDA_PIN
#define APP_FGT_I2C_SDA_PIN D0
#endif

#ifndef APP_FGT_I2C_SCL_PIN
#define APP_FGT_I2C_SCL_PIN D1
#endif

#ifndef APP_FGT_MCP23017_ADDRESS
#define APP_FGT_MCP23017_ADDRESS 0x20
#endif

static constexpr uint8_t kRegisterIodirA = 0x00;
static constexpr uint8_t kRegisterGppuA = 0x0C;
static constexpr uint8_t kRegisterGpioA = 0x12;
static constexpr uint8_t kRegisterOlatA = 0x14;

static bool write_u16(hal_mcp23017_t *device, uint8_t first_register, uint16_t value)
{
    if (device == nullptr || !device->initialized)
    {
        return false;
    }
    Wire.beginTransmission(device->config.address);
    Wire.write(first_register);
    Wire.write(static_cast<uint8_t>(value & 0xFF));
    Wire.write(static_cast<uint8_t>((value >> 8) & 0xFF));
    return Wire.endTransmission() == 0;
}

static bool read_u16(hal_mcp23017_t *device, uint8_t first_register, uint16_t *value_out)
{
    if (device == nullptr || !device->initialized || value_out == nullptr)
    {
        return false;
    }
    Wire.beginTransmission(device->config.address);
    Wire.write(first_register);
    if (Wire.endTransmission(false) != 0)
    {
        return false;
    }
    if (Wire.requestFrom(static_cast<int>(device->config.address), 2) != 2)
    {
        return false;
    }
    const uint8_t low = Wire.read();
    const uint8_t high = Wire.read();
    *value_out = static_cast<uint16_t>(low) | (static_cast<uint16_t>(high) << 8);
    return true;
}

hal_mcp23017_config_t hal_mcp23017_default_config()
{
    hal_mcp23017_config_t config = {};
    config.address = APP_FGT_MCP23017_ADDRESS;
    config.sda_pin = APP_FGT_I2C_SDA_PIN;
    config.scl_pin = APP_FGT_I2C_SCL_PIN;
    config.clock_hz = 100000;
    return config;
}

bool hal_mcp23017_open(hal_mcp23017_t *device, const hal_mcp23017_config_t *config)
{
    if (device == nullptr)
    {
        return false;
    }
    *device = {};
    device->config = config != nullptr ? *config : hal_mcp23017_default_config();
    if (device->config.address < 0x20 || device->config.address > 0x27 ||
        device->config.sda_pin < 0 || device->config.scl_pin < 0)
    {
        return false;
    }
    if (!Wire.begin(device->config.sda_pin, device->config.scl_pin, device->config.clock_hz))
    {
        return false;
    }
    device->initialized = true;
    device->direction_mask = 0xFFFF;
    device->pullup_mask = 0;
    device->output_latch = 0;

    // Write OFF before changing any pin to output. External pull-downs keep
    // actuator drivers off during reset and before this transaction completes.
    if (!write_u16(device, kRegisterOlatA, 0))
    {
        hal_mcp23017_close(device);
        return false;
    }
    return true;
}

void hal_mcp23017_close(hal_mcp23017_t *device)
{
    if (device == nullptr)
    {
        return;
    }
    if (device->initialized)
    {
        write_u16(device, kRegisterOlatA, 0);
        write_u16(device, kRegisterIodirA, 0xFFFF);
    }
    device->initialized = false;
    device->output_latch = 0;
}

bool hal_mcp23017_configure(hal_mcp23017_t *device, uint16_t output_mask, uint16_t input_pullup_mask)
{
    if (device == nullptr || !device->initialized || (output_mask & input_pullup_mask) != 0)
    {
        return false;
    }
    const uint16_t direction = static_cast<uint16_t>(~output_mask);
    if (!write_u16(device, kRegisterOlatA, 0) ||
        !write_u16(device, kRegisterGppuA, input_pullup_mask) ||
        !write_u16(device, kRegisterIodirA, direction))
    {
        return false;
    }
    device->direction_mask = direction;
    device->pullup_mask = input_pullup_mask;
    device->output_latch = 0;
    return true;
}

bool hal_mcp23017_write_outputs(hal_mcp23017_t *device, uint16_t output_mask, uint16_t enabled_mask)
{
    if (device == nullptr || !device->initialized || (enabled_mask & ~output_mask) != 0 ||
        (output_mask & device->direction_mask) != 0)
    {
        return false;
    }
    const uint16_t next = static_cast<uint16_t>((device->output_latch & ~output_mask) | enabled_mask);
    if (!write_u16(device, kRegisterOlatA, next))
    {
        return false;
    }
    device->output_latch = next;
    return true;
}

bool hal_mcp23017_read_gpio(hal_mcp23017_t *device, uint16_t *value_out)
{
    return read_u16(device, kRegisterGpioA, value_out);
}

bool hal_mcp23017_all_outputs_off(hal_mcp23017_t *device)
{
    if (device == nullptr || !device->initialized)
    {
        return false;
    }
    if (!write_u16(device, kRegisterOlatA, 0))
    {
        return false;
    }
    device->output_latch = 0;
    return true;
}
