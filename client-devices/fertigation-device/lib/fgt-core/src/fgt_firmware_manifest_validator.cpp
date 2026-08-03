#include "fgt_firmware_manifest_validator.h"

#include <string.h>

namespace fgt
{

namespace
{

constexpr char kManifestBegin[] =
    "INAS_FW_MANIFEST_V1_BEGIN";
constexpr char kManifestEnd[] =
    "INAS_FW_MANIFEST_V1_END";

} // namespace

FirmwareManifestScanner::FirmwareManifestScanner()
{
    reset();
}

void FirmwareManifestScanner::reset()
{
    memset(m_manifest, 0, sizeof(m_manifest));
    m_manifest_length = 0;
    m_begin_match_length = 0;
    m_capturing = false;
    m_complete = false;
    m_overflowed = false;
}

void FirmwareManifestScanner::feed(
    const uint8_t *data,
    size_t length)
{
    if (data == nullptr || length == 0 ||
        m_complete || m_overflowed)
    {
        return;
    }

    for (size_t i = 0;
         i < length && !m_complete && !m_overflowed;
         ++i)
    {
        const char value = static_cast<char>(data[i]);
        if (!m_capturing)
        {
            if (value == kManifestBegin[m_begin_match_length])
            {
                ++m_begin_match_length;
                if (m_begin_match_length ==
                    sizeof(kManifestBegin) - 1)
                {
                    memcpy(
                        m_manifest,
                        kManifestBegin,
                        sizeof(kManifestBegin) - 1);
                    m_manifest_length =
                        sizeof(kManifestBegin) - 1;
                    m_manifest[m_manifest_length] = '\0';
                    m_capturing = true;
                }
            }
            else
            {
                m_begin_match_length =
                    value == kManifestBegin[0] ? 1 : 0;
            }
            continue;
        }

        if (m_manifest_length + 1 >=
            sizeof(m_manifest))
        {
            m_overflowed = true;
            return;
        }
        m_manifest[m_manifest_length++] = value;
        m_manifest[m_manifest_length] = '\0';

        const size_t end_length =
            sizeof(kManifestEnd) - 1;
        if (m_manifest_length >= end_length &&
            memcmp(
                m_manifest +
                    m_manifest_length - end_length,
                kManifestEnd,
                end_length) == 0)
        {
            m_complete = true;
        }
    }
}

bool FirmwareManifestScanner::complete() const
{
    return m_complete;
}

bool FirmwareManifestScanner::overflowed() const
{
    return m_overflowed;
}

bool FirmwareManifestScanner::field_equals(
    const char *field,
    const char *expected) const
{
    if (!m_complete || field == nullptr ||
        expected == nullptr)
    {
        return false;
    }
    const size_t field_length = strlen(field);
    const size_t expected_length = strlen(expected);
    const char *cursor = m_manifest;
    while (cursor != nullptr && *cursor != '\0')
    {
        const char *line_end = strchr(cursor, '\n');
        const size_t line_length =
            line_end != nullptr
                ? static_cast<size_t>(line_end - cursor)
                : strlen(cursor);
        if (line_length ==
                field_length + 1 + expected_length &&
            memcmp(cursor, field, field_length) == 0 &&
            cursor[field_length] == '=' &&
            memcmp(
                cursor + field_length + 1,
                expected,
                expected_length) == 0)
        {
            return true;
        }
        cursor =
            line_end != nullptr ? line_end + 1 : nullptr;
    }
    return false;
}

bool FirmwareManifestScanner::matches(
    const char *project,
    const char *device_kind,
    const char *target,
    const char *framework) const
{
    return field_equals("schema", "1") &&
           field_equals("project", project) &&
           field_equals("device_kind", device_kind) &&
           field_equals("target", target) &&
           field_equals("framework", framework);
}

} // namespace fgt
