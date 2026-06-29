#include <Arduino.h>
#include <esp_camera.h>
#include "hal_camera.h"

static app_camera_frame_t app_camera_frame;
static camera_fb_t *fb = NULL; // Cameraデータ

void hal_camera_init()
{
    camera_config_t config = {
        .pin_pwdn = -1,
        .pin_reset = -1,
        .pin_xclk = 10,
        .pin_sscb_sda = 40,
        .pin_sscb_scl = 39,
        .pin_d7 = 48,
        .pin_d6 = 11,
        .pin_d5 = 12,
        .pin_d4 = 14,
        .pin_d3 = 16,
        .pin_d2 = 18,
        .pin_d1 = 17,
        .pin_d0 = 15,
        .pin_vsync = 38,
        .pin_href = 47,
        .pin_pclk = 13,
        .xclk_freq_hz = 20000000,
        .ledc_timer = LEDC_TIMER_1,
        .ledc_channel = LEDC_CHANNEL_0,
        .pixel_format = PIXFORMAT_JPEG,
        .frame_size = FRAMESIZE_UXGA,
        .jpeg_quality = 12,
        .fb_count = 1,
        .fb_location = CAMERA_FB_IN_PSRAM,
        .grab_mode = CAMERA_GRAB_LATEST,
    };
    esp_err_t result = esp_camera_init(&config);
    if (result != ESP_OK)
    {
        Serial.printf("esp_camera_init error 0x%x\n", result);
    }

    sensor_t *pSensor = esp_camera_sensor_get();
    pSensor->set_vflip(pSensor, 0);
    pSensor->set_hmirror(pSensor, 0);
    pSensor->set_denoise(pSensor, 1);
}

void hal_camera_deinit()
{
    esp_camera_deinit();
}

app_camera_frame_t *hal_camera_recv_frame()
{
    if (fb != NULL)
    {
        // カメラのフレームバッファ解放
        esp_camera_fb_return(fb);
        fb = NULL;
    }
    fb = esp_camera_fb_get();
    if (fb == NULL)
    {
        return NULL;
    }
    // set frame data
    app_camera_frame.width = fb->width;
    app_camera_frame.height = fb->height;
    app_camera_frame.format = fb->format;
    app_camera_frame.size = fb->len;
    app_camera_frame.buf = fb->buf;

    return &app_camera_frame;
}

esp_err_t hal_camera_fb_release()
{
    if (fb != NULL)
    {
        esp_camera_fb_return(fb); // カメラのフレームバッファ解放
        fb = NULL;
    }
    return ESP_OK;
}
