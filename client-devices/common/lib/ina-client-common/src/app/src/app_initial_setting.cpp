#include "app_initial_setting.h"

#include <Arduino.h>
#include <DNSServer.h>
#include <ESPAsyncWebServer.h>
#include <WiFi.h>
#include <string.h>

#include "app_config.h"
#include "app_def.h"

#define TAG "app_initial_setting"

static AsyncWebServer s_server(80);
static DNSServer s_dns_server;
static bool s_restart_requested = false;
static app_initial_setting_portal_reason_t s_portal_reason = APP_INITIAL_SETTING_PORTAL_REASON_UNCONFIGURED;

static String app_initial_setting_escape_attr(const char *value);
static uint8_t app_initial_setting_connected_station_count();

static const char *app_initial_setting_portal_reason_name(app_initial_setting_portal_reason_t reason)
{
    switch (reason)
    {
    case APP_INITIAL_SETTING_PORTAL_REASON_UNCONFIGURED:
        return "unconfigured";
    case APP_INITIAL_SETTING_PORTAL_REASON_BUTTON:
        return "button";
    case APP_INITIAL_SETTING_PORTAL_REASON_CONNECTION_RESET:
        return "connection_reset";
    case APP_INITIAL_SETTING_PORTAL_REASON_WIFI_FAILURE:
        return "wifi_failure";
    case APP_INITIAL_SETTING_PORTAL_REASON_MQTT_FAILURE:
        return "mqtt_failure";
    default:
        return "unknown";
    }
}

static const char *app_initial_setting_portal_reason_message(app_initial_setting_portal_reason_t reason)
{
    switch (reason)
    {
    case APP_INITIAL_SETTING_PORTAL_REASON_UNCONFIGURED:
        return "Connection settings are not configured yet.";
    case APP_INITIAL_SETTING_PORTAL_REASON_BUTTON:
        return "Setup mode was requested with the BOOT button.";
    case APP_INITIAL_SETTING_PORTAL_REASON_CONNECTION_RESET:
        return "Connection settings were cleared with the BOOT button.";
    case APP_INITIAL_SETTING_PORTAL_REASON_WIFI_FAILURE:
        return "Wi-Fi connection failed before reaching the MQTT broker.";
    case APP_INITIAL_SETTING_PORTAL_REASON_MQTT_FAILURE:
        return "MQTT broker connection failed after Wi-Fi connected.";
    default:
        return "Setup mode was started for an unknown reason.";
    }
}

static void app_initial_setting_init_status_led()
{
    pinMode(APP_STATUS_LED_PIN, OUTPUT);
    digitalWrite(APP_STATUS_LED_PIN, APP_STATUS_LED_ACTIVE_LOW ? HIGH : LOW);
}

static void app_initial_setting_set_status_led(bool on)
{
    digitalWrite(APP_STATUS_LED_PIN, APP_STATUS_LED_ACTIVE_LOW ? !on : on);
}

static void app_initial_setting_update_status_led_blink(uint32_t interval_ms)
{
    static uint32_t s_last_toggle_ms = 0;
    static bool s_led_on = false;

    const uint32_t now_ms = millis();
    if ((now_ms - s_last_toggle_ms) < interval_ms)
    {
        return;
    }

    s_last_toggle_ms = now_ms;
    s_led_on = !s_led_on;
    app_initial_setting_set_status_led(s_led_on);
}

static void app_initial_setting_copy_param(AsyncWebServerRequest *request,
                                           const char *name,
                                           char *dest,
                                           size_t dest_size,
                                           bool required,
                                           bool keep_existing_when_blank,
                                           bool *ok)
{
    if (!request->hasParam(name, true))
    {
        if (required)
        {
            *ok = false;
        }
        return;
    }

    const String value = request->getParam(name, true)->value();
    if (keep_existing_when_blank && value.length() == 0)
    {
        return;
    }

    if ((required && value.length() == 0) || value.length() >= dest_size)
    {
        *ok = false;
        return;
    }

    strncpy(dest, value.c_str(), dest_size - 1);
    dest[dest_size - 1] = '\0';
}

