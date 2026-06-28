/* USER CODE BEGIN Header */
/** FreeRTOS queue — Core 1 publishes, Core 0 consumes (latest wins on overflow). */
/* USER CODE END Header */

#ifndef TELEMETRY_QUEUE_H
#define TELEMETRY_QUEUE_H

#include "telemetry_sample.h"

#include <cstdint>

bool TelemetryQueue_Init(void);
bool TelemetryQueue_Publish(const TelemetrySample_t *sample);
bool TelemetryQueue_Receive(TelemetrySample_t *sample, uint32_t timeout_ms);
void TelemetryQueue_DrainToLatest(TelemetrySample_t *latest, bool *has_sample);

#endif // TELEMETRY_QUEUE_H
