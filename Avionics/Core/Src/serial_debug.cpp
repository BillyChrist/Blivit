#include "serial_debug.h"

#include <Arduino.h>
#include <cstdarg>
#include <cstdio>

static char serial_debug_buffer[512];

void SerialDebug_Init(void)
{
    Serial.begin(115200);
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

    va_list args;
    va_start(args, fmt);
    vsnprintf(serial_debug_buffer, sizeof(serial_debug_buffer), fmt, args);
    va_end(args);

    Serial.println(serial_debug_buffer);
}
