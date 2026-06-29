#include "log_queue.h"

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

#define LOG_QUEUE_DEPTH 128U

static QueueHandle_t log_queue = nullptr;
static uint32_t log_queue_dropped = 0;

bool LogQueue_Init(void)
{
    if (log_queue != nullptr)
    {
        return true;
    }

    log_queue = xQueueCreate(LOG_QUEUE_DEPTH, sizeof(TelemetrySample_t));
    return log_queue != nullptr;
}

bool LogQueue_Publish(const TelemetrySample_t *sample)
{
    if (!log_queue || !sample)
    {
        return false;
    }

    if (xQueueSend(log_queue, sample, 0) == pdTRUE)
    {
        return true;
    }

    TelemetrySample_t discard{};
    if (xQueueReceive(log_queue, &discard, 0) == pdTRUE)
    {
        log_queue_dropped++;
        return xQueueSend(log_queue, sample, 0) == pdTRUE;
    }

    log_queue_dropped++;
    return false;
}

uint32_t LogQueue_GetDroppedCount(void)
{
    return log_queue_dropped;
}

bool LogQueue_Receive(TelemetrySample_t *sample, uint32_t timeout_ms)
{
    if (!log_queue || !sample)
    {
        return false;
    }

    const TickType_t ticks = timeout_ms == 0U ? 0 : pdMS_TO_TICKS(timeout_ms);
    return xQueueReceive(log_queue, sample, ticks) == pdTRUE;
}
