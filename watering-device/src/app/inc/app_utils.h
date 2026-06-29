#ifndef __APP_UTILS_H__
#define __APP_UTILS_H__

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string>
#include "esp_random.h"

// リトライ回数
#define RETRY_COUNT 3
#define CALL_WITH_RETRY(func, retry)                \
    retry = 0;                                      \
    while (false == func)                           \
    {                                               \
        if (retry > RETRY_COUNT)                    \
        {                                           \
            ESP_LOGE(TAG, "Failed to send data\n"); \
            break;                                  \
        }                                           \
        retry++;                                    \
        delay(retry *retry * 1000);                 \
    }

class AppUtils
{
public:
    // UUID v4 生成関数
    static std::string generate_uuid_v4()
    {
        const char *hex_chars = "0123456789abcdef";
        char uuid[37]; // 36文字 + null終端

        for (int i = 0; i < 36; i++)
        {
            if (i == 8 || i == 13 || i == 18 || i == 23)
            {
                uuid[i] = '-'; // UUIDのフォーマット
            }
            else
            {
                uint8_t rand_byte = esp_random() & 0xFF; // 0-255の乱数
                uuid[i] = hex_chars[rand_byte % 16];
            }
        }

        // UUIDv4 のバージョン（13桁目 = 4）
        uuid[14] = '4';

        // UUIDv4 のバリアント（17桁目 = 8,9,a,b のいずれか）
        const char variant_chars[] = "89ab";
        uuid[19] = variant_chars[esp_random() % 4];

        uuid[36] = '\0'; // 文字列終端

        return std::string(uuid);
    }

    // CRC32 計算関数
    static uint32_t crc32(const uint8_t *data, size_t length)
    {
        uint32_t crc = 0xFFFFFFFF;
        for (size_t i = 0; i < length; i++)
        {
            crc = crc ^ data[i];
            for (size_t j = 0; j < 8; j++)
            {
                crc = (crc >> 1) ^ (0xEDB88320 & -(crc & 1));
            }
        }
        return ~crc;
    }
};

#endif // __APP_UTILS_H__