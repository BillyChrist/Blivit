/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * Component: SparkFun u-blox SAM-M8Q GPS Breakout, Qwiic
 *
 * 72-channel GNSS receiver supporting GPS, GLONASS, Galileo,
 * and BeiDou. Requires 3.3 V power and offers I2C access via Qwiic.
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
#include "main.h"
#include "serial_debug.h"

#include <Arduino.h>
#include <SparkFun_u-blox_GNSS_Arduino_Library.h>
#include <Wire.h>

#include <cstdio>
#include <cstring>
#include <cstdint>

static SFE_UBLOX_GNSS gnss;

typedef struct
{
    double latitude;
    double longitude;
    float altitude_m;
    float speed_mps;
    float course_deg;
    float vel_n_mps;
    float vel_e_mps;
    float vel_d_mps;
    int satellites;
    float hdop;
    bool fix_valid;
    uint8_t fix_type;
    uint16_t year;
    uint8_t month;
    uint8_t day;
    uint8_t hour;
    uint8_t minute;
    uint8_t second;
} GPS_Reading_t;

static bool gps_connected = false;
static uint32_t last_gps_retry_ms = 0;
static uint32_t last_gps_rx_ms = 0;
static uint32_t gps_update_count = 0;
static uint32_t last_pvt_itow_ms = UINT32_MAX;

#define GPS_RETRY_INTERVAL_MS 5000U
#define GPS_I2C_STALE_MS 15000U

static bool GPS_ConfigureModule(void);
static bool GPS_TryConnect(void);
static void GPS_MarkDisconnected(const char *reason);
static bool GPS_ReadModule(GPS_Reading_t *reading);
static void GPS_ApplyReading(const GPS_Reading_t *reading);
static void GPS_FormatStatusStrings(const GPS_Reading_t *reading);

GPS_Data_t gpsData{};

bool GPS_Init(void)
{
    gpsData = {};
    strncpy(gpsData.status, "NOFIX", sizeof(gpsData.status));
    strncpy(gpsData.mode, "NONE", sizeof(gpsData.mode));

    last_gps_retry_ms = millis();
    gps_connected = GPS_TryConnect();
    if (!gps_connected)
    {
        SerialDebug_Print(
            "[GPS] init failed — check Qwiic wiring (SDA=%d SCL=%d); retrying every %u s",
            GPS_SDA_PIN,
            GPS_SCL_PIN,
            GPS_RETRY_INTERVAL_MS / 1000U);
        return false;
    }

    SerialDebug_Print("[GPS] SAM-M8Q ready on I2C (SDA=%d SCL=%d @ 100kHz)", GPS_SDA_PIN, GPS_SCL_PIN);
    return true;
}

void GPS_Update(void)
{
    if (!gps_connected)
    {
        const uint32_t now = millis();
        if ((now - last_gps_retry_ms) < GPS_RETRY_INTERVAL_MS)
        {
            return;
        }

        last_gps_retry_ms = now;
        gps_connected = GPS_TryConnect();
        if (!gps_connected)
        {
            return;
        }

        SerialDebug_Print("[GPS] SAM-M8Q connected on I2C retry (SDA=%d SCL=%d @ 100kHz)", GPS_SDA_PIN, GPS_SCL_PIN);
    }

    const uint32_t now = millis();
    if (gnss.checkUblox())
    {
        last_gps_rx_ms = now;
    }

    if (!gnss.getPVT())
    {
        if ((now - last_gps_rx_ms) >= GPS_I2C_STALE_MS)
        {
            GPS_MarkDisconnected("no UBX NAV-PVT for 15 s — reconnecting");
        }
        return;
    }

    const uint32_t pvt_itow_ms = gnss.getTimeOfWeek();
    if (pvt_itow_ms == last_pvt_itow_ms)
    {
        return;
    }
    last_pvt_itow_ms = pvt_itow_ms;

    GPS_Reading_t reading{};
    if (!GPS_ReadModule(&reading))
    {
        return;
    }

    GPS_ApplyReading(&reading);
    GPS_FormatStatusStrings(&reading);
    gps_update_count++;

    // Periodic GPS diagnostic if debug_message enabled
    if (debug_message)
    {
        static uint32_t last_gps_debug_ms = 0;
        const uint32_t debug_now = millis();
        if ((debug_now - last_gps_debug_ms) >= 1000U)
        {
            last_gps_debug_ms = debug_now;
            SerialDebug_Print(
                "[GPSDBG] ready=%d update=%lu fix_valid=%d fix_type=%u sats=%d hdop=%.1f lat=%.6f lon=%.6f utc=%02u:%02u:%02u date=%04u-%02u-%02u",
                GPS_IsReady() ? 1 : 0,
                static_cast<unsigned long>(gps_update_count),
                reading.fix_valid ? 1 : 0,
                reading.fix_type,
                reading.satellites,
                reading.hdop,
                reading.latitude,
                reading.longitude,
                reading.hour,
                reading.minute,
                reading.second,
                reading.year,
                reading.month,
                reading.day);
        }
    }
}

uint32_t GPS_GetUpdateCount(void)
{
    return gps_update_count;
}

bool GPS_IsReady(void)
{
    return gps_connected;
}

const GPS_Data_t *GPS_GetData(void)
{
    return &gpsData;
}

