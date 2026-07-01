#include <string.h>
#include "app_task.h"
#include "app_def.h"

#define APP_TASK_MAX_ELEM 16 // Maximum number of task request elements
#pragma pack(push, 1)
typedef struct
{
    task_request_header_t header;                    // Header for task request
    task_request_elem_t elemList[APP_TASK_MAX_ELEM]; // List of task request elements
} task_context_t;
#pragma pack(pop)

static task_context_t __taskCtx;
static task_request_elem_t *__taskReqElemListPtr = __taskCtx.elemList;
static bool _taskInProgress[APP_TASK_MAX_ELEM] = {false}; // Task status array to track which tasks are in progress

void app_task_init()
{
    __taskCtx.header.magicNumber = 0;
    __taskCtx.header.nextTaskSec = 0; // Initialize to 0

    memset(__taskCtx.elemList, 0, sizeof(__taskCtx.elemList));

    memset(_taskInProgress, 0, sizeof(_taskInProgress));
}

void app_task_deinit()
{
    // No specific deinitialization needed for this task
}

bool app_task_set(const uint8_t *data, uint32_t len)
{
    if (len < sizeof(task_request_header_t) || len > sizeof(task_context_t))
    {
        // Invalid data length
        return false;
    }

    memcpy(&__taskCtx, data, sizeof(__taskCtx));
    if (__taskCtx.header.magicNumber != TASK_MAGIC_NUMBER)
    {
        // Invalid magic number
        return false;
    }
    // Check if the next task timestamp is valid
    if (__taskCtx.header.nextTaskSec == 0)
    {
        // Reset the next task timestamp to 600
        __taskCtx.header.nextTaskSec = 600;
    }
    int taskCount = sizeof(__taskCtx.elemList) / sizeof(task_request_elem_t);
    // Check if the task request elements are valid
    for (int i = 0; i < taskCount; i++)
    {
        if (__taskCtx.elemList[i].taskId >= TASK_ID_MAX)
        {
            // Invalid task ID
            return false;
        }
        _taskInProgress[i] = true; // Mark the task as in progress
    }
    // If we reach here, the task request is valid

    return true;
}

bool app_task_is_valid()
{
    if (__taskCtx.header.magicNumber != TASK_MAGIC_NUMBER)
    {
        return false; // Invalid magic number
    }
    if (__taskCtx.header.nextTaskSec == 0)
    {
        return false; // Invalid next task timestamp
    }
    for (size_t i = 0; i < APP_TASK_MAX_ELEM; i++)
    {
        if (__taskCtx.elemList[i].taskId >= TASK_ID_MAX)
        {
            return false; // Invalid task ID in the list
        }
    }
    return true; // All checks passed, task request is valid
}

void app_task_reset()
{
    __taskCtx.header.magicNumber = TASK_MAGIC_NUMBER;
    __taskCtx.header.nextTaskSec = 0; // Reset to 0

    memset(__taskCtx.elemList, 0, sizeof(__taskCtx.elemList));
}

bool app_task_is_in_progress(task_id_t taskId)
{
    for (size_t i = 0; i < APP_TASK_MAX_ELEM; i++)
    {
        if (__taskCtx.elemList[i].taskId == taskId)
        {
            return _taskInProgress[i]; // Return the status of the task
        }
    }
    return false; // Task ID not found
}

bool app_task_is_all_completed()
{
    for (size_t i = 0; i < APP_TASK_MAX_ELEM; i++)
    {
        if (_taskInProgress[i])
        {
            return false; // At least one task is still in progress
        }
    }
    return true; // All tasks are completed
}

uint16_t app_task_get_next_task_sec()
{
    return __taskCtx.header.nextTaskSec; // Return the next task start time in seconds
}

task_request_elem_t *app_task_get(task_id_t taskId)
{
    for (size_t i = 0; i < APP_TASK_MAX_ELEM; i++)
    {
        if (__taskCtx.elemList[i].taskId == taskId)
        {
            return &__taskCtx.elemList[i];
        }
    }
    return NULL;
}
