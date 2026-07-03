#include "app_ota.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <Update.h>
#include <WiFi.h>
#include <ctype.h>
#include <mbedtls/sha256.h>
#include <string.h>
#include "esp_ota_ops.h"

#include "app_config.h"
#include "app_debug_log.h"
#include "app_def.h"
#include "app_network.h"

#define APP_OTA_PENDING_FILE "/.ota_pending"

typedef struct
{
    bool received;
    bool valid;
    bool has_update;
    char error[32];
    char update_id[64];
    char device_kind[4];
    char version[32];
    char build_id[64];
    char url[384];
    char sha256[65];
    uint32_t size;
    bool force;
    bool allow_downgrade;
} app_ota_offer_t;

typedef struct
{
    bool exists;
    char update_id[64];
    char version[32];
} app_ota_pending_boot_t;

static app_ota_offer_t s_offer;
static app_ota_pending_boot_t s_pending_boot;
static bool s_accepting_offer = false;

static void app_ota_clear_offer()
{
    memset(&s_offer, 0, sizeof(s_offer));
}

static void app_ota_set_offer_error(const char *error)
{
    s_offer.received = true;
    s_offer.valid = false;
    s_offer.has_update = false;
    strncpy(s_offer.error, error, sizeof(s_offer.error) - 1);
}

static bool app_ota_copy_string(char *dest, size_t dest_size, const char *value)
{
    if (dest == nullptr || dest_size == 0 || value == nullptr || value[0] == '\0')
    {
        return false;
    }

    const size_t length = strlen(value);
    if (length >= dest_size)
    {
        return false;
    }

    memcpy(dest, value, length + 1);
    return true;
}

static bool app_ota_is_safe_token(const char *value)
{
    if (value == nullptr || value[0] == '\0')
    {
        return false;
    }

    for (const char *cursor = value; *cursor != '\0'; cursor++)
    {
        const char c = *cursor;
        if (isalnum(static_cast<unsigned char>(c)) || c == '.' || c == '-' || c == '_' || c == ':' || c == '+')
        {
            continue;
        }
        return false;
    }

    return true;
}

static bool app_ota_is_sha256_hex(const char *value)
{
    if (value == nullptr || strlen(value) != 64)
    {
        return false;
    }

    for (size_t i = 0; i < 64; i++)
    {
        if (!isxdigit(static_cast<unsigned char>(value[i])))
        {
            return false;
        }
    }

    return true;
}

static bool app_ota_is_device_kind(const char *value)
{
    if (value == nullptr || strlen(value) != 3)
    {
        return false;
    }

    for (size_t i = 0; i < 3; i++)
    {
        if (!isupper(static_cast<unsigned char>(value[i])))
        {
            return false;
        }
    }
    return true;
}

static void app_ota_digest_to_hex(const uint8_t *digest, char *hex_out, size_t hex_size)
{
    if (hex_out == nullptr || hex_size < 65)
    {
        return;
    }

    static const char kHex[] = "0123456789abcdef";
    for (size_t i = 0; i < 32; i++)
    {
        hex_out[i * 2] = kHex[(digest[i] >> 4) & 0x0F];
        hex_out[(i * 2) + 1] = kHex[digest[i] & 0x0F];
    }
    hex_out[64] = '\0';
}

static bool app_ota_save_pending_boot()
{
    File file = LittleFS.open(APP_OTA_PENDING_FILE, "w");
    if (!file)
    {
        Serial.println("Failed to open OTA pending file for write");
        return false;
    }

    file.printf("{\"update_id\":\"%s\",\"version\":\"%s\"}", s_offer.update_id, s_offer.version);
    file.close();
    return true;
}

