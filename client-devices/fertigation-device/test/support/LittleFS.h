#pragma once

#include <algorithm>
#include <cstring>
#include <map>
#include <string>
#include <vector>

struct File
{
    std::vector<uint8_t> *bytes = nullptr;
    explicit operator bool() const { return bytes != nullptr; }
    size_t size() const { return bytes ? bytes->size() : 0; }
    size_t read(uint8_t *out, size_t length)
    {
        const size_t count = std::min(length, size());
        if (count) std::memcpy(out, bytes->data(), count);
        return count;
    }
    size_t write(const uint8_t *data, size_t length)
    {
        if (!bytes) return 0;
        bytes->assign(data, data + length);
        return length;
    }
    void close() {}
};

struct TestLittleFS
{
    std::map<std::string, std::vector<uint8_t>> files;
    bool exists(const char *path) const { return files.count(path) != 0; }
    File open(const char *path, const char *mode)
    {
        if (mode[0] == 'w') files[path].clear();
        return {exists(path) ? &files[path] : nullptr};
    }
};
inline TestLittleFS LittleFS;
