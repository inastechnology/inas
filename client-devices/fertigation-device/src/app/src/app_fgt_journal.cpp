#include "app_fgt_journal.h"

#include <LittleFS.h>

static constexpr const char *kJournalFile = "/.fgt_batch_journal";

static app_fgt_journal_state_t s_state = {};
static bool s_has_persisted_state = false;

static bool save_state()
{
    const fgt::JournalRecord store = fgt::make_journal_record(s_state);
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
        s_has_persisted_state = true;
        return true;
    }
    return false;
}

void app_fgt_journal_init()
{
    s_state = {};
    s_has_persisted_state = false;
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
    fgt::JournalRecord store = {};
    const size_t read_size = file.read(reinterpret_cast<uint8_t *>(&store), sizeof(store));
    file.close();
    app_fgt_journal_state_t loaded = {};
    if (fgt::decode_journal_record(
            reinterpret_cast<const uint8_t *>(&store),
            read_size,
            &loaded) != fgt::JournalDecodeResult::invalid)
    {
        s_state = loaded;
        s_has_persisted_state = true;
    }
}

const app_fgt_journal_state_t &app_fgt_journal_get()
{
    return s_state;
}

bool app_fgt_journal_has_persisted_state()
{
    return s_has_persisted_state;
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
