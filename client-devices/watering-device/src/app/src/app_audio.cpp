#include <WebSocketsServer.h>
#include "hal_audio.h"
#include "app_def.h"
#include "app_network.h"

// buffer for audio data
static uint16_t audioBuffer[I2S_DMA_BUF_LEN * I2S_DMA_BUF_COUNT];

// ================================================================
// Public functions
// ================================================================
void app_audio_init()
{
    hal_audio_init();
}

void app_audio_deinit()
{
    hal_audio_deinit();
}

bool app_audio_report(uint32_t seqId)
{
    const int read_count = 8; // 64ms/回 * 8回 = 512ms = 0.5s
    char buf[256];
    // Audioデータの情報を送信
    snprintf(buf, sizeof(buf), "{\"seqId\":%d,\"count\":%d}", seqId, read_count);
    if (app_network_send(APP_MSG_TYPE_AUDIO, (uint8_t *)buf, strlen(buf), seqId) == false)
    {
        Serial.println("Failed to send audio data");
        return false;
    }
    Serial.println("Audio Data:");
    Serial.println(buf);

    // Audioデータ読み取りと送信
    for (int i = 0; i < read_count; i++)
    {
        size_t bytesIn = 0;
        esp_err_t result = hal_audio_recv_data((uint8_t *)audioBuffer, sizeof(audioBuffer), &bytesIn);
        if (result != ESP_OK)
        {
            Serial.printf("hal_audio_recv_data error 0x%x\n", result);
            return false;
        }
        Serial.printf("\t-> Recorded Audio Data: %d\n", bytesIn);

        if (app_network_send(APP_MSG_TYPE_AUDIO, (uint8_t *)audioBuffer, bytesIn, seqId) == false)
        {
            Serial.println("Failed to send audio data");
            return false;
        }
    }

    return true;
}