static void app_ota_load_pending_boot()
{
    memset(&s_pending_boot, 0, sizeof(s_pending_boot));
    if (!LittleFS.exists(APP_OTA_PENDING_FILE))
    {
        return;
    }

    File file = LittleFS.open(APP_OTA_PENDING_FILE, "r");
    if (!file)
    {
        Serial.println("Failed to open OTA pending file");
        return;
    }

    JsonDocument doc;
    const DeserializationError error = deserializeJson(doc, file);
    file.close();
    if (error)
    {
        Serial.printf("Failed to parse OTA pending file: %s\n", error.c_str());
        return;
    }

    const char *update_id = doc["update_id"] | "";
    const char *version = doc["version"] | "";
    if (!app_ota_is_safe_token(update_id) || !app_ota_is_safe_token(version))
    {
        Serial.println("OTA pending file content is invalid");
        return;
    }

    if (!app_ota_copy_string(s_pending_boot.update_id, sizeof(s_pending_boot.update_id), update_id) ||
        !app_ota_copy_string(s_pending_boot.version, sizeof(s_pending_boot.version), version))
    {
        Serial.println("OTA pending file fields are too large");
        return;
    }
    s_pending_boot.exists = true;
}

static bool app_ota_publish_status(uint32_t seq_id, const char *state, const char *update_id, const char *to_version, uint8_t progress, const char *error)
{
    char payload[512];
    const char *safe_update_id = update_id != nullptr && update_id[0] != '\0' ? update_id : "none";
    const char *safe_to_version = to_version != nullptr && to_version[0] != '\0' ? to_version : APP_FIRMWARE_VERSION;
    int write_len = 0;

    if (error != nullptr && error[0] != '\0')
    {
        write_len = snprintf(payload,
                             sizeof(payload),
                             "{\"seq\":%lu,\"schema_version\":1,\"device_kind\":\"%s\",\"update_id\":\"%s\",\"state\":\"%s\",\"from_version\":\"%s\",\"to_version\":\"%s\",\"firmware_version\":\"%s\",\"firmware_build_id\":\"%s\",\"progress\":%u,\"error\":\"%s\"}",
                             static_cast<unsigned long>(seq_id),
                             APP_DEVICE_KIND,
                             safe_update_id,
                             state,
                             APP_FIRMWARE_VERSION,
                             safe_to_version,
                             APP_FIRMWARE_VERSION,
                             APP_FIRMWARE_BUILD_ID,
                             static_cast<unsigned int>(progress),
                             error);
    }
    else
    {
        write_len = snprintf(payload,
                             sizeof(payload),
                             "{\"seq\":%lu,\"schema_version\":1,\"device_kind\":\"%s\",\"update_id\":\"%s\",\"state\":\"%s\",\"from_version\":\"%s\",\"to_version\":\"%s\",\"firmware_version\":\"%s\",\"firmware_build_id\":\"%s\",\"progress\":%u}",
                             static_cast<unsigned long>(seq_id),
                             APP_DEVICE_KIND,
                             safe_update_id,
                             state,
                             APP_FIRMWARE_VERSION,
                             safe_to_version,
                             APP_FIRMWARE_VERSION,
                             APP_FIRMWARE_BUILD_ID,
                             static_cast<unsigned int>(progress));
    }

    if (write_len < 0 || static_cast<size_t>(write_len) >= sizeof(payload))
    {
        Serial.println("OTA status payload too large");
        return false;
    }

    Serial.printf("Sending OTA status: %s\n", payload);
    return app_network_send(APP_MSG_TYPE_OTA_STATUS, reinterpret_cast<const uint8_t *>(payload), strlen(payload), seq_id);
}

static bool app_ota_fail(uint32_t seq_id, const char *error)
{
    Update.abort();
    app_ota_publish_status(seq_id, "failed", s_offer.update_id, s_offer.version, 0, error);
    app_network_flush(APP_MQTT_STATUS_PUBLISH_DRAIN_MS);
    return false;
}

