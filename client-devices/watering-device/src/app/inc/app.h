#ifndef __APP_H__
#define __APP_H__

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string>
#include "esp_random.h"

int app_init();
void app_deinit();
void app_loop();

#endif // __APP_H__