#include "esp_err.h"
#include "esp_log.h"
#include <WiFi.h>
#include <PubSubClient.h>
#include <ESPmDNS.h>
#include <string.h>

#include "app_network.h"
#include "app_config.h"
#include "app_debug_log.h"
#include "app_device_adapter.h"
#include "app_initial_setting.h"
#include "app_task.h"
#include "app_ota.h"

#define TAG __FILE__
#define APP_MQTT_CONFIG_KIND "config"
#define APP_MQTT_CONFIG_REQUEST_MODE "request"
#define APP_MQTT_CONFIG_PUSH_MODE "push"
#define APP_MQTT_CONFIG_REPLY_MODE "reply"

// ==========================================
// Private Functions
// ==========================================
// MQTT topic format: /<client_id>/kinds/<kind>/<mode>
#define MQTT_PUB_TOPIC_FMT "/%s/kinds/%s/%s"
#define MQTT_OTA_KIND_OFFER_TOPIC_FMT "/kinds/%s/devices/%s/ota/offer"

static const char *kAppMsgKind[MAX_APP_MSG_TYPE] = {
    APP_MQTT_PUB_KIND,
    APP_MQTT_PUB_KIND,
    APP_MQTT_PUB_KIND,
    APP_MQTT_PUB_KIND,
    APP_MQTT_PUB_KIND,
    APP_MQTT_DEBUG_LOG_KIND,
    APP_MQTT_OTA_KIND};

static const char *kAppMsgMode[MAX_APP_MSG_TYPE] = {
    APP_MQTT_PUB_MODE,
    APP_MQTT_PUB_MODE,
    APP_MQTT_PUB_MODE,
    APP_MQTT_PUB_MODE,
    APP_MQTT_PUB_MODE,
    APP_MQTT_DEBUG_LOG_MODE,
    APP_MQTT_OTA_STATUS_MODE};

WiFiClient espClient;
PubSubClient client(espClient);
static bool s_setup_portal_enabled = true;

void app_network_sub_callback(char *topic, byte *payload, unsigned int length);
static bool app_network_subscribe_topics();
static bool app_network_subscribe_topic(const char *kind, const char *mode);
static bool app_network_subscribe_ota_kind_offer_topic();
static bool app_network_is_ota_kind_offer_topic(const char *topic);

// ================================================================
// Private functions
// ================================================================
static int32_t app_network_context_id(const char *context)
{
    if (context != nullptr && strcmp(context, "reconnect") == 0)
    {
        return 2;
    }
    return 1;
}

static const char *app_network_wifi_status_name(wl_status_t status)
{
    switch (status)
    {
    case WL_IDLE_STATUS:
        return "WL_IDLE_STATUS";
    case WL_NO_SSID_AVAIL:
        return "WL_NO_SSID_AVAIL";
    case WL_SCAN_COMPLETED:
        return "WL_SCAN_COMPLETED";
    case WL_CONNECTED:
        return "WL_CONNECTED";
    case WL_CONNECT_FAILED:
        return "WL_CONNECT_FAILED";
    case WL_CONNECTION_LOST:
        return "WL_CONNECTION_LOST";
    case WL_DISCONNECTED:
        return "WL_DISCONNECTED";
    default:
        return "UNKNOWN";
    }
}

static bool app_network_parse_kinds_topic(const char *topic, char *clientId, size_t clientIdSize, char *kind, size_t kindSize, char *mode, size_t modeSize)
{
    if (topic == nullptr || clientId == nullptr || kind == nullptr || mode == nullptr)
    {
        return false;
    }

    // /<client_id>/kinds/<kind>/<mode>
    if (topic[0] != '/')
    {
        return false;
    }

    const char *clientStart = topic + 1;
    const char *kindsPrefix = strstr(clientStart, "/kinds/");
    if (kindsPrefix == nullptr)
    {
        return false;
    }

    const size_t clientIdLen = kindsPrefix - clientStart;
    if (clientIdLen == 0 || clientIdLen >= clientIdSize)
    {
        return false;
    }
    memcpy(clientId, clientStart, clientIdLen);
    clientId[clientIdLen] = '\0';

    const char *kindStart = kindsPrefix + strlen("/kinds/");
    const char *kindEnd = strchr(kindStart, '/');
    if (kindEnd == nullptr)
    {
        return false;
    }

    const size_t kindLen = kindEnd - kindStart;
    if (kindLen == 0 || kindLen >= kindSize)
    {
        return false;
    }
    memcpy(kind, kindStart, kindLen);
    kind[kindLen] = '\0';

    const char *modeStart = kindEnd + 1;
    if (*modeStart == '\0')
    {
        return false;
    }

    const char *extraSlash = strchr(modeStart, '/');
    if (extraSlash != nullptr)
    {
        return false;
    }

    const size_t modeLen = strlen(modeStart);
    if (modeLen >= modeSize)
    {
        return false;
    }
    memcpy(mode, modeStart, modeLen + 1);

    return true;
}