static bool GPS_ConfigureModule(void)
{
    bool ok = true;

    if (!gnss.setPortInput(COM_PORT_I2C, COM_TYPE_UBX))
    {
        SerialDebug_Print("[GPS] config failed: setPortInput I2C UBX");
        ok = false;
    }

    if (!gnss.setI2COutput(COM_TYPE_UBX))
    {
        SerialDebug_Print("[GPS] config failed: setI2COutput UBX");
        ok = false;
    }

    if (!gnss.setAutoPVT(true, true, 500))
    {
        SerialDebug_Print("[GPS] config failed: setAutoPVT");
        ok = false;
    }

    if (!gnss.setMeasurementRate(250))
    {
        SerialDebug_Print("[GPS] config failed: setMeasurementRate 250 ms");
        ok = false;
    }

    return ok;
}

static bool GPS_TryConnect(void)
{
    Wire.begin(GPS_SDA_PIN, GPS_SCL_PIN);
    Wire.setClock(100000);

    if (!gnss.begin(Wire, 0x42, 500))
    {
        return false;
    }

    if (!GPS_ConfigureModule())
    {
        SerialDebug_Print("[GPS] module responded on I2C but configuration failed");
        return false;
    }

    last_gps_rx_ms = millis();
    last_pvt_itow_ms = UINT32_MAX;
    return true;
}

static void GPS_MarkDisconnected(const char *reason)
{
    gps_connected = false;
    last_gps_retry_ms = millis();
    if (reason && reason[0] != '\0')
    {
        SerialDebug_Print("[GPS] %s", reason);
    }
}

static bool GPS_ReadModule(GPS_Reading_t *reading)
{
    if (!reading || !gps_connected)
    {
        return false;
    }

    reading->latitude = gnss.getLatitude() / 10000000.0;
    reading->longitude = gnss.getLongitude() / 10000000.0;
    reading->altitude_m = gnss.getAltitudeMSL() / 1000.0f;
    reading->speed_mps = gnss.getGroundSpeed() / 1000.0f;
    reading->course_deg = gnss.getHeading() / 100000.0f;
    reading->vel_n_mps = gnss.getNedNorthVel() / 1000.0f;
    reading->vel_e_mps = gnss.getNedEastVel() / 1000.0f;
    reading->vel_d_mps = gnss.getNedDownVel() / 1000.0f;
    reading->satellites = gnss.getSIV();
    reading->hdop = gnss.getHorizontalDOP() / 100.0f;
    reading->fix_type = gnss.getFixType();
    reading->fix_valid = gnss.getGnssFixOk() && reading->fix_type >= 2;
    reading->year = gnss.getYear();
    reading->month = gnss.getMonth();
    reading->day = gnss.getDay();
    reading->hour = gnss.getHour();
    reading->minute = gnss.getMinute();
    reading->second = gnss.getSecond();

    return true;
}

static void GPS_ApplyReading(const GPS_Reading_t *reading)
{
    if (!reading)
    {
        return;
    }

    if (reading->fix_valid)
    {
        gpsData.position.latitude = reading->latitude;
        gpsData.position.longitude = reading->longitude;
        gpsData.position.altitude = reading->altitude_m;
        gpsData.position.speed = reading->speed_mps;
        gpsData.position.course = reading->course_deg;
        gpsData.position.vel_n = reading->vel_n_mps;
        gpsData.position.vel_e = reading->vel_e_mps;
        gpsData.position.vel_d = reading->vel_d_mps;
    }

    gpsData.fix.satellites = reading->satellites;
    gpsData.fix.hdop = reading->hdop;
    gpsData.fix.valid = reading->fix_valid;

    if (reading->fix_valid)
    {
        snprintf(
            gpsData.utc_time,
            sizeof(gpsData.utc_time),
            "%02u:%02u:%02u",
            reading->hour,
            reading->minute,
            reading->second);

        snprintf(
            gpsData.date,
            sizeof(gpsData.date),
            "%04u-%02u-%02u",
            reading->year,
            reading->month,
            reading->day);
    }
    else
    {
        gpsData.utc_time[0] = '\0';
        gpsData.date[0] = '\0';
    }
}

static void GPS_FormatStatusStrings(const GPS_Reading_t *reading)
{
    if (!reading)
    {
        return;
    }

    if (reading->fix_valid)
    {
        strncpy(gpsData.status, "FIX", sizeof(gpsData.status));
    }
    else if (reading->satellites > 0)
    {
        strncpy(gpsData.status, "ACQ", sizeof(gpsData.status));
    }
    else
    {
        strncpy(gpsData.status, "NOFIX", sizeof(gpsData.status));
    }
    gpsData.status[sizeof(gpsData.status) - 1] = '\0';

    switch (reading->fix_type)
    {
    case 3:
    case 4:
        strncpy(gpsData.mode, "3D", sizeof(gpsData.mode));
        break;
    case 2:
        strncpy(gpsData.mode, "2D", sizeof(gpsData.mode));
        break;
    case 1:
        strncpy(gpsData.mode, "DR", sizeof(gpsData.mode));
        break;
    case 5:
        strncpy(gpsData.mode, "TIME", sizeof(gpsData.mode));
        break;
    default:
        strncpy(gpsData.mode, "NONE", sizeof(gpsData.mode));
        break;
    }
    gpsData.mode[sizeof(gpsData.mode) - 1] = '\0';
}
