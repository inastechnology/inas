#include "app_fgt_journal.h"

#include <LittleFS.h>

#include "app_utils.h"

static constexpr const char *kJournalFile = "/.fgt_batch_journal";
static constexpr uint32_t kJournalMagic = 0x4647544AUL;
static constexpr uint16_t kJournalVersion = 1;

typedef struct
{
    uint32_t magic;
    uint16_t version;
    uint16_t state_size;
    app_fgt_journal_state_t state;
    uint32_t crc32;
} app_fgt_journal_store_t;

static app_fgt_journal_state_t s_state = {};

static bool save_state()
{
    app_fgt_journal_store_t store = {};
    store.magic = kJournalMagic;
    store.version = kJournalVersion;
    store.state_size = sizeof(store.state);
    store.state = s_state;
    store.state.valid = true;
    store.crc32 = AppUtils::crc32(reinterpret_cast<const uint8_t *>(&store), sizeof(store) - sizeof(store.crc32));
    File file = LittleFS.open(kJournalFile, "w");
    if (!file)
    {
        return false;
    }
    const size_t written = file.write(reinterpret_cast<const uint8_t *>(&store), sizeof(store));
    file.close();
    if (written == sizeof(store))
    {
        s_state = store.state;
        return true;
    }
    return false;
}

void app_fgt_journal_init()
{
    s_state = {};
    if (!LittleFS.exists(kJournalFile))
    {
        s_state.valid = true;
        return;
    }
    File file = LittleFS.open(kJournalFile, "r");
    if (!file)
    {
        return;
    }
    app_fgt_journal_store_t store = {};
    const size_t read_size = file.read(reinterpret_cast<uint8_t *>(&store), sizeof(store));
    file.close();
    const uint32_t expected = AppUtils::crc32(reinterpret_cast<const uint8_t *>(&store), sizeof(store) - sizeof(store.crc32));
    if (read_size == sizeof(store) && store.magic == kJournalMagic &&
        store.version == kJournalVersion && store.state_size == sizeof(store.state) && store.crc32 == expected)
    {
        s_state = store.state;
        s_state.valid = true;
    }
}

const app_fgt_journal_state_t &app_fgt_journal_get()
{
    return s_state;
}

bool app_fgt_journal_mark_started(time_t schedule_epoch_utc, uint32_t batch_id)
{
    s_state.valid = true;
    s_state.in_progress = true;
    s_state.schedule_epoch_utc = schedule_epoch_utc;
    s_state.batch_id = batch_id;
    return save_state();
}

bool app_fgt_journal_mark_finished()
{
    s_state.in_progress = false;
    return save_state();
}

bool app_fgt_journal_acknowledge_recovery(uint32_t recovery_ack)
{
    if (recovery_ack == 0 || recovery_ack == s_state.recovery_ack)
    {
        return false;
    }
    s_state.recovery_ack = recovery_ack;
    s_state.in_progress = false;
    return save_state();
}