static bool app_network_build_pub_topic(char *topicOut, size_t topicOutSize, const char *deviceId, app_msg_type_t kind)
{
    if (topicOut == nullptr || deviceId == nullptr || kind >= MAX_APP_MSG_TYPE)
    {
        return false;
    }

    const int writeLen = snprintf(topicOut, topicOutSize, MQTT_PUB_TOPIC_FMT, deviceId, kAppMsgKind[kind], kAppMsgMode[kind]);
    if (writeLen < 0 || (size_t)writeLen >= topicOutSize)
    {
        return false;
    }
    return true;
}

static bool app_network_connect_client()
{
    espClient.stop();
    delay(50);

    if (strlen(appConfig.mqtt_username) == 0)
    {
        return client.connect(appConfig.device_id);
    }

    return client.connect(appConfig.device_id, appConfig.mqtt_username, appConfig.mqtt_password);
}

static bool app_network_probe_tcp(const IPAddress &broker_ip)
{
    if (!APP_MQTT_TCP_PROBE_ENABLED)
    {
        return true;
    }

    WiFiClient probe_client;
    probe_client.setTimeout(APP_MQTT_TCP_PROBE_TIMEOUT_MS / 1000);

    Serial.printf("TCP probe %s:%u timeout=%u ms...",
                  broker_ip.toString().c_str(),
                  static_cast<unsigned int>(appConfig.mqtt_port),
                  static_cast<unsigned int>(APP_MQTT_TCP_PROBE_TIMEOUT_MS));
    const bool connected = probe_client.connect(broker_ip, appConfig.mqtt_port, APP_MQTT_TCP_PROBE_TIMEOUT_MS);
    if (connected)
    {
        Serial.println("connected");
        probe_client.stop();
        delay(100);
        return true;
    }

    Serial.println("failed");
    probe_client.stop();
    return false;
}

static bool app_network_connect_mqtt_with_retries(const char *context)
{
    IPAddress broker_ip;
    const int dns_result = WiFi.hostByName(appConfig.mqtt_broker, broker_ip);

    Serial.println("===== MQTT Connect =====");
    Serial.printf("Context: %s\n", context);
    Serial.printf("Broker: %s\n", appConfig.mqtt_broker);
    Serial.printf("Broker DNS: %s%s\n", dns_result == 1 ? broker_ip.toString().c_str() : "failed", dns_result == 1 ? "" : "");
    Serial.printf("Port: %u\n", static_cast<unsigned int>(appConfig.mqtt_port));
    Serial.printf("Client ID: %s\n", appConfig.device_id);
    Serial.printf("Auth: %s\n", strlen(appConfig.mqtt_username) > 0 ? "enabled" : "disabled");
    Serial.printf("Retries: %u delay=%u ms\n",
                  static_cast<unsigned int>(APP_MQTT_CONNECT_RETRY_COUNT),
                  static_cast<unsigned int>(APP_MQTT_CONNECT_RETRY_DELAY_MS));

    if (dns_result != 1)
    {
        Serial.println("MQTT DNS resolution failed; cannot connect.");
        Serial.println("========================");
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_NETWORK,
                            APP_DEBUG_LOG_ERROR,
                            APP_DEBUG_EVENT_MQTT_DNS_FAILED,
                            app_network_context_id(context),
                            0);
        return false;
    }

    app_network_probe_tcp(broker_ip);

    client.setServer(broker_ip, appConfig.mqtt_port);
    client.setCallback(app_network_sub_callback);

    for (uint8_t attempt = 1; attempt <= APP_MQTT_CONNECT_RETRY_COUNT; attempt++)
    {
        Serial.printf("Connecting to MQTT attempt %u/%u via %s...",
                      attempt,
                      static_cast<unsigned int>(APP_MQTT_CONNECT_RETRY_COUNT),
                      broker_ip.toString().c_str());
        if (app_network_connect_client())
        {
            Serial.println("connected");
            Serial.println("========================");
            APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_NETWORK,
                                APP_DEBUG_LOG_INFO,
                                APP_DEBUG_EVENT_MQTT_CONNECTED,
                                app_network_context_id(context),
                                static_cast<int32_t>(appConfig.mqtt_port));
            return app_network_subscribe_topics();
        }

        Serial.printf("failed, rc=%d\n", client.state());
        if (attempt < APP_MQTT_CONNECT_RETRY_COUNT)
        {
            delay(APP_MQTT_CONNECT_RETRY_DELAY_MS);
        }
    }

    Serial.println("MQTT Connection Failed; settings may be wrong or broker may be unreachable.");
    Serial.println("========================");
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_NETWORK,
                        APP_DEBUG_LOG_ERROR,
                        APP_DEBUG_EVENT_MQTT_FAILED,
                        app_network_context_id(context),
                        client.state());
    return false;
}

