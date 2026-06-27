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

#include "blivit_main.h"
#include "heartbeat.h"
#include "rfd900.h"
#include "gps.h"
#include "imu.h"

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
    GPS_Update();
    IMU_Update();
    Heartbeat_Update();
    RFD900_Process();
}