static String app_initial_setting_page()
{
    String html;
    html.reserve(4800);
    html += F("<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\">");
    html += F("<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">");
    html += F("<title>INA Water Controller Setup</title>");
    html += F("<style>");
    html += F("body{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f6f7f9;color:#1f2933}");
    html += F("main{max-width:520px;margin:0 auto;padding:28px 18px}");
    html += F("h1{font-size:24px;margin:0 0 8px}p{margin:0 0 20px;color:#52606d;line-height:1.5}");
    html += F("form{background:#fff;border:1px solid #d9e2ec;border-radius:8px;padding:18px;box-shadow:0 1px 2px rgba(15,23,42,.06)}");
    html += F("label{display:block;font-weight:600;margin:14px 0 6px}");
    html += F("input{box-sizing:border-box;width:100%;font:inherit;padding:10px 12px;border:1px solid #bcccdc;border-radius:6px;background:#fff}");
    html += F("input:focus{outline:2px solid #2f80ed33;border-color:#2f80ed}");
    html += F(".row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.hint{font-size:13px;color:#627d98;margin-top:6px}");
    html += F(".reason{background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:12px 14px;margin:14px 0 16px;color:#7c2d12}");
    html += F(".reason strong{display:block;margin-bottom:4px}.reason code{font-size:12px;color:#9a3412}");
    html += F("button{width:100%;margin-top:20px;padding:12px 14px;border:0;border-radius:6px;background:#1f6feb;color:#fff;font-weight:700;font:inherit}");
    html += F("@media(max-width:520px){.row{grid-template-columns:1fr}}");
    html += F("</style></head><body><main>");
    html += F("<h1>INA Water Controller Setup</h1>");
    html += F("<p>Wi-Fi and MQTT settings are saved on the device. It will restart after saving.</p>");
    html += F("<section class=\"reason\"><strong>AP mode reason</strong>");
    html += app_initial_setting_portal_reason_message(s_portal_reason);
    html += F("<br><code>");
    html += app_initial_setting_portal_reason_name(s_portal_reason);
    html += F("</code></section>");
    html += F("<form method=\"post\" action=\"/save\">");
    html += F("<label for=\"ssid\">Wi-Fi SSID</label>");
    html += F("<input id=\"ssid\" name=\"ssid\" required maxlength=\"255\" value=\"");
    html += app_initial_setting_escape_attr(appConfig.ssid);
    html += F("\">");
    html += F("<label for=\"password\">Wi-Fi Password</label>");
    html += F("<input id=\"password\" name=\"password\" type=\"password\" maxlength=\"255\" autocomplete=\"new-password\">");
    html += F("<div class=\"hint\">Leave blank to keep the current Wi-Fi password.</div>");
    html += F("<label for=\"mqtt_broker\">MQTT Broker</label>");
    html += F("<input id=\"mqtt_broker\" name=\"mqtt_broker\" required maxlength=\"255\" value=\"");
    html += app_initial_setting_escape_attr(appConfig.mqtt_broker);
    html += F("\">");
    html += F("<div class=\"row\"><div><label for=\"mqtt_port\">MQTT Port</label>");
    html += F("<input id=\"mqtt_port\" name=\"mqtt_port\" type=\"number\" min=\"1\" max=\"65535\" required value=\"");
    html += String(appConfig.mqtt_port);
    html += F("\"></div><div><label for=\"mqtt_username\">MQTT Username</label>");
    html += F("<input id=\"mqtt_username\" name=\"mqtt_username\" maxlength=\"255\" value=\"");
    html += app_initial_setting_escape_attr(appConfig.mqtt_username);
    html += F("\"></div></div>");
    html += F("<label for=\"mqtt_password\">MQTT Password</label>");
    html += F("<input id=\"mqtt_password\" name=\"mqtt_password\" type=\"password\" maxlength=\"255\" autocomplete=\"new-password\">");
    html += F("<div class=\"hint\">Leave blank to keep the current MQTT password. Leave MQTT username and password both blank when authentication is not used.</div>");
    html += F("<button type=\"submit\">Save and Restart</button>");
    html += F("</form></main></body></html>");
    return html;
}

static String app_initial_setting_escape_attr(const char *value)
{
    String escaped;
    if (value == nullptr)
    {
        return escaped;
    }

    for (const char *p = value; *p != '\0'; p++)
    {
        switch (*p)
        {
        case '&':
            escaped += F("&amp;");
            break;
        case '"':
            escaped += F("&quot;");
            break;
        case '<':
            escaped += F("&lt;");
            break;
        case '>':
            escaped += F("&gt;");
            break;
        default:
            escaped += *p;
            break;
        }
    }

    return escaped;
}

static uint8_t app_initial_setting_connected_station_count()
{
    return WiFi.softAPgetStationNum();
}

static void app_initial_setting_apply_form(AsyncWebServerRequest *request)
{
    bool ok = true;
    uint16_t mqtt_port = 0;

    app_initial_setting_copy_param(request, "ssid", appConfig.ssid, sizeof(appConfig.ssid), true, false, &ok);
    app_initial_setting_copy_param(request, "password", appConfig.password, sizeof(appConfig.password), false, true, &ok);
    app_initial_setting_copy_param(request, "mqtt_broker", appConfig.mqtt_broker, sizeof(appConfig.mqtt_broker), true, false, &ok);
    app_initial_setting_copy_param(request, "mqtt_username", appConfig.mqtt_username, sizeof(appConfig.mqtt_username), false, false, &ok);
    app_initial_setting_copy_param(request, "mqtt_password", appConfig.mqtt_password, sizeof(appConfig.mqtt_password), false, true, &ok);

    if (request->hasParam("mqtt_username", true) &&
        request->getParam("mqtt_username", true)->value().length() == 0)
    {
        appConfig.mqtt_password[0] = '\0';
    }

    if (!request->hasParam("mqtt_port", true))
    {
        ok = false;
    }
    else
    {
        const int port = request->getParam("mqtt_port", true)->value().toInt();
        if (port <= 0 || port > 65535)
        {
            ok = false;
        }
        else
        {
            mqtt_port = static_cast<uint16_t>(port);
        }
    }

    const bool has_mqtt_username = strlen(appConfig.mqtt_username) > 0;
    const bool has_mqtt_password = strlen(appConfig.mqtt_password) > 0;
    if (strlen(appConfig.password) == 0 || has_mqtt_username != has_mqtt_password)
    {
        ok = false;
    }

    if (!ok)
    {
        request->send(400, "text/plain", "Invalid configuration");
        return;
    }

    appConfig.mqtt_port = mqtt_port;
    appConfig.crc32 = AppUtils().crc32((const uint8_t *)&appConfig, sizeof(AppConfig) - sizeof(uint32_t));
    Serial.println("Saving setup form configuration...");
    appConfig.show();
    appConfig.save();

    request->send(200, "text/html", "<!doctype html><html><body><h1>Saved</h1><p>The device will restart.</p></body></html>");
    s_restart_requested = true;
}

void app_initial_setting_start_portal(app_initial_setting_portal_reason_t reason, uint32_t recovery_timeout_ms)
{
    s_portal_reason = reason;
    IPAddress ap_ip;
    ap_ip.fromString(APP_INITIAL_SETTING_AP_IP);
    const IPAddress subnet(255, 255, 255, 0);

    Serial.println("Starting initial setting portal...");
    Serial.println("===== Setup Portal Settings =====");
    Serial.printf("Reason: %s\n", app_initial_setting_portal_reason_name(reason));
    Serial.printf("Recovery timeout: %s", recovery_timeout_ms > 0 ? "" : "disabled\n");
    if (recovery_timeout_ms > 0)
    {
        Serial.printf("%lu ms\n", static_cast<unsigned long>(recovery_timeout_ms));
    }
    Serial.printf("AP SSID: %s\n", APP_INITIAL_SETTING_SSID);
    Serial.printf("AP Password: %s (len=%u)\n",
                  strlen(APP_INITIAL_SETTING_PASS) > 0 ? "[SET]" : "(empty)",
                  static_cast<unsigned int>(strlen(APP_INITIAL_SETTING_PASS)));
    Serial.printf("AP IP: %s\n", APP_INITIAL_SETTING_AP_IP);
    Serial.printf("DNS captive portal: enabled\n");
    Serial.printf("HTTP URL: http://%s/\n", APP_INITIAL_SETTING_AP_IP);
    Serial.printf("Existing Wi-Fi SSID field value: %s\n", strlen(appConfig.ssid) > 0 ? appConfig.ssid : "(empty)");
    Serial.printf("Existing MQTT Broker field value: %s\n", strlen(appConfig.mqtt_broker) > 0 ? appConfig.mqtt_broker : "(empty)");
    Serial.println("=================================");
    app_initial_setting_init_status_led();
    WiFi.persistent(false);
    WiFi.disconnect(true, true);
    delay(200);
    WiFi.mode(WIFI_OFF);
    delay(200);
    WiFi.mode(WIFI_AP);
    if (!WiFi.softAPConfig(ap_ip, ap_ip, subnet))
    {
        Serial.println("Failed to configure initial setting AP");
        delay(1000);
        ESP.restart();
    }

    if (!WiFi.softAP(APP_INITIAL_SETTING_SSID, APP_INITIAL_SETTING_PASS))
    {
        Serial.println("Failed to start initial setting AP");
        delay(1000);
        ESP.restart();
    }

    s_dns_server.start(53, "*", ap_ip);

    s_server.on("/", HTTP_GET, [](AsyncWebServerRequest *request)
                { request->send(200, "text/html", app_initial_setting_page()); });
    s_server.on("/save", HTTP_POST, [](AsyncWebServerRequest *request)
                { app_initial_setting_apply_form(request); });
    s_server.onNotFound([](AsyncWebServerRequest *request)
                        { request->redirect("/"); });
    s_server.begin();

    Serial.printf("Initial setting AP started: ssid=%s ip=%s status_led=slow_blink\n",
                  APP_INITIAL_SETTING_SSID,
                  ap_ip.toString().c_str());

    uint32_t recovery_idle_start_ms = millis();
    uint8_t previous_station_count = app_initial_setting_connected_station_count();
    Serial.printf("Setup portal connected stations: %u\n", static_cast<unsigned int>(previous_station_count));

    while (true)
    {
        s_dns_server.processNextRequest();
        app_initial_setting_update_status_led_blink(APP_SETUP_PORTAL_ACTIVE_LED_BLINK_MS);

        const uint8_t station_count = app_initial_setting_connected_station_count();
        if (station_count != previous_station_count)
        {
            Serial.printf("Setup portal connected stations: %u\n", static_cast<unsigned int>(station_count));
            previous_station_count = station_count;
        }
        if (station_count > 0)
        {
            recovery_idle_start_ms = millis();
        }

        if (s_restart_requested)
        {
            app_initial_setting_set_status_led(true);
            delay(1000);
            ESP.restart();
        }
        if (recovery_timeout_ms > 0 && station_count == 0 && (millis() - recovery_idle_start_ms) >= recovery_timeout_ms)
        {
            Serial.printf("Setup portal recovery idle timeout reached after %lu ms with no AP clients. Restarting to retry normal operation...\n",
                          static_cast<unsigned long>(recovery_timeout_ms));
            delay(1000);
            ESP.restart();
        }
        delay(10);
    }
}

bool app_initial_setting_handle_setup_portal_request()
{
    app_initial_setting_init_status_led();
    pinMode(APP_SETUP_PORTAL_BUTTON_PIN, INPUT_PULLUP);
    Serial.println("===== Setup Portal Button =====");
    Serial.printf("Setup portal: press BOOT within %u ms and hold for %u ms.\n",
                  static_cast<unsigned int>(APP_SETUP_PORTAL_ARM_WINDOW_MS),
                  static_cast<unsigned int>(APP_SETUP_PORTAL_HOLD_MS));
    Serial.printf("Connection reset: keep holding BOOT for %u ms.\n",
                  static_cast<unsigned int>(APP_SETUP_PORTAL_RESET_HOLD_MS));
    Serial.printf("Button pin: %u active=LOW\n", static_cast<unsigned int>(APP_SETUP_PORTAL_BUTTON_PIN));
    Serial.println("LED: fast blink while hold is being accepted");
    Serial.println("================================");

    const uint32_t arm_start_ms = millis();
    while (digitalRead(APP_SETUP_PORTAL_BUTTON_PIN) != LOW)
    {
        if ((millis() - arm_start_ms) >= APP_SETUP_PORTAL_ARM_WINDOW_MS)
        {
            return false;
        }
        delay(20);
    }

    Serial.printf("Setup portal button detected at %u ms after boot.\n",
                  static_cast<unsigned int>(millis() - arm_start_ms));

    const uint32_t reset_hold_ms = max(static_cast<uint32_t>(APP_SETUP_PORTAL_RESET_HOLD_MS),
                                       static_cast<uint32_t>(APP_SETUP_PORTAL_HOLD_MS));
    Serial.printf("Setup portal button is pressed. Hold for %u ms to open setup portal, or %u ms to clear connection settings.\n",
                  static_cast<unsigned int>(APP_SETUP_PORTAL_HOLD_MS),
                  static_cast<unsigned int>(reset_hold_ms));

    const uint32_t start_ms = millis();
    bool reset_requested = false;
    while (digitalRead(APP_SETUP_PORTAL_BUTTON_PIN) == LOW)
    {
        app_initial_setting_update_status_led_blink(APP_SETUP_PORTAL_REQUEST_LED_BLINK_MS);
        if ((millis() - start_ms) >= reset_hold_ms)
        {
            reset_requested = true;
            break;
        }
        delay(50);
    }

    const uint32_t held_ms = millis() - start_ms;
    if (held_ms < APP_SETUP_PORTAL_HOLD_MS)
    {
        Serial.println("Setup portal request cancelled.");
        app_initial_setting_set_status_led(false);
        return false;
    }

    if (reset_requested)
    {
        Serial.println("Connection settings reset requested.");
        appConfig.clear_connection_settings();
        appConfig.save();
        app_initial_setting_start_portal(APP_INITIAL_SETTING_PORTAL_REASON_CONNECTION_RESET);
        return true;
    }

    Serial.println("Setup portal requested.");
    app_initial_setting_start_portal(APP_INITIAL_SETTING_PORTAL_REASON_BUTTON);
    return true;
}