static bool app_network_subscribe_topics()
{
    bool ok = true;

    ok = app_network_subscribe_topic(APP_MQTT_CONFIG_KIND, APP_MQTT_CONFIG_REPLY_MODE) && ok;
    ok = app_network_subscribe_topic(APP_MQTT_CONFIG_KIND, APP_MQTT_CONFIG_PUSH_MODE) && ok;
    ok = app_network_subscribe_ota_kind_offer_topic() && ok;
    ok = app_network_subscribe_topic(APP_MQTT_PUB_KIND, "immediate") && ok;
    ok = app_network_subscribe_topic(APP_MQTT_PUB_KIND, "enqueue") && ok;

    return ok;
}

static bool app_network_subscribe_topic(const char *kind, const char *mode)
{
    char topic[128];
    const int write_len = snprintf(topic, sizeof(topic), MQTT_PUB_TOPIC_FMT, appConfig.device_id, kind, mode);
    if (write_len < 0 || static_cast<size_t>(write_len) >= sizeof(topic))
    {
        ESP_LOGE(TAG, "Failed to build subscribe topic: %s/%s\n", kind, mode);
        return false;
    }

    if (client.subscribe(topic) == false)
    {
        ESP_LOGE(TAG, "Failed to subscribe topic: %s\n", topic);
        return false;
    }

    ESP_LOGI(TAG, "** Subscribed to topic: %s\n", topic);
    return true;
}

static bool app_network_subscribe_ota_kind_offer_topic()
{
    char topic[128];
    const int write_len = snprintf(topic, sizeof(topic), MQTT_OTA_KIND_OFFER_TOPIC_FMT, APP_DEVICE_KIND, appConfig.device_id);
    if (write_len < 0 || static_cast<size_t>(write_len) >= sizeof(topic))
    {
        ESP_LOGE(TAG, "Failed to build OTA kind offer subscribe topic\n");
        return false;
    }

    if (client.subscribe(topic) == false)
    {
        ESP_LOGE(TAG, "Failed to subscribe topic: %s\n", topic);
        return false;
    }

    ESP_LOGI(TAG, "** Subscribed to topic: %s\n", topic);
    return true;
}

static bool app_network_is_ota_kind_offer_topic(const char *topic)
{
    char expected[128];
    const int write_len = snprintf(expected, sizeof(expected), MQTT_OTA_KIND_OFFER_TOPIC_FMT, APP_DEVICE_KIND, appConfig.device_id);
    if (write_len < 0 || static_cast<size_t>(write_len) >= sizeof(expected))
    {
        return false;
    }
    return strcmp(topic, expected) == 0;
}

