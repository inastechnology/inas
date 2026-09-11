#include <unity.h>
#include "fgt_moisture_guard.h"

// Run the real configuration and journal implementation against an in-memory FS.
#include "../../src/app/src/app_fgt_runtime_config.cpp"
#include "../../src/app/src/app_fgt_journal.cpp"

static bool apply(const char *json)
{
    return app_fgt_runtime_config_apply_json(reinterpret_cast<const uint8_t *>(json), strlen(json));
}

void setUp()
{
    LittleFS.files.clear();
    app_fgt_runtime_config_init();
    app_fgt_journal_init();
}
void tearDown() {}

static void test_guard_settings_survive_restart_and_reject_invalid_json()
{
    TEST_ASSERT_FALSE(app_fgt_runtime_config_get().moisture_guard.enabled);
    TEST_ASSERT_TRUE(apply(R"({"fgt":{"enabled":true,"moisture_guard":{"enabled":true,"threshold_percent":60}},"schedules":[{"hour":6,"minute":30}]})"));
    app_fgt_runtime_config_init();
    TEST_ASSERT_TRUE(app_fgt_runtime_config_get().enabled);
    TEST_ASSERT_TRUE(app_fgt_runtime_config_get().moisture_guard.enabled);
    TEST_ASSERT_EQUAL_UINT8(60, app_fgt_runtime_config_get().moisture_guard.threshold_percent);
    TEST_ASSERT_EQUAL_UINT8(1, app_fgt_runtime_config_get().schedule_count);
    TEST_ASSERT_FALSE(app_fgt_runtime_config_is_received());

    for (const char *json : {
             R"({"fgt":{"moisture_guard":null}})",
             R"({"fgt":{"moisture_guard":[]}})",
             R"({"fgt":{"moisture_guard":{"enabled":1}}})",
             R"({"fgt":{"moisture_guard":{"enabled":"false"}}})",
             R"({"fgt":{"moisture_guard":{"enabled":null}}})",
             R"({"fgt":{"moisture_guard":{"threshold_percent":-1}}})",
             R"({"fgt":{"moisture_guard":{"threshold_percent":101}}})",
             R"({"fgt":{"moisture_guard":{"threshold_percent":60.5}}})",
             R"({"fgt":{"moisture_guard":{"threshold_percent":true}}})",
             R"({"fgt":{"moisture_guard":{"threshold_percent":"60"}}})",
             R"({"fgt":{"moisture_guard":{"threshold_percent":null}}})"})
    {
        TEST_ASSERT_FALSE_MESSAGE(apply(json), json);
        TEST_ASSERT_TRUE(app_fgt_runtime_config_get().moisture_guard.enabled);
        TEST_ASSERT_EQUAL_UINT8(60, app_fgt_runtime_config_get().moisture_guard.threshold_percent);
    }
    TEST_ASSERT_TRUE(apply(R"({"fgt":{"moisture_guard":{"enabled":false,"threshold_percent":0}}})"));
    app_fgt_runtime_config_init();
    TEST_ASSERT_FALSE(app_fgt_runtime_config_get().moisture_guard.enabled);
    TEST_ASSERT_EQUAL_UINT8(0, app_fgt_runtime_config_get().moisture_guard.threshold_percent);
    TEST_ASSERT_TRUE(apply(R"({"fgt":{"moisture_guard":{"enabled":true,"threshold_percent":100}}})"));
    app_fgt_runtime_config_init();
    TEST_ASSERT_EQUAL_UINT8(100, app_fgt_runtime_config_get().moisture_guard.threshold_percent);
}

// Frozen firmware 0.2.3 layout, independent of the current append-only structure.
struct LegacyConfigV2
{
    bool valid;
    bool received_from_mqtt;
    char ntp_server[256];
    int32_t timezone_offset_sec;
    uint32_t sleep_sec;
    uint32_t ota_check_interval_sec;
    bool debug_log_on_wake;
    bool enabled;
    uint32_t recovery_ack;
    bool timed_outputs_enabled;
    fgt::TimedProgram timed_program;
    fgt::Recipe recipe;
    fgt::Limits limits;
    app_fgt_sensor_config_t sensors;
    uint8_t schedule_count;
    app_fgt_schedule_entry_t schedules[APP_FGT_MAX_SCHEDULES];
};
struct LegacyStoreV2
{
    uint32_t magic;
    uint16_t version;
    uint16_t config_size;
    LegacyConfigV2 config;
    uint32_t crc32;
};

