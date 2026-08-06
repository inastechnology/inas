#pragma once

#include <stdint.h>
#include <time.h>

namespace fgt
{

constexpr uint32_t kScheduleOnTimeGraceSec = 15UL * 60UL;
constexpr uint32_t kScheduleCatchUpLimitSec = 6UL * 60UL * 60UL;

enum class ScheduledBatchAction : uint8_t
{
    run_on_time = 0,
    run_catch_up,
    defer_for_ota,
    skip_too_old,
};

struct ScheduledBatchDecision
{
    ScheduledBatchAction action = ScheduledBatchAction::run_on_time;
    uint32_t delay_sec = 0;
};

ScheduledBatchDecision decide_scheduled_batch(time_t now_utc,
                                              time_t schedule_epoch_utc,
                                              bool ota_update_attempted,
                                              bool persisted_history_available);

} // namespace fgt