void app_network_sub_callback(char *topic, byte *payload, unsigned int length)
{
    // handle message
    if (length >= 512)
    {
        Serial.print("Message arrived [");
        Serial.print(topic);
        Serial.print("] ");
        Serial.println("Payload too large");
        return;
    }

    if (app_network_is_ota_kind_offer_topic(topic))
    {
        Serial.print("Message arrived [");
        Serial.print(topic);
        Serial.print("] ");
        if (app_ota_apply_offer_json(payload, length))
        {
            Serial.println("OTA offer received via MQTT");
        }
        return;
    }

    char topicClientId[DEVICE_ID_LEN];
    char topicKind[32];
    char topicMode[32];
    if (app_network_parse_kinds_topic(topic, topicClientId, sizeof(topicClientId), topicKind, sizeof(topicKind), topicMode, sizeof(topicMode)) == false)
    {
        Serial.print("Message arrived [");
        Serial.print(topic);
        Serial.print("] ");
        Serial.println("Invalid topic");
        return;
    }

    if (strcmp(topicClientId, appConfig.device_id) != 0)
    {
        ESP_LOGD(TAG, "Ignore message for other client: %s", topicClientId);
        return;
    }

    Serial.print("Message arrived [");
    Serial.print(topic);
    Serial.print("] ");

    if (strcmp(topicKind, APP_MQTT_CONFIG_KIND) == 0)
    {
        if (strcmp(topicMode, APP_MQTT_CONFIG_PUSH_MODE) == 0 || strcmp(topicMode, APP_MQTT_CONFIG_REPLY_MODE) == 0)
        {
            if (app_device_adapter_apply_runtime_config_json(payload, length))
            {
                Serial.println("Runtime config received via MQTT");
            }
        }
        return;
    }

    if (strcmp(topicKind, APP_MQTT_PUB_KIND) != 0)
    {
        ESP_LOGD(TAG, "Ignore message for kind: %s", topicKind);
        return;
    }

    if (strcmp(topicMode, "immediate") != 0 && strcmp(topicMode, "enqueue") != 0)
    {
        Serial.println("Unknown mode");
        return;
    }

    // Compatible behavior: if binary task payload arrives, feed task engine.
    if (app_task_set(payload, length))
    {
        Serial.printf("Task request accepted from %s/%s (%u bytes)\n", topicKind, topicMode, length);
        return;
    }

    Serial.printf("MQTT message received (%s/%s, %u bytes)\n", topicKind, topicMode, length);
}
// ================================================================
// Public functions
// ================================================================

bool app_network_start()
{
    if (!appConfig.is_network_configured())
    {
        Serial.println("Network configuration is missing.");
        Serial.printf("Missing fields: ssid=%s password=%s mqtt_broker=%s mqtt_port=%s\n",
                      strlen(appConfig.ssid) > 0 ? "set" : "empty",
                      strlen(appConfig.password) > 0 ? "set" : "empty",
                      strlen(appConfig.mqtt_broker) > 0 ? "set" : "empty",
                      appConfig.mqtt_port > 0 ? "set" : "empty");
        if (s_setup_portal_enabled)
        {
            Serial.println("Starting setup portal.");
            app_initial_setting_start_portal(APP_INITIAL_SETTING_PORTAL_REASON_UNCONFIGURED);
        }
        else
        {
            Serial.println("Setup portal is disabled; continuing without AP mode.");
        }
        return false;
    }

    // Wifi
    WiFi.mode(WIFI_STA);
    Serial.println("===== Wi-Fi STA Connect =====");
    Serial.printf("SSID: %s\n", appConfig.ssid);
    Serial.printf("Password: [SET] (len=%u)\n", static_cast<unsigned int>(strlen(appConfig.password)));
    Serial.printf("Timeout: %u ms\n", static_cast<unsigned int>(APP_WIFI_CONNECT_TIMEOUT_MS));
    WiFi.begin(appConfig.ssid, appConfig.password);
    Serial.print("\nWifi Connecting");
    const uint32_t start_ms = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - start_ms) < APP_WIFI_CONNECT_TIMEOUT_MS)
    {
        delay(500);
        Serial.print(".");
    }

    if (WiFi.status() != WL_CONNECTED)
    {
        const wl_status_t status = WiFi.status();
        Serial.printf("\nWiFi Connection Failed: status=%d (%s)\n",
                      static_cast<int>(status),
                      app_network_wifi_status_name(status));
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_NETWORK,
                            APP_DEBUG_LOG_ERROR,
                            APP_DEBUG_EVENT_WIFI_FAILED,
                            static_cast<int32_t>(status),
                            0);
        if (app_device_adapter_has_valid_runtime_config())
        {
            Serial.println("WiFi unavailable; continuing with saved runtime config.");
            return false;
        }

        Serial.println("No saved runtime config is available; starting setup portal for reconfiguration.");
        if (s_setup_portal_enabled)
        {
            app_initial_setting_start_portal(APP_INITIAL_SETTING_PORTAL_REASON_WIFI_FAILURE,
                                             APP_SETUP_PORTAL_RECOVERY_TIMEOUT_MS);
        }
        else
        {
            Serial.println("Setup portal is disabled; continuing without AP mode.");
        }
        return false;
    }
    WiFi.setTxPower(WIFI_POWER_13dBm);
    Serial.println("\n WiFi connected");
    Serial.println("IP Address: " + WiFi.localIP().toString());
    Serial.println("Gateway: " + WiFi.gatewayIP().toString());
    Serial.printf("RSSI: %d dBm\n", WiFi.RSSI());
    Serial.println("=============================");
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_NETWORK,
                        WiFi.RSSI() < -85 ? APP_DEBUG_LOG_WARNING : APP_DEBUG_LOG_INFO,
                        APP_DEBUG_EVENT_WIFI_CONNECTED,
                        WiFi.RSSI(),
                        0);

    // mDNS
    // if (MDNS.begin(appConfig.device_id))
    // {
    //     Serial.println("mDNS responder started");
    //     MDNS.addService("http", "tcp", 80);
    // }

    if (!app_network_connect_mqtt_with_retries("startup"))
    {
        if (app_device_adapter_has_valid_runtime_config())
        {
            Serial.println("MQTT unavailable; continuing with saved runtime config.");
            return false;
        }

        Serial.println("No saved runtime config is available; starting setup portal for MQTT reconfiguration.");
        if (s_setup_portal_enabled)
        {
            app_initial_setting_start_portal(APP_INITIAL_SETTING_PORTAL_REASON_MQTT_FAILURE,
                                             APP_SETUP_PORTAL_RECOVERY_TIMEOUT_MS);
        }
        else
        {
            Serial.println("Setup portal is disabled; continuing without AP mode.");
        }
        return false;
    }

    return true;
}

