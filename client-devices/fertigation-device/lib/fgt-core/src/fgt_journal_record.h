#pragma once

#include <stddef.h>
#include <stdint.h>
#include <time.h>

namespace fgt
{

constexpr uint32_t kJournalMagic = 0x4647544AUL;
constexpr uint16_t kJournalVersion = 1;

struct JournalState
{
    bool valid = false;
    bool in_progress = false;
    time_t schedule_epoch_utc = 0;
    uint32_t recovery_ack = 0;
    uint32_t batch_id = 0;
};

// Version 1 deliberately retains the deployed binary layout. The CRC length is
// derived from crc32's offset, not from sizeof(Record), because tail padding may
// follow crc32 when time_t requires 8-byte alignment.
struct JournalRecord
{
    uint32_t magic = 0;
    uint16_t version = 0;
    uint16_t state_size = 0;
    JournalState state = {};
    uint32_t crc32 = 0;
};

enum class JournalDecodeResult : uint8_t
{
    invalid = 0,
    current,
    legacy_crc,
};

constexpr size_t journal_crc_length()
{
    return offsetof(JournalRecord, crc32);
}

uint32_t journal_crc32(const uint8_t *data, size_t length);
JournalRecord make_journal_record(const JournalState &state);
JournalDecodeResult decode_journal_record(const uint8_t *data,
                                          size_t length,
                                          JournalState *state_out);

} // namespace fgt
