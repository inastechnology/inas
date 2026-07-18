#pragma once

#include <stdint.h>
#include <time.h>

typedef struct
{
    bool valid;
    bool in_progress;
    time_t schedule_epoch_utc;
    uint32_t recovery_ack;
    uint32_t batch_id;
} app_fgt_journal_state_t;

void app_fgt_journal_init();
const app_fgt_journal_state_t &app_fgt_journal_get();
bool app_fgt_journal_mark_started(time_t schedule_epoch_utc, uint32_t batch_id);
bool app_fgt_journal_mark_finished();
bool app_fgt_journal_acknowledge_recovery(uint32_t recovery_ack);