bool app_network_is_connected()
{
    return client.connected();
}

void app_network_stop()
{
    app_network_flush(APP_MQTT_DISCONNECT_DRAIN_MS);

    // MQTT
    client.disconnect();

    // mDNS
    // MDNS.end();

    // Wifi
    WiFi.disconnect(true);
}

void app_network_loop()
{
    if (client.connected())
    {
        client.loop();
    }
}

void app_network_flush(uint32_t duration_ms)
{
    const uint32_t start_ms = millis();
    do
    {
        app_network_loop();
        delay(20);
    } while (client.connected() && (millis() - start_ms) < duration_ms);
}

bool app_network_send(app_msg_type_t kind, const uint8_t *const data, uint16_t data_len, int seqId, bool retain)
{
    char acTopic[128];
    (void)seqId;

    // check kind
    if (kind >= MAX_APP_MSG_TYPE)
    {
        ESP_LOGE(TAG, "Invalid message type\n");
        return false;
    }

    // check connection status
    if (client.connected() == false)
    {
        ESP_LOGE(TAG, "MQTT client is not connected\n");
        return false;
    }

    // publish message
    if (app_network_build_pub_topic(acTopic, sizeof(acTopic), appConfig.device_id, kind) == false)
    {
        ESP_LOGE(TAG, "Failed to build publish topic\n");
        return false;
    }
    ESP_LOGI(TAG, "** Publishing to topic: %s\n", acTopic);
    if (client.publish(acTopic, data, data_len, retain) == false)
    {
        ESP_LOGE(TAG, "Failed to publish message\n");
        return false;
    }

    return true;
}

