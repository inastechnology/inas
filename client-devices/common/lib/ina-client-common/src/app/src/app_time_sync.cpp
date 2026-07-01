#include "app_time_sync.h"

#include <Arduino.h>
#include <esp_sntp.h>

bool app_time_sync_with_ntp(const char *ntp_server, int32_t timezone_offset_sec, uint32_t timeout_ms)
{
    if (ntp_server == nullptr || ntp_server[0] == '\0')
    {
        return false;
    }

    configTime(timezone_offset_sec, 0, ntp_server);

    const uint32_t started_ms = millis();
    time_t now = 0;
    while ((millis() - started_ms) < timeout_ms)
    {
        time(&now);
        if (now > 1700000000)
        {
            Serial.printf("Time synchronized with %s: %ld\n", ntp_server, static_cast<long>(now));
            return true;
        }
        delay(250);
    }

    Serial.printf("NTP sync timeout: %s\n", ntp_server);
    return false;
}

bool app_time_is_synchronized()
{
    time_t now = 0;
    time(&now);
    return now > 1700000000;
}
