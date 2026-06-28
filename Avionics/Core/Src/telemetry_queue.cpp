#include "telemetry_queue.h"

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

#define TELEMETRY_QUEUE_DEPTH 4U

static QueueHandle_t telemetry_queue = nullptr;

bool TelemetryQueue_Init(void)
{
    if (telemetry_queue != nullptr)
    {
        return true;
    }

    telemetry_queue = xQueueCreate(TELEMETRY_QUEUE_DEPTH, sizeof(TelemetrySample_t));
    return telemetry_queue != nullptr;
}

bool TelemetryQueue_Publish(const TelemetrySample_t *sample)
{
    if (!telemetry_queue || !sample)
    {
        return false;
    }

    if (xQueueSend(telemetry_queue, sample, 0) == pdTRUE)
    {
        return true;
    }

    TelemetrySample_t discard{};
    xQueueReceive(telemetry_queue, &discard, 0);
    return xQueueSend(telemetry_queue, sample, 0) == pdTRUE;
}

bool TelemetryQueue_Receive(TelemetrySample_t *sample, uint32_t timeout_ms)
{
    if (!telemetry_queue || !sample)
    {
        return false;
    }

    const TickType_t ticks = timeout_ms == 0U ? 0 : pdMS_TO_TICKS(timeout_ms);
    return xQueueReceive(telemetry_queue, sample, ticks) == pdTRUE;
}

void TelemetryQueue_DrainToLatest(TelemetrySample_t *latest, bool *has_sample)
{
    if (!telemetry_queue || !latest || !has_sample)
    {
        return;
    }

    TelemetrySample_t incoming{};
    while (TelemetryQueue_Receive(&incoming, 0))
    {
        *latest = incoming;
        *has_sample = true;
    }
}
