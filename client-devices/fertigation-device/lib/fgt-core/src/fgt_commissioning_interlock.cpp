#include "fgt_commissioning_interlock.h"

namespace fgt
{

namespace
{

uint32_t remaining(uint32_t duration_ms, uint32_t started_ms, uint32_t now_ms)
{
    const uint32_t elapsed_ms = now_ms - started_ms;
    return elapsed_ms >= duration_ms ? 0 : duration_ms - elapsed_ms;
}

} // namespace

CommissioningInterlock::CommissioningInterlock(uint32_t guard_ms,
                                               uint32_t max_on_ms)
    : m_guard_ms(guard_ms),
      m_max_on_ms(max_on_ms)
{
}

CommissioningSwitchResult CommissioningInterlock::request_on(uint8_t channel,
                                                             uint32_t duration_ms,
                                                             uint32_t now_ms)
{
    if (channel >= 5)
    {
        return CommissioningSwitchResult::invalid_channel;
    }
    if (duration_ms == 0 || duration_ms > m_max_on_ms)
    {
        return CommissioningSwitchResult::invalid_duration;
    }
    if (m_active_channel >= 0)
    {
        return CommissioningSwitchResult::output_already_active;
    }
    if (m_has_last_off && remaining(m_guard_ms, m_last_off_ms, now_ms) > 0)
    {
        return CommissioningSwitchResult::guard_period_active;
    }

    m_active_channel = static_cast<int8_t>(channel);
    m_active_started_ms = now_ms;
    m_active_duration_ms = duration_ms;
    return CommissioningSwitchResult::ok;
}

bool CommissioningInterlock::request_off(uint32_t now_ms)
{
    if (m_active_channel < 0)
    {
        return false;
    }
    mark_off(now_ms);
    return true;
}

bool CommissioningInterlock::tick(uint32_t now_ms)
{
    if (m_active_channel < 0 ||
        remaining(m_active_duration_ms, m_active_started_ms, now_ms) > 0)
    {
        return false;
    }
    mark_off(now_ms);
    return true;
}

CommissioningSwitchSnapshot CommissioningInterlock::snapshot(uint32_t now_ms) const
{
    CommissioningSwitchSnapshot result = {};
    result.active_channel = m_active_channel;
    if (m_active_channel >= 0)
    {
        result.active_remaining_ms =
            remaining(m_active_duration_ms, m_active_started_ms, now_ms);
    }
    else if (m_has_last_off)
    {
        result.guard_remaining_ms = remaining(m_guard_ms, m_last_off_ms, now_ms);
    }
    return result;
}

void CommissioningInterlock::mark_off(uint32_t now_ms)
{
    m_active_channel = -1;
    m_active_started_ms = 0;
    m_active_duration_ms = 0;
    m_has_last_off = true;
    m_last_off_ms = now_ms;
}

const char *commissioning_switch_result_name(CommissioningSwitchResult result)
{
    switch (result)
    {
    case CommissioningSwitchResult::ok:
        return "ok";
    case CommissioningSwitchResult::invalid_channel:
        return "invalid_channel";
    case CommissioningSwitchResult::invalid_duration:
        return "invalid_duration";
    case CommissioningSwitchResult::output_already_active:
        return "output_already_active";
    case CommissioningSwitchResult::guard_period_active:
        return "guard_period_active";
    }
    return "unknown";
}

} // namespace fgt
