#pragma once

#include <stddef.h>
#include <stdint.h>

struct TestSerial
{
    template <typename... Args> void printf(const char *, Args...) {}
    void println(const char *) {}
};
inline TestSerial Serial;

template <typename T> T constrain(T value, T low, T high)
{
    return value < low ? low : (value > high ? high : value);
}
