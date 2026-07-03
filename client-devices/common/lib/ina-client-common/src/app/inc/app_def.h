#pragma once

// =================================================================================================
// Common Configuration
// =================================================================================================
#ifndef APP_REPORT_INTERVAL_SEC
#define APP_REPORT_INTERVAL_SEC 1200 // データ送信間隔（秒）
#endif

// =================================================================================================
// Network Configuration
// =================================================================================================
#ifndef APP_WIFI_SSID
#define APP_WIFI_SSID "" // 初期設定画面で設定する接続先Wi-Fi SSID
#endif

#ifndef APP_WIFI_PASS
#define APP_WIFI_PASS "" // 初期設定画面で設定する接続先Wi-Fiパスワード
#endif

#ifndef APP_INITIAL_SETTING_SSID
#define APP_INITIAL_SETTING_SSID "INADSensor-setup" // 初期設定APのSSID
#endif

#ifndef APP_INITIAL_SETTING_PASS
#define APP_INITIAL_SETTING_PASS "12345678" // 初期設定APのパスワード（8文字以上）
#endif

#ifndef APP_INITIAL_SETTING_AP_IP
#define APP_INITIAL_SETTING_AP_IP "192.168.4.1"
#endif

#ifndef APP_LITTLEFS_PARTITION_LABEL
#define APP_LITTLEFS_PARTITION_LABEL "storage"
#endif

#ifndef APP_WIFI_CONNECT_TIMEOUT_MS
#define APP_WIFI_CONNECT_TIMEOUT_MS 30000
#endif

#ifndef APP_MQTT_CONNECT_RETRY_COUNT
#define APP_MQTT_CONNECT_RETRY_COUNT 3
#endif

#ifndef APP_MQTT_CONNECT_RETRY_DELAY_MS
#define APP_MQTT_CONNECT_RETRY_DELAY_MS 2000
#endif

#ifndef APP_MQTT_TCP_PROBE_ENABLED
#define APP_MQTT_TCP_PROBE_ENABLED true
#endif

#ifndef APP_MQTT_TCP_PROBE_TIMEOUT_MS
#define APP_MQTT_TCP_PROBE_TIMEOUT_MS 5000
#endif

#ifndef APP_MQTT_STATUS_PUBLISH_DRAIN_MS
#define APP_MQTT_STATUS_PUBLISH_DRAIN_MS 1000
#endif

#ifndef APP_MQTT_DISCONNECT_DRAIN_MS
#define APP_MQTT_DISCONNECT_DRAIN_MS 250
#endif

#ifndef APP_DEBUG_LOG_MAX_EVENTS
#define APP_DEBUG_LOG_MAX_EVENTS 128
#endif

#ifndef APP_DEBUG_LOG_PAYLOAD_SIZE
#define APP_DEBUG_LOG_PAYLOAD_SIZE 512
#endif

#ifndef APP_DEBUG_LOG_PUBLISH_DRAIN_MS
#define APP_DEBUG_LOG_PUBLISH_DRAIN_MS 1000
#endif

#ifndef APP_FACTORY_RESET_BUTTON_PIN
#define APP_FACTORY_RESET_BUTTON_PIN 0
#endif

#ifndef APP_FACTORY_RESET_ARM_WINDOW_MS
#define APP_FACTORY_RESET_ARM_WINDOW_MS 3000
#endif

#ifndef APP_FACTORY_RESET_HOLD_MS
#define APP_FACTORY_RESET_HOLD_MS 5000
#endif

#ifndef APP_SETUP_PORTAL_BUTTON_PIN
#define APP_SETUP_PORTAL_BUTTON_PIN APP_FACTORY_RESET_BUTTON_PIN // XIAO ESP32S3 BOOT button (active low)
#endif

#ifndef APP_SETUP_PORTAL_ARM_WINDOW_MS
#define APP_SETUP_PORTAL_ARM_WINDOW_MS APP_FACTORY_RESET_ARM_WINDOW_MS
#endif