static bool app_ota_download_and_install(uint32_t seq_id)
{
    if (strncmp(s_offer.url, "http://", strlen("http://")) != 0)
    {
        return app_ota_fail(seq_id, "url_rejected");
    }

    const esp_partition_t *next_partition = esp_ota_get_next_update_partition(nullptr);
    if (next_partition == nullptr)
    {
        return app_ota_fail(seq_id, "size_too_large");
    }
    if (s_offer.size > next_partition->size)
    {
        return app_ota_fail(seq_id, "size_too_large");
    }

    WiFiClient wifi_client;
    HTTPClient http;
    http.setConnectTimeout(APP_OTA_HTTP_CONNECT_TIMEOUT_MS);
    http.setTimeout(APP_OTA_HTTP_READ_TIMEOUT_MS);
    if (!http.begin(wifi_client, s_offer.url))
    {
        http.end();
        return app_ota_fail(seq_id, "http_connect_failed");
    }

    const int http_status = http.GET();
    if (http_status != HTTP_CODE_OK)
    {
        Serial.printf("OTA HTTP status invalid: %d\n", http_status);
        http.end();
        return app_ota_fail(seq_id, http_status <= 0 ? "http_connect_failed" : "http_status_invalid");
    }

    const int content_length = http.getSize();
    if (content_length > 0 && static_cast<uint32_t>(content_length) != s_offer.size)
    {
        Serial.printf("OTA content length mismatch: %d/%lu\n", content_length, static_cast<unsigned long>(s_offer.size));
        http.end();
        return app_ota_fail(seq_id, "content_length_mismatch");
    }

    if (!Update.begin(s_offer.size, U_FLASH))
    {
        Serial.printf("Update.begin failed: %s\n", Update.errorString());
        http.end();
        return app_ota_fail(seq_id, "size_too_large");
    }

    mbedtls_sha256_context sha_context;
    mbedtls_sha256_init(&sha_context);
    if (mbedtls_sha256_starts_ret(&sha_context, 0) != 0)
    {
        mbedtls_sha256_free(&sha_context);
        http.end();
        return app_ota_fail(seq_id, "flash_write_failed");
    }

    uint8_t buffer[1024];
    uint32_t written = 0;
    uint8_t last_reported_progress = 0;
    const uint32_t start_ms = millis();
    WiFiClient *stream = http.getStreamPtr();
    app_ota_publish_status(seq_id, "downloading", s_offer.update_id, s_offer.version, 5, nullptr);

    while (written < s_offer.size)
    {
        app_network_loop();
        if ((millis() - start_ms) > APP_OTA_TOTAL_TIMEOUT_MS)
        {
            mbedtls_sha256_free(&sha_context);
            http.end();
            return app_ota_fail(seq_id, "download_timeout");
        }

        const int available = stream->available();
        if (available <= 0)
        {
            if (!http.connected())
            {
                break;
            }
            delay(20);
            continue;
        }

        size_t to_read = static_cast<size_t>(available);
        if (to_read > sizeof(buffer))
        {
            to_read = sizeof(buffer);
        }
        if (to_read > (s_offer.size - written))
        {
            to_read = s_offer.size - written;
        }

        const size_t read_len = stream->readBytes(buffer, to_read);
        if (read_len == 0)
        {
            delay(20);
            continue;
        }

        if (mbedtls_sha256_update_ret(&sha_context, buffer, read_len) != 0)
        {
            mbedtls_sha256_free(&sha_context);
            http.end();
            return app_ota_fail(seq_id, "flash_write_failed");
        }

        const size_t write_len = Update.write(buffer, read_len);
        if (write_len != read_len)
        {
            Serial.printf("Update.write failed: %u/%u error=%s\n", static_cast<unsigned int>(write_len), static_cast<unsigned int>(read_len), Update.errorString());
            mbedtls_sha256_free(&sha_context);
            http.end();
            return app_ota_fail(seq_id, "flash_write_failed");
        }

        written += read_len;
        const uint8_t progress = static_cast<uint8_t>(5 + ((written * 70ULL) / s_offer.size));
        if (progress >= last_reported_progress + 25 || written == s_offer.size)
        {
            last_reported_progress = progress;
            app_ota_publish_status(seq_id, "downloading", s_offer.update_id, s_offer.version, progress, nullptr);
        }
    }

    if (written != s_offer.size)
    {
        Serial.printf("OTA length mismatch after download: %lu/%lu\n", static_cast<unsigned long>(written), static_cast<unsigned long>(s_offer.size));
        mbedtls_sha256_free(&sha_context);
        http.end();
        return app_ota_fail(seq_id, "content_length_mismatch");
    }

    uint8_t digest[32];
    if (mbedtls_sha256_finish_ret(&sha_context, digest) != 0)
    {
        mbedtls_sha256_free(&sha_context);
        http.end();
        return app_ota_fail(seq_id, "sha256_mismatch");
    }
    mbedtls_sha256_free(&sha_context);

    char actual_sha256[65];
    app_ota_digest_to_hex(digest, actual_sha256, sizeof(actual_sha256));
    if (strcasecmp(actual_sha256, s_offer.sha256) != 0)
    {
        Serial.printf("OTA SHA-256 mismatch actual=%s expected=%s\n", actual_sha256, s_offer.sha256);
        http.end();
        return app_ota_fail(seq_id, "sha256_mismatch");
    }

    app_ota_publish_status(seq_id, "written", s_offer.update_id, s_offer.version, 90, nullptr);
    if (!Update.end(true))
    {
        Serial.printf("Update.end failed: %s\n", Update.errorString());
        http.end();
        return app_ota_fail(seq_id, "set_boot_partition_failed");
    }
    if (!Update.isFinished())
    {
        http.end();
        return app_ota_fail(seq_id, "flash_write_failed");
    }

    http.end();
    if (!app_ota_save_pending_boot())
    {
        Serial.println("OTA pending boot status could not be saved; continuing reboot");
    }
    app_ota_publish_status(seq_id, "rebooting", s_offer.update_id, s_offer.version, 100, nullptr);
    app_network_flush(APP_MQTT_STATUS_PUBLISH_DRAIN_MS);
    delay(250);
    ESP.restart();
    return true;
}

