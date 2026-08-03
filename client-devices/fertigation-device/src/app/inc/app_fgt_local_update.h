#pragma once

class AsyncWebServer;

typedef bool (*app_fgt_local_update_prepare_callback_t)();

void app_fgt_local_update_init(
    app_fgt_local_update_prepare_callback_t prepare_callback);
void app_fgt_local_update_register_routes(
    AsyncWebServer *server);
void app_fgt_local_update_loop();
void app_fgt_local_update_end();
bool app_fgt_local_update_busy();
