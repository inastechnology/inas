#pragma once

#include "esp_err.h"

typedef struct
{
    int width;
    int height;
    int format;
    int size;
    uint8_t *buf;
} app_camera_frame_t;

void hal_camera_init();
void hal_camera_deinit();
app_camera_frame_t *hal_camera_recv_frame();
esp_err_t hal_camera_fb_release();
