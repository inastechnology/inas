#include "fgt_journal_record.h"

#include <string.h>

namespace fgt
{

uint32_t journal_crc32(const uint8_t *data, size_t length)
{
    uint32_t crc = 0xFFFFFFFFUL;
    for (size_t i = 0; i < length; ++i)
    {
        crc ^= data[i];
        for (size_t bit = 0; bit < 8; ++bit)
        {
            crc = (crc >> 1) ^ (0xEDB88320UL & -(crc & 1UL));
        }
    }
    return ~crc;
}

JournalRecord make_journal_record(const JournalState &state)
{
    JournalRecord record = {};
    record.magic = kJournalMagic;
    record.version = kJournalVersion;
    record.state_size = sizeof(record.state);
    record.state = state;
    record.state.valid = true;
    record.crc32 = journal_crc32(
        reinterpret_cast<const uint8_t *>(&record),
        journal_crc_length());
    return record;
}

JournalDecodeResult decode_journal_record(const uint8_t *data,
                                          size_t length,
                                          JournalState *state_out)
{
    if (data == nullptr || state_out == nullptr ||
        length != sizeof(JournalRecord))
    {
        return JournalDecodeResult::invalid;
    }

    JournalRecord record = {};
    memcpy(&record, data, sizeof(record));
    if (record.magic != kJournalMagic ||
        record.version != kJournalVersion ||
        record.state_size != sizeof(record.state))
    {
        return JournalDecodeResult::invalid;
    }

    const uint32_t stored_crc = record.crc32;
    const uint32_t current_crc = journal_crc32(
        reinterpret_cast<const uint8_t *>(&record),
        journal_crc_length());
    JournalDecodeResult result = JournalDecodeResult::current;
    if (stored_crc != current_crc)
    {
        // Firmware 0.2.1 included the zero-valued crc32 field itself when
        // writing records on ABIs with tail padding. Recreate that calculation
        // only as a read-side migration path. All new writes use the field
        // offset above.
        record.crc32 = 0;
        const uint32_t legacy_crc = journal_crc32(
            reinterpret_cast<const uint8_t *>(&record),
            sizeof(record) - sizeof(record.crc32));
        if (stored_crc != legacy_crc)
        {
            return JournalDecodeResult::invalid;
        }
        result = JournalDecodeResult::legacy_crc;
    }

    *state_out = record.state;
    state_out->valid = true;
    return result;
}

} // namespace fgt