bool app_network_send_large(app_msg_type_t kind, const uint8_t *const data, unsigned int data_len, int seqId, bool retain)
{
    char acTopic[128];
    (void)seqId;

    // check kind
    if (kind >= MAX_APP_MSG_TYPE)
    {
        ESP_LOGE(TAG, "Invalid message type\n");
        return false;
    }

    // check connection status
    if (client.connected() == false)
    {
        ESP_LOGE(TAG, "MQTT client is not connected\n");
        return false;
    }

    // publish message
    if (app_network_build_pub_topic(acTopic, sizeof(acTopic), appConfig.device_id, kind) == false)
    {
        ESP_LOGE(TAG, "Failed to build publish topic\n");
        return false;
    }
    ESP_LOGI(TAG, "** Publishing to topic: %s\n", acTopic);
    if (client.beginPublish(acTopic, data_len, retain) == false)
    {
        ESP_LOGE(TAG, "Failed to begin publish message\n");
        return false;
    }
    const int chunkSize = 1024 - 128;
    for (int i = 0; i < data_len; i += chunkSize)
    {
        int len = chunkSize;
        if (i + len > data_len)
        {
            len = data_len - i;
        }
        if (client.write(data + i, len) == false)
        {
            ESP_LOGE(TAG, "Failed to write message(%d/%d)\n", i, data_len);
            return false;
        }
        app_network_loop();
        delay(100);
    }
    if (client.endPublish() == false)
    {
        ESP_LOGE(TAG, "Failed to end publish message\n");
        return false;
    }

    return true;
}

bool app_network_reconnect()
{
    Serial.println("Reconnecting to MQTT...");

    if (!appConfig.is_network_configured())
    {
        Serial.println("Network configuration is missing during reconnect.");
        return false;
    }

    WiFi.mode(WIFI_STA);
    Serial.printf("Reconnect Wi-Fi SSID: %s timeout=%u ms\n",
                  appConfig.ssid,
                  static_cast<unsigned int>(APP_WIFI_CONNECT_TIMEOUT_MS));
    WiFi.begin(appConfig.ssid, appConfig.password);
    Serial.print("\nWifi Connecting");
    const uint32_t start_ms = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - start_ms) < APP_WIFI_CONNECT_TIMEOUT_MS)
    {
        delay(500);
        Serial.print(".");
    }

    if (WiFi.status() != WL_CONNECTED)
    {
        const wl_status_t status = WiFi.status();
        Serial.printf("\nWiFi Connection Failed during reconnect: status=%d (%s)\n",
                      static_cast<int>(status),
                      app_network_wifi_status_name(status));
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_NETWORK,
                            APP_DEBUG_LOG_ERROR,
                            APP_DEBUG_EVENT_WIFI_RECONNECT_FAILED,
                            static_cast<int32_t>(status),
                            0);
        return false;
    }

    WiFi.setTxPower(WIFI_POWER_19_5dBm);
    Serial.println("\n WiFi connected");
    Serial.println("IP Address: " + WiFi.localIP().toString());
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_NETWORK,
                        WiFi.RSSI() < -85 ? APP_DEBUG_LOG_WARNING : APP_DEBUG_LOG_INFO,
                        APP_DEBUG_EVENT_WIFI_RECONNECTED,
                        WiFi.RSSI(),
                        0);

    return app_network_connect_mqtt_with_retries("reconnect");
}

bool app_network_request_runtime_config()
{
    static const char payload[] = "{\"request\":\"runtime_config\"}";
    char topic[128];

    if (!client.connected())
    {
        return false;
    }

    const int write_len = snprintf(topic, sizeof(topic), "/%s/kinds/%s/%s", appConfig.device_id, APP_MQTT_CONFIG_KIND, APP_MQTT_CONFIG_REQUEST_MODE);
    if (write_len < 0 || static_cast<size_t>(write_len) >= sizeof(topic))
    {
        return false;
    }

    return client.publish(topic, reinterpret_cast<const uint8_t *>(payload), strlen(payload), false);
}

bool app_network_wait_for_runtime_config(uint32_t timeout_ms)
{
    const uint32_t start_ms = millis();
    while ((millis() - start_ms) < timeout_ms)
    {
        app_network_loop();
        if (app_device_adapter_is_runtime_config_received())
        {
            return true;
        }
        delay(50);
    }

    return app_device_adapter_is_runtime_config_received();
}

bool app_network_wait_for_ota_offer(uint32_t timeout_ms)
{
    const uint32_t start_ms = millis();
    while ((millis() - start_ms) < timeout_ms)
    {
        app_network_loop();
        if (app_ota_is_offer_received())
        {
            return true;
        }
        delay(50);
    }

    return app_ota_is_offer_received();
}

void app_network_set_setup_portal_enabled(bool enabled)
{
    s_setup_portal_enabled = enabled;
}

bool app_network_is_setup_portal_enabled()
{
    return s_setup_portal_enabled;
}
