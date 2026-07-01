#pragma once

#include <time.h>

bool app_time_sync_with_ntp(const char *ntp_server, int32_t timezone_offset_sec, uint32_t timeout_ms = 15000);
bool app_time_is_synchronized();
