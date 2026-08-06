#include "fgt_schedule_policy.h"

namespace fgt
{

ScheduledBatchDecision decide_scheduled_batch(time_t now_utc,
                                              time_t schedule_epoch_utc,
                                              bool ota_update_attempted,
                                              bool persisted_history_available)
{
    ScheduledBatchDecision decision = {};
    if (now_utc > schedule_epoch_utc)
    {
        const uint64_t delay = static_cast<uint64_t>(now_utc - schedule_epoch_utc);
        decision.delay_sec = delay > UINT32_MAX
                                 ? UINT32_MAX
                                 : static_cast<uint32_t>(delay);
    }
    if (decision.delay_sec > kScheduleOnTimeGraceSec &&
        (!persisted_history_available ||
         decision.delay_sec > kScheduleCatchUpLimitSec))
    {
        decision.action = ScheduledBatchAction::skip_too_old;
    }
    else if (ota_update_attempted)
    {
        decision.action = ScheduledBatchAction::defer_for_ota;
    }
    else if (decision.delay_sec > kScheduleOnTimeGraceSec)
    {
        decision.action = ScheduledBatchAction::run_catch_up;
    }
    return decision;
}

} // namespace fgt
