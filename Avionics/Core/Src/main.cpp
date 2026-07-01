/* USER CODE BEGIN Header */
/** ESP32 entry — dual-core: Core 1 sensors, Core 0 RFD/heartbeat/USB debug. */
/* USER CODE END Header */

#include "main.h"
#include "avionics_log.h"
#include "heartbeat.h"
#include "log_queue.h"
#include "serial_debug.h"
#include "tasks.h"
#include "telemetry_queue.h"

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

// ===== Runtime mode =====
bool debug_mode = false;
bool debug_message = false;
bool debug_binary_telemetry = true;
bool rfd900_hw_flow_control = true;

// ===== ESP32 GPIO pinout (numbers below are ESP32 GPIO, not RFD900 pin names) =====
// RFD900 UART: cross TX/RX. Hardware flow control: cross RTS↔CTS (SiK / RS-232 style).
const int RFD900_TX_PIN     = 25;   // GPIO25  ESP32 UART TX   ->  RFD900 RX
const int RFD900_RX_PIN     = 26;   // GPIO26  ESP32 UART RX   <-  RFD900 TX
const int RFD900_CTS_PIN    = 27;   // GPIO27  ESP32 UART CTS (input)   <-  RFD900 RTS
const int RFD900_RTS_PIN    = 14;   // GPIO14  ESP32 UART RTS (output)  ->  RFD900 CTS
const int HWT905_TX_PIN     = 17;   // GPIO17  ESP32 UART2 TX  ->  HWT905 RX
const int HWT905_RX_PIN     = 16;   // GPIO16  ESP32 UART2 RX  <-  HWT905 TX
const int GPS_SDA_PIN       = 21;   // GPIO21  I2C SDA  <->  Qwiic GPS
const int GPS_SCL_PIN       = 22;   // GPIO22  I2C SCL  <->  Qwiic GPS
const int HEARTBEAT_LED_PIN = 2;    // GPIO2   On-board status LED

void setup()
{
    SerialDebug_Init();
    SerialDebug_Print("Blivit avionics boot");

    if (!TelemetryQueue_Init())
    {
        SerialDebug_Print("[ERR] telemetry queue init failed");
    }

    if (!LogQueue_Init())
    {
        SerialDebug_Print("[ERR] log queue init failed");
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