void app_ota_init()
{
    app_ota_clear_offer();
    s_accepting_offer = false;
    app_ota_load_pending_boot();
}

void app_ota_mark_waiting()
{
    s_accepting_offer = true;
}

void app_ota_finish_waiting()
{
    s_accepting_offer = false;
}

bool app_ota_apply_offer_json(const uint8_t *payload, size_t length)
{
    app_ota_clear_offer();
    if (payload == nullptr || length == 0)
    {
        Serial.println("Empty OTA offer received; cached offer cleared");
        return false;
    }

    JsonDocument doc;
    const DeserializationError error = deserializeJson(doc, payload, length);
    if (error)
    {
        Serial.printf("Failed to parse OTA offer JSON: %s\n", error.c_str());
        app_ota_set_offer_error("invalid_payload");
        return false;
    }

    s_offer.received = true;
    s_accepting_offer = false;
    const int schema_version = doc["schema_version"] | 0;
    if (schema_version != 1)
    {
        app_ota_set_offer_error("unsupported_schema");
        return true;
    }

    const char *action = doc["action"] | "";
    if (strcmp(action, "none") == 0)
    {
        s_offer.valid = true;
        s_offer.has_update = false;
        return true;
    }
    if (strcmp(action, "update") != 0)
    {
        app_ota_set_offer_error("invalid_payload");
        return true;
    }

    const char *update_id = doc["update_id"] | "";
    const char *device_kind = doc["device_kind"] | "";
    const char *version = doc["version"] | "";
    const char *build_id = doc["build_id"] | "";
    const char *url = doc["url"] | "";
    const char *sha256 = doc["sha256"] | "";
    const uint32_t size = doc["size"] | 0;

    if (!app_ota_is_device_kind(device_kind) || strcmp(device_kind, APP_DEVICE_KIND) != 0)
    {
        app_ota_set_offer_error("device_kind_mismatch");
        return true;
    }

    if (!app_ota_is_safe_token(update_id) ||
        !app_ota_is_safe_token(version) ||
        size == 0 ||
        !app_ota_is_sha256_hex(sha256) ||
        !app_ota_copy_string(s_offer.update_id, sizeof(s_offer.update_id), update_id) ||
        !app_ota_copy_string(s_offer.device_kind, sizeof(s_offer.device_kind), device_kind) ||
        !app_ota_copy_string(s_offer.version, sizeof(s_offer.version), version) ||
        !app_ota_copy_string(s_offer.url, sizeof(s_offer.url), url) ||
        !app_ota_copy_string(s_offer.sha256, sizeof(s_offer.sha256), sha256))
    {
        app_ota_set_offer_error("invalid_payload");
        return true;
    }

    if (build_id[0] != '\0')
    {
        if (!app_ota_is_safe_token(build_id) || !app_ota_copy_string(s_offer.build_id, sizeof(s_offer.build_id), build_id))
        {
            app_ota_set_offer_error("invalid_payload");
            return true;
        }
    }

    s_offer.size = size;
    s_offer.force = doc["force"] | false;
    s_offer.allow_downgrade = doc["allow_downgrade"] | false;
    s_offer.valid = true;
    s_offer.has_update = true;
    return true;
}

