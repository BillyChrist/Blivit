#include "tasks.h"

#include "avionics_command.h"
#include "avionics_log.h"
#include "gps.h"
#include "heartbeat.h"
#include "imu.h"
#include "log_queue.h"
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
#define LOG_TASK_STACK 4096U
#define LOG_TASK_PRIORITY 1U
#define SENSOR_LOOP_DELAY_MS 5U

static void SensorTask(void *param);
static void CommsTask(void *param);
static void LogTask(void *param);

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

    xTaskCreatePinnedToCore(
        LogTask,
        "blivit-log",
        LOG_TASK_STACK,
        nullptr,
        LOG_TASK_PRIORITY,
        nullptr,
        SENSOR_TASK_CORE);
}

static void SensorTask(void *param)
{
    (void)param;

    GPS_Init();
    IMU_Init();

    SerialDebug_Print("[TASK] sensor core=%d — GPS I2C + IMU UART (%u ms heartbeat snapshot)",
                      SENSOR_TASK_CORE,
                      static_cast<unsigned>(TELEMETRY_OUTPUT_INTERVAL_MS));

    uint32_t last_publish_ms = 0;
    uint32_t last_logged_gps_updates = 0;

    for (;;)
    {
        GPS_Update();
        IMU_Update();

        const uint32_t now = millis();

        const uint32_t gps_updates = GPS_GetUpdateCount();
        const bool gps_new = gps_updates != last_logged_gps_updates;

        if (AvionicsLog_IsRecording() && gps_new)
        {
            TelemetrySample_t log_sample{};
            if (TelemetrySample_BuildFromSensors(&log_sample))
            {
                log_sample.source_mask = TELEMETRY_SOURCE_GPS;
                log_sample.imu_frame_type = 0U;
                LogQueue_Publish(&log_sample);

                last_logged_gps_updates = gps_updates;
            }
        }

        const bool publish_due = (now - last_publish_ms) >=
            (AvionicsLog_IsDownloading() ? TELEMETRY_DOWNLOAD_INTERVAL_MS
                                         : TELEMETRY_OUTPUT_INTERVAL_MS);

        if (publish_due)
        {
            TelemetrySample_t heartbeat_sample{};
            if (TelemetrySample_BuildFromSensors(&heartbeat_sample))
            {
                heartbeat_sample.source_mask = TELEMETRY_SOURCE_PERIODIC;
                TelemetryQueue_Publish(&heartbeat_sample);
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

        TelemetrySample_t incoming{};
        bool got_new_sample = false;
        TelemetryQueue_DrainToLatest(&incoming, &got_new_sample);

        if (got_new_sample)
        {
            latest = incoming;
            Heartbeat_UpdateFromSample(&latest);

            if (debug_mode)
            {
                telemetry_output();
            }
        }

        if (!debug_mode && !AvionicsLog_IsDownloading())
        {
            RFD900_Process();
        }

        vTaskDelay(pdMS_TO_TICKS(1));
    }
}

static void LogTask(void *param)
{
    (void)param;

    SerialDebug_Print("[TASK] log core=%d — drain queue -> LittleFS CSV", SENSOR_TASK_CORE);

    for (;;)
    {
        TelemetrySample_t sample{};
        if (LogQueue_Receive(&sample, 50U))
        {
            if (AvionicsLog_IsRecording())
            {
                AvionicsLog_Append(&sample);
            }
        }
    }
}
