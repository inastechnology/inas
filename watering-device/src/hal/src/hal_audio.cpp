#include "driver/i2s.h"
#include "esp_err.h"
#include "esp_log.h"
#include "hal_audio.h"

#define I2S_PORT I2S_NUM_0
#define I2S_READ_TIMEOUT (3000 / portTICK_PERIOD_MS) // timeout 1s
#define I2S_SAMPLE_RATE (16000)                      // sample rate 16kHz
#define I2S_SAMPLE_BITS (I2S_BITS_PER_SAMPLE_16BIT)  // 16bit
#define I2S_CHANNEL_FORMAT I2S_CHANNEL_FMT_ONLY_LEFT // mono
#define I2S_COMM_FORMAT I2S_COMM_FORMAT_I2S          // default

static const char *TAG = "hal_audio";

void hal_audio_init()
{
    esp_log_level_set(TAG, ESP_LOG_DEBUG);
    // set I2S configuration
    i2s_config_t i2s_config = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX), // マスター受信モード
        .sample_rate = I2S_SAMPLE_RATE,
        .bits_per_sample = I2S_SAMPLE_BITS,
        .channel_format = I2S_CHANNEL_FORMAT,
        .communication_format = I2S_COMM_FORMAT,
        .intr_alloc_flags = 0, // デフォルトの割り込み設定
        .dma_buf_count = I2S_DMA_BUF_COUNT,
        .dma_buf_len = I2S_DMA_BUF_LEN,
        .use_apll = false,
        .tx_desc_auto_clear = false,
        .fixed_mclk = 0};

    // set I2S pin configuration
    i2s_pin_config_t pin_config = {
        .bck_io_num = I2S_PIN_NO_CHANGE,
        .ws_io_num = 42,
        .data_out_num = I2S_PIN_NO_CHANGE,
        .data_in_num = 41,
    };

    esp_err_t ret;
    // install I2S driver
    ret = i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
    if (ret != ESP_OK)
    {
        ESP_LOGE(TAG, "I2Sドライバのインストールに失敗しました: %s", esp_err_to_name(ret));
        return;
    }

    // set I2S pin
    ret = i2s_set_pin(I2S_PORT, &pin_config);
    if (ret != ESP_OK)
    {
        ESP_LOGE(TAG, "I2Sピン設定に失敗しました: %s", esp_err_to_name(ret));
        i2s_driver_uninstall(I2S_PORT);
        return;
    }

    ESP_LOGI(TAG, "I2S初期化に成功しました");
}

void hal_audio_deinit()
{
    // uninstall I2S driver
    esp_err_t ret = i2s_driver_uninstall(I2S_PORT);
    if (ret != ESP_OK)
    {
        ESP_LOGE(TAG, "I2Sドライバのアンインストールに失敗しました: %s", esp_err_to_name(ret));
    }
    else
    {
        ESP_LOGI(TAG, "I2S終了処理に成功しました");
    }
}

esp_err_t hal_audio_recv_data(void *dest, size_t size, size_t *bytes_read)
{
    // read audio data from I2S
    esp_err_t ret = i2s_read(I2S_PORT, dest, size, bytes_read, I2S_READ_TIMEOUT);
    if (ret != ESP_OK)
    {
        ESP_LOGE("hal_audio", "I2S read error: %s", esp_err_to_name(ret));
    }
    // gain control
    // volume up
    for (int i = 0; i < size / 2; i++)
    {
        int16_t *data = (int16_t *)dest;
        data[i] = data[i] * 2;
    }
    int16_t *data = (int16_t *)dest;
    int samples = (*bytes_read) / 2;
    for (int i = 0; i < samples; i++)
    {
        int32_t amplified = (int32_t)data[i] * 2;
        if (amplified > INT16_MAX)
            amplified = INT16_MAX;
        else if (amplified < INT16_MIN)
            amplified = INT16_MIN;
        data[i] = (int16_t)amplified;
    }

    return ret;
}