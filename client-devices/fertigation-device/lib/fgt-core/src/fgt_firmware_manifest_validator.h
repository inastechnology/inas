#pragma once

#include <stddef.h>
#include <stdint.h>

namespace fgt
{

class FirmwareManifestScanner
{
public:
    FirmwareManifestScanner();

    void reset();
    void feed(const uint8_t *data, size_t length);
    bool complete() const;
    bool overflowed() const;
    bool matches(const char *project,
                 const char *device_kind,
                 const char *target,
                 const char *framework) const;

private:
    static constexpr size_t kManifestCapacity = 512;
    char m_manifest[kManifestCapacity] = {};
    size_t m_manifest_length = 0;
    size_t m_begin_match_length = 0;
    bool m_capturing = false;
    bool m_complete = false;
    bool m_overflowed = false;

    bool field_equals(
        const char *field,
        const char *expected) const;
};

} // namespace fgt