#ifndef APP_SETUP_PORTAL_HOLD_MS
#define APP_SETUP_PORTAL_HOLD_MS APP_FACTORY_RESET_HOLD_MS
#endif

#ifndef APP_SETUP_PORTAL_RESET_HOLD_MS
#define APP_SETUP_PORTAL_RESET_HOLD_MS 10000
#endif

#ifndef APP_STATUS_LED_PIN
#define APP_STATUS_LED_PIN LED_BUILTIN
#endif

#ifndef APP_STATUS_LED_ACTIVE_LOW
#define APP_STATUS_LED_ACTIVE_LOW true
#endif

#ifndef APP_SETUP_PORTAL_REQUEST_LED_BLINK_MS
#define APP_SETUP_PORTAL_REQUEST_LED_BLINK_MS 100
#endif

#ifndef APP_SETUP_PORTAL_ACTIVE_LED_BLINK_MS
#define APP_SETUP_PORTAL_ACTIVE_LED_BLINK_MS 500
#endif

#ifndef APP_SETUP_PORTAL_RECOVERY_TIMEOUT_MS
#define APP_SETUP_PORTAL_RECOVERY_TIMEOUT_MS 120000
#endif

#ifndef APP_MQTT_BROKER_ADDR
#define APP_MQTT_BROKER_ADDR "" // 初期設定画面で設定するMQTT Broker
#endif

#ifndef APP_MQTT_BROKER_PORT
#define APP_MQTT_BROKER_PORT 1883 // MQTT Brokerのポート番号
#endif

#ifndef APP_MQTT_USERNAME
#define APP_MQTT_USERNAME "" // MQTT Username (未設定時は空文字)
#endif

#ifndef APP_MQTT_PASSWORD
#define APP_MQTT_PASSWORD "" // MQTT Password (未設定時は空文字)
#endif

#ifndef APP_MQTT_PUB_KIND
#define APP_MQTT_PUB_KIND "agri" // Publish Topic kind
#endif

#ifndef APP_MQTT_PUB_MODE
#define APP_MQTT_PUB_MODE "immediate" // Publish Topic mode
#endif

#ifndef APP_MQTT_DEBUG_LOG_KIND
#define APP_MQTT_DEBUG_LOG_KIND "debug"
#endif

#ifndef APP_MQTT_DEBUG_LOG_MODE
#define APP_MQTT_DEBUG_LOG_MODE "log"
#endif

#ifndef APP_FIRMWARE_VERSION
#define APP_FIRMWARE_VERSION "0.0.0-dev"
#endif

#ifndef APP_FIRMWARE_BUILD_ID
#define APP_FIRMWARE_BUILD_ID __DATE__ " " __TIME__
#endif

#ifndef APP_FIRMWARE_PROJECT
#define APP_FIRMWARE_PROJECT "ina-device"
#endif

#ifndef APP_FIRMWARE_TARGET
#define APP_FIRMWARE_TARGET "esp32"
#endif

#ifndef APP_FIRMWARE_FRAMEWORK
#define APP_FIRMWARE_FRAMEWORK "arduino"
#endif

#ifndef APP_DEVICE_KIND
#define APP_DEVICE_KIND "DEV"
#endif

#ifndef APP_MQTT_OTA_KIND
#define APP_MQTT_OTA_KIND "ota"
#endif

#ifndef APP_MQTT_OTA_STATUS_MODE
#define APP_MQTT_OTA_STATUS_MODE "status"
#endif

#ifndef APP_OTA_OFFER_WAIT_MS
#define APP_OTA_OFFER_WAIT_MS 15000
#endif

#ifndef APP_OTA_HTTP_CONNECT_TIMEOUT_MS
#define APP_OTA_HTTP_CONNECT_TIMEOUT_MS 10000
#endif

#ifndef APP_OTA_HTTP_READ_TIMEOUT_MS
#define APP_OTA_HTTP_READ_TIMEOUT_MS 30000
#endif

#ifndef APP_OTA_TOTAL_TIMEOUT_MS
#define APP_OTA_TOTAL_TIMEOUT_MS 180000
#endif
