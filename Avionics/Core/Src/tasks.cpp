#include "tasks.h"

#include "avionics_command.h"
#include "avionics_log.h"
#include "gps.h"
#include "heartbeat.h"
#include "imu.h"
#include "main.h"
#include "rfd900.h"
#include "serial_debug.h"
#include "telemetry_queue.h"
#include "telemetry_sample.h"

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#define SENSOR_TASK_CORE 1
#define COMMS_TASK_CORE 0
#define SENSOR_TASK_STACK 6144U
#define COMMS_TASK_STACK 6144U
#define SENSOR_TASK_PRIORITY 2U
#define COMMS_TASK_PRIORITY 2U
#define SENSOR_LOOP_DELAY_MS 5U

static void SensorTask(void *param);
static void CommsTask(void *param);

void Tasks_Start(void)
{
    xTaskCreatePinnedToCore(
        SensorTask,
        "blivit-sensors",
        SENSOR_TASK_STACK,
        nullptr,
        SENSOR_TASK_PRIORITY,
        nullptr,
        SENSOR_TASK_CORE);

    xTaskCreatePinnedToCore(
        CommsTask,
        "blivit-comms",
        COMMS_TASK_STACK,
        nullptr,
        COMMS_TASK_PRIORITY,
        nullptr,
        COMMS_TASK_CORE);
}

static void SensorTask(void *param)
{
    (void)param;

    GPS_Init();
    IMU_Init();

    SerialDebug_Print("[TASK] sensor core=%d — GPS I2C + IMU UART (high-fidelity log + %u ms telemetry queue)",
                      SENSOR_TASK_CORE,
                      static_cast<unsigned>(TELEMETRY_OUTPUT_INTERVAL_MS));

    TelemetrySample_t sample{};
    uint32_t last_publish_ms = 0;

    for (;;)
    {
        GPS_Update();
        IMU_Update();

        const uint32_t now = millis();
        const bool publish_due = (now - last_publish_ms) >= TELEMETRY_OUTPUT_INTERVAL_MS;
        const bool need_sample = AvionicsLog_IsRecording() || publish_due;

        if (need_sample && TelemetrySample_BuildFromSensors(&sample))
        {
            if (AvionicsLog_IsRecording())
            {
                AvionicsLog_Append(&sample);
            }

            if (publish_due)
            {
                TelemetryQueue_Publish(&sample);
                last_publish_ms = now;
            }
        }

        vTaskDelay(pdMS_TO_TICKS(SENSOR_LOOP_DELAY_MS));
    }
}

static void CommsTask(void *param)
{
    (void)param;

    if (!debug_mode)
    {
        RFD900_Init();
    }

    SerialDebug_Print(
        "[TASK] comms core=%d — %s",
        COMMS_TASK_CORE,
        debug_mode ? "USB debug telemetry" : "RFD900 + heartbeat");

    TelemetrySample_t latest{};
    bool has_sample = false;

    for (;;)
    {
        if (debug_mode)
        {
            AvionicsCommand_PollUsb();
        }

        AvionicsCommand_Tick();

        if (!debug_mode)
        {
            RFD900_PollIncoming();
        }

        TelemetryQueue_DrainToLatest(&latest, &has_sample);

        if (has_sample && !AvionicsLog_IsDownloading())
        {
            Heartbeat_UpdateFromSample(&latest);

            if (debug_mode)
            {
                telemetry_output();
            }
            else
            {
                RFD900_Process();
            }
        }

        vTaskDelay(pdMS_TO_TICKS(1));
    }
}
