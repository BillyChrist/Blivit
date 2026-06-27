/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * Component: SparkFun u-blox SAM-M8Q GPS Breakout, Qwiic
 *
 * 72-channel GNSS receiver supporting GPS, GLONASS, Galileo,
 * and BeiDou. Requires 3.3 V power and offers UART or I2C access.
 *
 * @attention
 * Copyright (c) 2026 Geofabrica. All rights reserved.
 *
 * License: MIT License
 *
 * Author: BillyChrist
 *
 * GPS sensor module implementation.
 * ================================================================
 */
/* USER CODE END Header */

#include "gps.h"

GPS_Data_t gpsData = {
    .position = {
        .latitude = 0.0,
        .longitude = 0.0,
        .altitude = 0.0f,
        .speed = 0.0f,
        .course = 0.0f,
    },
    .fix = {
        .satellites = 0,
        .hdop = 0.0f,
        .valid = false,
    },
    .utc_time = "",
    .date = "",
    .status = "",
    .mode = "",
};

bool GPS_Init(void)
{
    // TODO: initialize GPS communication and configuration
    return true;
}

void GPS_Update(void)
{
    /*
     * TODO: read GPS data from the receiver and populate gpsData.
     * Example fields:
     *   gpsData.position.latitude
     *   gpsData.position.longitude
     *   gpsData.position.altitude
     *   gpsData.position.speed
     *   gpsData.position.course
     *   gpsData.fix.satellites
     *   gpsData.fix.hdop
     *   gpsData.fix.valid
     *   gpsData.utc_time
     *   gpsData.date
     *   gpsData.status
     *   gpsData.mode
     */
}
