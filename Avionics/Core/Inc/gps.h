/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * @attention
 * Copyright (c) 2026 Geofabrica. All rights reserved.
 *
 * License: MIT License
 *
 * Author: BillyChrist
 *
 * GPS sensor module interface.
 * ================================================================
 */
/* USER CODE END Header */

#ifndef GPS_H
#define GPS_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>

typedef struct
{
    double latitude;
    double longitude;
    float altitude;
    float speed;
    float course;
} GPS_Position_t;

typedef struct
{
    int satellites;
    float hdop;
    bool valid;
} GPS_Fix_t;

typedef struct
{
    GPS_Position_t position;
    GPS_Fix_t fix;
    char utc_time[16];
    char date[12];
    char status[8];
    char mode[8];
} GPS_Data_t;

extern GPS_Data_t gpsData;

bool GPS_Init(void);
void GPS_Update(void);

#ifdef __cplusplus
}
#endif

#endif // GPS_H
