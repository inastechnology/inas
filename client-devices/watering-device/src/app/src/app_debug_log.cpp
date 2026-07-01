#include "app_debug_log.h"

#include <Arduino.h>
#include <string.h>

#include "app_def.h"
#include "app_network.h"

static constexpr uint8_t APP_DEBUG_LOG_FORMAT_VERSION = 1;
static constexpr uint8_t APP_DEBUG_LOG_RECORD_SIZE = 13;
static constexpr uint8_t APP_DEBUG_LOG_HEADER_SIZE = 16;

typedef struct
{
    uint8_t file_id;
    uint16_t line;
    uint8_t level;
    uint8_t event_code;
    int32_t arg0;
    int32_t arg1;
    uint16_t order;
} app_debug_log_event_record_t;

static app_debug_log_event_record_t s_events[APP_DEBUG_LOG_MAX_EVENTS];
static uint16_t s_event_count = 0;
static uint16_t s_event_dropped = 0;
static uint16_t s_next_order = 0;
static uint8_t s_publish_payload[APP_DEBUG_LOG_PAYLOAD_SIZE];

static void app_debug_log_write_u16(uint8_t *buffer, size_t offset, uint16_t value)
{
    buffer[offset] = static_cast<uint8_t>(value & 0xFF);
    buffer[offset + 1] = static_cast<uint8_t>((value >> 8) & 0xFF);
}

static void app_debug_log_write_i32(uint8_t *buffer, size_t offset, int32_t value)
{
    const uint32_t raw = static_cast<uint32_t>(value);
    buffer[offset] = static_cast<uint8_t>(raw & 0xFF);
    buffer[offset + 1] = static_cast<uint8_t>((raw >> 8) & 0xFF);
    buffer[offset + 2] = static_cast<uint8_t>((raw >> 16) & 0xFF);
    buffer[offset + 3] = static_cast<uint8_t>((raw >> 24) & 0xFF);
}

static void app_debug_log_write_u32(uint8_t *buffer, size_t offset, uint32_t value)
{
    buffer[offset] = static_cast<uint8_t>(value & 0xFF);
    buffer[offset + 1] = static_cast<uint8_t>((value >> 8) & 0xFF);
    buffer[offset + 2] = static_cast<uint8_t>((value >> 16) & 0xFF);
    buffer[offset + 3] = static_cast<uint8_t>((value >> 24) & 0xFF);
}

static uint8_t app_debug_log_priority(uint8_t level)
{
    if (level > APP_DEBUG_LOG_ERROR)
    {
        return APP_DEBUG_LOG_ERROR;
    }
    if (level < APP_DEBUG_LOG_INFO)
    {
        return APP_DEBUG_LOG_INFO;
    }
    return level;
}

static bool app_debug_log_replace_lower_priority(const app_debug_log_event_record_t &event)
{
    uint16_t replace_index = UINT16_MAX;
    uint8_t replace_level = APP_DEBUG_LOG_ERROR;
    uint16_t replace_order = 0;

    for (uint16_t i = 0; i < s_event_count; i++)
    {
        if (s_events[i].level >= event.level)
        {
            continue;
        }

        if (replace_index == UINT16_MAX ||
            s_events[i].level < replace_level ||
            (s_events[i].level == replace_level && s_events[i].order < replace_order))
        {
            replace_index = i;
            replace_level = s_events[i].level;
            replace_order = s_events[i].order;
        }
    }

    if (replace_index == UINT16_MAX)
    {
        return false;
    }

    s_events[replace_index] = event;
    s_event_dropped++;
    return true;
}

static bool app_debug_log_append_payload_record(size_t *payload_len, const app_debug_log_event_record_t &event)
{
    if (payload_len == nullptr || *payload_len + APP_DEBUG_LOG_RECORD_SIZE > sizeof(s_publish_payload))
    {
        return false;
    }

    const size_t offset = *payload_len;
    s_publish_payload[offset] = event.file_id;
    app_debug_log_write_u16(s_publish_payload, offset + 1, event.line);
    s_publish_payload[offset + 3] = event.level;
    s_publish_payload[offset + 4] = event.event_code;
    app_debug_log_write_i32(s_publish_payload, offset + 5, event.arg0);
    app_debug_log_write_i32(s_publish_payload, offset + 9, event.arg1);
    *payload_len += APP_DEBUG_LOG_RECORD_SIZE;
    return true;
}

void app_debug_log_reset()
{
    memset(s_events, 0, sizeof(s_events));
    s_event_count = 0;
    s_event_dropped = 0;
    s_next_order = 0;
}

void app_debug_log_event(uint8_t file_id,
                         uint16_t line,
                         app_debug_log_level_t level,
                         uint8_t event_code,
                         int32_t arg0,
                         int32_t arg1)
{
    app_debug_log_event_record_t event = {};
    event.file_id = file_id;
    event.line = line;
    event.level = app_debug_log_priority(level);
    event.event_code = event_code;
    event.arg0 = arg0;
    event.arg1 = arg1;
    event.order = s_next_order++;

    if (s_event_count < APP_DEBUG_LOG_MAX_EVENTS)
    {
        s_events[s_event_count++] = event;
        return;
    }

    if (!app_debug_log_replace_lower_priority(event))
    {
        s_event_dropped++;
    }
}

uint16_t app_debug_log_event_count()
{
    return s_event_count;
}

uint16_t app_debug_log_dropped_count()
{
    return s_event_dropped;
}

bool app_debug_log_publish(uint32_t seq_id)
{
    memset(s_publish_payload, 0, sizeof(s_publish_payload));
    s_publish_payload[0] = 'D';
    s_publish_payload[1] = 'L';
    s_publish_payload[2] = 'G';
    s_publish_payload[3] = APP_DEBUG_LOG_FORMAT_VERSION;
    app_debug_log_write_u32(s_publish_payload, 4, seq_id);
    app_debug_log_write_u16(s_publish_payload, 8, s_event_count);
    app_debug_log_write_u16(s_publish_payload, 10, 0);
    app_debug_log_write_u16(s_publish_payload, 12, s_event_dropped);
    s_publish_payload[14] = APP_DEBUG_LOG_RECORD_SIZE;
    s_publish_payload[15] = 0;

    size_t payload_len = APP_DEBUG_LOG_HEADER_SIZE;
    uint16_t sent_count = 0;

    for (int level = APP_DEBUG_LOG_ERROR; level >= APP_DEBUG_LOG_INFO; level--)
    {
        for (uint16_t i = 0; i < s_event_count; i++)
        {
            if (s_events[i].level != level)
            {
                continue;
            }
            if (!app_debug_log_append_payload_record(&payload_len, s_events[i]))
            {
                goto publish;
            }
            sent_count++;
        }
    }

publish:
    app_debug_log_write_u16(s_publish_payload, 10, sent_count);

    Serial.printf("Sending compact debug log: records=%u/%u dropped=%u bytes=%u\n",
                  static_cast<unsigned int>(sent_count),
                  static_cast<unsigned int>(s_event_count),
                  static_cast<unsigned int>(s_event_dropped),
                  static_cast<unsigned int>(payload_len));

    return app_network_send(APP_MSG_TYPE_DEBUG_LOG,
                            s_publish_payload,
                            static_cast<uint16_t>(payload_len),
                            seq_id);
}
