/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * Component: ESP32 DevKit V1 (ESP32-WROOM-32)
 *
 * Application entry point, pin map, init/run loop, and Arduino setup/loop.
 * ================================================================
 */
/* USER CODE END Header */

#include "main.h"
#include "gps.h"
#include "heartbeat.h"
#include "imu.h"
#include "rfd900.h"
#include "serial_debug.h"

#include <Arduino.h>

// ===== Runtime mode =====
// true  = bench debug: telemetry over USB serial (no RFD900 traffic)
// false = field mode: telemetry over RFD900 radio to ground station
bool debug_mode = true;

// ===== ESP32 Pinout Schedule =====
const int RFD900_TX_PIN = 25;     // ESP32 TX -> RFD900 RX
const int RFD900_RX_PIN = 26;     // ESP32 RX <- RFD900 TX
const int RFD900_CTS_PIN = 27;    // ESP32 CTS <- RFD900 RTS (if enabled)
const int RFD900_RTS_PIN = 14;    // ESP32 RTS -> RFD900 CTS (if enabled)
const int HWT905_TX_PIN = 17;     // UART2 TX2 -> HWT905 RX
const int HWT905_RX_PIN = 16;     // UART2 RX2 <- HWT905 TX
const int GPS_SDA_PIN = 21;       // I2C SDA for Qwiic GPS
const int GPS_SCL_PIN = 22;       // I2C SCL for Qwiic GPS
const int HEARTBEAT_LED_PIN = 2;  // On-board LED / status indicator

void Blivit_Init(void)
{
    GPS_Init();
    IMU_Init();
    Heartbeat_Init();

    if (debug_mode)
    {
        SerialDebug_Print("[MODE] debug — telemetry on USB serial @ 115200");
    }
    else
    {
        RFD900_Init();
        SerialDebug_Print("[MODE] field — telemetry over RFD900 radio");
    }
}

void Blivit_Run(void)
{
    GPS_Update();
    IMU_Update();
    Heartbeat_Update();

    if (debug_mode)
    {
        telemetry_output();
    }
    else
    {
        RFD900_Process();
    }
}

void setup()
{
    SerialDebug_Init();
    SerialDebug_Print("Blivit avionics boot");
    Blivit_Init();
    SerialDebug_Print("Blivit init complete");
}

void loop()
{
    Blivit_Run();
}
