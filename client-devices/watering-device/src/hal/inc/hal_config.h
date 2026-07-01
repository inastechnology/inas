#ifndef __HAL_CONFIG_H__
#define __HAL_CONFIG_H__

#include <stdint.h>
#include <stddef.h>
/// @brief Save the configuration to rom
/// @return void

void HAL_config_save(const uint8_t *data, size_t size);

/// @brief Load the configuration from rom
/// @return bool - true if the configuration is valid
bool HAL_config_load(uint8_t *data, size_t size);

/// @brief Check whether saved config exists
/// @return bool - true when saved config exists
bool HAL_config_exists();

#endif // __HAL_CONFIG_H__