static void test_legacy_config_preserves_schedules_with_guard_disabled()
{
    LegacyStoreV2 legacy = {};
    legacy.magic = 0x46475443UL;
    legacy.version = 2;
    legacy.config_size = sizeof(legacy.config);
    legacy.config.valid = true;
    strcpy(legacy.config.ntp_server, "time.example.test");
    legacy.config.timezone_offset_sec = 32400;
    legacy.config.sleep_sec = 900;
    legacy.config.ota_check_interval_sec = 21600;
    legacy.config.enabled = true;
    legacy.config.recovery_ack = 7;
    legacy.config.sensors = default_sensors();
    legacy.config.schedule_count = 1;
    legacy.config.schedules[0] = {true, 6, 30};
    legacy.crc32 = AppUtils::crc32(reinterpret_cast<const uint8_t *>(&legacy), offsetof(LegacyStoreV2, crc32));
    const uint8_t *bytes = reinterpret_cast<const uint8_t *>(&legacy);
    LittleFS.files[APP_FGT_RUNTIME_CONFIG_FILE] = {bytes, bytes + sizeof(legacy)};
    app_fgt_runtime_config_init();
    const auto &config = app_fgt_runtime_config_get();
    TEST_ASSERT_TRUE(config.enabled);
    TEST_ASSERT_EQUAL_STRING("time.example.test", config.ntp_server);
    TEST_ASSERT_EQUAL_UINT32(900, config.sleep_sec);
    TEST_ASSERT_EQUAL_UINT32(7, config.recovery_ack);
    TEST_ASSERT_EQUAL_UINT8(1, config.schedule_count);
    TEST_ASSERT_EQUAL_UINT8(30, config.schedules[0].minute);
    TEST_ASSERT_FALSE(config.moisture_guard.enabled);
    TEST_ASSERT_EQUAL_UINT8(40, config.moisture_guard.threshold_percent);
    TEST_ASSERT_TRUE(app_fgt_runtime_config_save_current());
    app_fgt_runtime_config_init();
    TEST_ASSERT_EQUAL_UINT32(900, app_fgt_runtime_config_get().sleep_sec);

    // A damaged old record must not silently migrate into automatic operation.
    LittleFS.files[APP_FGT_RUNTIME_CONFIG_FILE] = {bytes, bytes + sizeof(legacy)};
    LittleFS.files[APP_FGT_RUNTIME_CONFIG_FILE][20] ^= 1;
    app_fgt_runtime_config_init();
    TEST_ASSERT_FALSE(app_fgt_runtime_config_get().enabled);
}

static void test_consumed_moisture_skip_is_not_due_after_restart()
{
    TEST_ASSERT_TRUE(apply(R"({"timezone_offset_sec":0,"fgt":{"enabled":true,"moisture_guard":{"enabled":true,"threshold_percent":60}},"schedules":[{"hour":6,"minute":30},{"hour":16,"minute":30}]})"));
    const time_t due = 20000L * 86400L + 6L * 3600L + 30L * 60L;
    app_fgt_schedule_entry_t schedule;
    time_t epoch = 0;
    TEST_ASSERT_TRUE(app_fgt_runtime_config_find_due_schedule(due, 0, &schedule, &epoch));
    TEST_ASSERT_EQUAL(fgt::MoistureGuardDecision::skip_wet,
                      fgt::decide_moisture_guard(app_fgt_runtime_config_get().moisture_guard, true, 60.0f));
    TEST_ASSERT_TRUE(app_fgt_journal_mark_started(epoch, 42));
    TEST_ASSERT_TRUE(app_fgt_journal_mark_finished());
    app_fgt_runtime_config_init();
    app_fgt_journal_init();
    TEST_ASSERT_FALSE(app_fgt_journal_get().in_progress);
    TEST_ASSERT_FALSE(app_fgt_runtime_config_find_due_schedule(due + 300, app_fgt_journal_get().schedule_epoch_utc, &schedule, &epoch));
    TEST_ASSERT_TRUE(app_fgt_runtime_config_find_due_schedule(due + 10 * 3600, app_fgt_journal_get().schedule_epoch_utc, &schedule, &epoch));
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_guard_settings_survive_restart_and_reject_invalid_json);
    RUN_TEST(test_legacy_config_preserves_schedules_with_guard_disabled);
    RUN_TEST(test_consumed_moisture_skip_is_not_due_after_restart);
    return UNITY_END();
}
