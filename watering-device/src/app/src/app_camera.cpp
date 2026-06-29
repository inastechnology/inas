#include <WebSocketsServer.h>

#include "hal_camera.h"
#include "app_def.h"
#include "app_network.h"

// ================================================================
// Public functions
// ================================================================
void app_camera_init()
{
    hal_camera_init();
}

void app_camera_deinit()
{
    hal_camera_deinit();
}

bool app_camera_report(uint32_t seqId)
{
    app_camera_frame_t *pFrame = hal_camera_recv_frame();
    if (pFrame == NULL)
    {
        Serial.println("Camera Frame is NULL");
        return false;
    }

    // カメラデータのサイズを送信
    char buf[256];
    snprintf(buf, sizeof(buf), "{\"seqId\":%d,\"width\":%d,\"height\":%d,\"format\":%d,\"size\":%d}", seqId, pFrame->width, pFrame->height, pFrame->format, pFrame->size);
    Serial.println("Camera Data:");
    Serial.println(buf);
    if (app_network_send(APP_MSG_TYPE_IMAGE, (const uint8_t *)buf, strlen(buf), seqId) == false)
    {
        Serial.println("Failed to send camera data");
        hal_camera_fb_release();
        return false;
    }
    // カメラデータを送信
    const int chunkSize = 0xFFFF - 128;
    int totalSend = 0;
    for (int i = 0; i < pFrame->size; i += chunkSize)
    {
        int len = chunkSize;
        if (i + len > pFrame->size)
        {
            len = pFrame->size - i;
        }
        if (app_network_send(APP_MSG_TYPE_IMAGE, pFrame->buf + i, len, seqId) == false)
        {
            Serial.println("Failed to send camera data");
            hal_camera_fb_release();
            return false;
        }
        totalSend += len;
        Serial.printf("Send %d/%d\n", totalSend, pFrame->size);
    }
    // last chunk
    if (pFrame->size % chunkSize != 0)
    {
        if (app_network_send(APP_MSG_TYPE_IMAGE, pFrame->buf + pFrame->size - (pFrame->size % chunkSize), pFrame->size % chunkSize) == false)
        {
            Serial.println("Failed to send camera data");
            hal_camera_fb_release();
            return false;
        }
    }
    Serial.println("Send Camera Data Done");
    hal_camera_fb_release();

    return true;
}

// ================================================================
// static functions
// ================================================================
