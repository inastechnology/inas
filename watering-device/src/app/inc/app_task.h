#pragma once
#include <stdint.h>

typedef enum
{
    TASK_ID_NONE = 0,
    TASK_ID_SENSOR_REPORT, // sensor report task
    TASK_ID_CAMERA_REPORT, // camera report task
    TASK_ID_AUDIO_REPORT,  // audio report task
    TASK_ID_PUMP_CONTROL,  // pump control task
    TASK_ID_VALVE_CONTROL, // valve control task
    TASK_ID_MAX
} task_id_t;

#define TASK_MAGIC_NUMBER 0x1A5D

#pragma pack(push, 1)
typedef struct
{
    uint16_t magicNumber; // magic number to identify task request
    uint16_t nextTaskSec; // next task start time in seconds
} task_request_header_t;
#pragma pack(pop)

#pragma pack(push, 1)
typedef struct
{
    uint8_t taskId;
    uint8_t payload[3]; // payload for task request, can be used for additional parameters
} task_request_elem_t;
#pragma pack(pop)

#pragma pack(push, 1)
typedef struct
{
    uint8_t taskId;
    uint8_t reserved[3]; // payload for task request, can be used for additional parameters
} task_request_sensor_t;
#pragma pack(pop)

#pragma pack(push, 1)
typedef struct
{
    uint8_t taskId;
    uint8_t reserved[3]; // payload for task request, can be used for additional parameters
} task_request_cam_t;
#pragma pack(pop)

#pragma pack(push, 1)
typedef struct
{
    uint8_t taskId;
    uint8_t reserved[3]; // payload for task request, can be used for additional parameters
} task_request_audio_t;
#pragma pack(pop)

#pragma pack(push, 1)
typedef struct
{
    uint8_t taskId;
    uint8_t pumpId;       // pump ID for control
    uint16_t durationSec; // duration in seconds for pump control
} task_request_pump_t;
#pragma pack(pop)

#pragma pack(push, 1)
typedef struct
{
    uint8_t taskId;
    uint8_t valveId;      // valve ID for control
    uint16_t durationSec; // duration in seconds for valve control
} task_request_valve_t;
#pragma pack(pop)

void app_task_init();
void app_task_deinit();
bool app_task_set(const uint8_t *data, uint32_t len);
bool app_task_is_valid();
void app_task_reset();
uint16_t app_task_get_next_task_sec();
bool app_task_is_in_progress(task_id_t taskId);
bool app_task_is_all_completed();
task_request_elem_t *app_task_get(task_id_t taskId);
