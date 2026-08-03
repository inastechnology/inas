#pragma once

#include <stdint.h>

namespace fgt
{

enum class CommissioningSwitchResult : uint8_t
{
    ok,
    invalid_channel,
    invalid_duration,
    output_already_active,
    guard_period_active,
};

struct CommissioningSwitchSnapshot
{
    int8_t active_channel = -1;
    uint32_t active_remaining_ms = 0;
    uint32_t guard_remaining_ms = 0;
};

class CommissioningInterlock
{
public:
    CommissioningInterlock(uint32_t guard_ms, uint32_t max_on_ms);

    CommissioningSwitchResult request_on(uint8_t channel,
                                         uint32_t duration_ms,
                                         uint32_t now_ms);
    bool request_off(uint32_t now_ms);
    bool tick(uint32_t now_ms);
    CommissioningSwitchSnapshot snapshot(uint32_t now_ms) const;

private:
    uint32_t m_guard_ms;
    uint32_t m_max_on_ms;
    int8_t m_active_channel = -1;
    uint32_t m_active_started_ms = 0;
    uint32_t m_active_duration_ms = 0;
    bool m_has_last_off = false;
    uint32_t m_last_off_ms = 0;

    void mark_off(uint32_t now_ms);
};

const char *commissioning_switch_result_name(CommissioningSwitchResult result);

} // namespace fgt
