#include "app.h"

#include <Arduino.h>

static bool s_app_initialized = false;

void setup()
{
    s_app_initialized = (app_init() == 0);
}

void loop()
{
    if (s_app_initialized)
    {
        app_loop();
        return;
    }

    delay(1000);
}
