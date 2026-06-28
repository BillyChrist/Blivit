/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * Component: ESP32 DevKit V1 (ESP32-WROOM-32)
 *
 * ESP32 DevKit V1 is a dual-core Xtensa LX6 controller running up to
 * 240 MHz with 4 MB flash, 2.4 GHz Wi-Fi, Bluetooth 4.2 Classic + BLE,
 * Micro-USB programming/debug, and multiple UART/I2C/SPI interfaces.
 *
 * The system uses separate UARTs for RFD900x and HWT905, plus I2C or
 * UART for the SAM-M8Q GPS module.
 *
 * @attention
 * Copyright (c) 2026 Geofabrica. All rights reserved.
 *
 * License: MIT License
 *
 * Author: BillyChrist
 *
 * Core avionics application entry and control flow.
 * ================================================================
 */
/* USER CODE END Header */

// Includes
#include "blivit_main.h"
#include "heartbeat.h"
#include "rfd900.h"
#include "gps.h"
#include "imu.h"


// ===== ESP32 Pinout Schedule =====
// RFD900x
const int RFD900_TX_PIN     = 25; // ESP32 TX -> RFD900 RX
const int RFD900_RX_PIN     = 26; // ESP32 RX <- RFD900 TX
const int RFD900_CTS_PIN    = 27; // ESP32 CTS <- RFD900 RTS (if enabled)
const int RFD900_RTS_PIN    = 14; // ESP32 RTS -> RFD900 CTS (if enabled)
// IMU
const int HWT905_TX_PIN      = 4; // UART2 TX (GPIO 16 -RX)
const int HWT905_RX_PIN      = 5; // UART2 RX (GPIO 17 -TX)
// GPS
const int GPS_SDA_PIN       = 21; // I2C SDA for Qwiic GPS (GPIO 21)
const int GPS_SCL_PIN       = 22; // I2C SCL for Qwiic GPS (GPIO 22)
// Internal
const int HEARTBEAT_LED_PIN  = 2; // On-board LED / status indicator


// Entry Point
int main(void)
{
    Blivit_Init();

    while (1)
    {
        Blivit_Run();
    }

    return 0;
}

void Blivit_Init(void)
{
    GPS_Init();
    IMU_Init();
    Heartbeat_Init();
    RFD900_Init();
}

void Blivit_Run(void)
{

    // GPS Handling
    GPS_Update();

    // IMU Handling
    IMU_Update();

    // Heartbeat Handling
    Heartbeat_Update();

        // Output Method
            // heartbeat_output();
            debug_output();

    // Coms Handling
    RFD900_Process();



    debug_output();
}