bool app_ota_is_offer_received()
{
    return s_offer.received;
}

bool app_ota_should_update()
{
    return s_offer.received && s_offer.valid && s_offer.has_update;
}

bool app_ota_publish_pending_boot_status(uint32_t seq_id)
{
    if (!s_pending_boot.exists)
    {
        return false;
    }

    const bool booted = app_ota_publish_status(seq_id, "booted", s_pending_boot.update_id, s_pending_boot.version, 100, nullptr);
    if (!booted)
    {
        return false;
    }
    app_network_flush(APP_MQTT_STATUS_PUBLISH_DRAIN_MS);

    const bool confirmed = app_ota_publish_status(seq_id, "confirmed", s_pending_boot.update_id, s_pending_boot.version, 100, nullptr);
    if (!confirmed)
    {
        return false;
    }
    app_network_flush(APP_MQTT_STATUS_PUBLISH_DRAIN_MS);
    LittleFS.remove(APP_OTA_PENDING_FILE);
    memset(&s_pending_boot, 0, sizeof(s_pending_boot));
    return true;
}

bool app_ota_handle_offer(uint32_t seq_id)
{
    if (!s_offer.received)
    {
        return false;
    }

    if (!s_offer.valid)
    {
        app_ota_publish_status(seq_id, "failed", s_offer.update_id, s_offer.version, 0, s_offer.error[0] != '\0' ? s_offer.error : "invalid_payload");
        app_network_flush(APP_MQTT_STATUS_PUBLISH_DRAIN_MS);
        return false;
    }

    if (!s_offer.has_update)
    {
        return false;
    }

    app_ota_publish_status(seq_id, "offered", s_offer.update_id, s_offer.version, 0, nullptr);
    if (strcmp(s_offer.version, APP_FIRMWARE_VERSION) == 0)
    {
        app_ota_publish_status(seq_id, "skipped", s_offer.update_id, s_offer.version, 0, "already_running");
        app_network_flush(APP_MQTT_STATUS_PUBLISH_DRAIN_MS);
        return false;
    }

    app_ota_publish_status(seq_id, "started", s_offer.update_id, s_offer.version, 0, nullptr);
    app_network_flush(APP_MQTT_STATUS_PUBLISH_DRAIN_MS);
    app_ota_download_and_install(seq_id);
    return true;
}
