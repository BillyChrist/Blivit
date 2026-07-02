#include "serial_debug.h"

#include <Arduino.h>
#include <cstdarg>
#include <cstdio>

#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

static SemaphoreHandle_t serial_debug_mutex = nullptr;

void SerialDebug_Init(void)
{
    Serial.begin(115200);

    if (serial_debug_mutex == nullptr)
    {
        serial_debug_mutex = xSemaphoreCreateMutex();
    }

    while (!Serial && (millis() < 3000))
    {
        /* wait up to 3 s for USB serial on boot */
    }
}

uint32_t SerialDebug_Millis(void)
{
    return millis();
}

void SerialDebug_Print(const char *fmt, ...)
{
    if (!fmt)
    {
        return;
    }

    char local_buffer[512];

    va_list args;
    va_start(args, fmt);
    vsnprintf(local_buffer, sizeof(local_buffer), fmt, args);
    va_end(args);

    if (serial_debug_mutex != nullptr)
    {
        xSemaphoreTake(serial_debug_mutex, portMAX_DELAY);
    }

    Serial.println(local_buffer);

    if (serial_debug_mutex != nullptr)
    {
        xSemaphoreGive(serial_debug_mutex);
    }
}
