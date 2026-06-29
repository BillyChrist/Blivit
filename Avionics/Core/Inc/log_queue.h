/* FreeRTOS queue — sensor path enqueues CSV rows, LogTask writes to LittleFS. */

#ifndef LOG_QUEUE_H
#define LOG_QUEUE_H

#include "telemetry_sample.h"

#include <cstdint>

bool LogQueue_Init(void);
bool LogQueue_Publish(const TelemetrySample_t *sample);
bool LogQueue_Receive(TelemetrySample_t *sample, uint32_t timeout_ms);
uint32_t LogQueue_GetDroppedCount(void);

#endif // LOG_QUEUE_H
