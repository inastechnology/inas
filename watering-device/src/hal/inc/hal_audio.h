#pragma once

#include "esp_err.h"

#define I2S_DMA_BUF_COUNT 16 // DMA buffer count
#define I2S_DMA_BUF_LEN 1024 // DMA buffer length per one buffer

void hal_audio_init();
void hal_audio_deinit();
esp_err_t hal_audio_recv_data(void *dest, size_t size, size_t *bytes_read);