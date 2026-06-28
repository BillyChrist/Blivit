/* USER CODE BEGIN Header */
/** ESP32 entry — dual-core: Core 1 sensors, Core 0 RFD/heartbeat/USB debug. */
/* USER CODE END Header */

#include "main.h"
#include "avionics_log.h"
#include "heartbeat.h"
#include "serial_debug.h"
#include "tasks.h"
#include "telemetry_queue.h"

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

// ===== Runtime mode =====
bool debug_mode = true;
bool debug_binary_telemetry = false;
bool rfd900_hw_flow_control = true;

// ===== ESP32 Pinout Schedule =====
const int RFD900_TX_PIN     = 25;   // ESP32 TX -> RFD900 RX
const int RFD900_RX_PIN     = 26;   // ESP32 RX <- RFD900 TX
const int RFD900_CTS_PIN    = 27;   // ESP32 CTS <- RFD900 RTS
const int RFD900_RTS_PIN    = 14;   // ESP32 RTS -> RFD900 CTS
const int HWT905_TX_PIN     = 17;   // UART2 TX2 -> HWT905 RX
const int HWT905_RX_PIN     = 16;   // UART2 RX2 <- HWT905 TX
const int GPS_SDA_PIN       = 21;   // I2C SDA for Qwiic GPS
const int GPS_SCL_PIN       = 22;   // I2C SCL for Qwiic GPS
const int HEARTBEAT_LED_PIN = 2;    // On-board LED / status indicator

void setup()
{
    SerialDebug_Init();
    SerialDebug_Print("Blivit avionics boot");

    if (!TelemetryQueue_Init())
    {
        SerialDebug_Print("[ERR] telemetry queue init failed");
    }

    Heartbeat_Init();

    if (!AvionicsLog_Init())
    {
        SerialDebug_Print("[WARN] onboard CSV logging unavailable");
    }

    if (debug_mode)
    {
        SerialDebug_Print("[MODE] debug — combined text telemetry on USB @ 115200");
    }
    else
    {
        SerialDebug_Print("[MODE] field — RFD900 @ 57600 (Core 0 comms task)");
    }

    Tasks_Start();
    SerialDebug_Print("Blivit dual-core tasks started");
}

void loop()
{
    vTaskDelay(portMAX_DELAY);
}
