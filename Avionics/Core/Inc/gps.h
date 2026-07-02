/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * GPS sensor module interface.
 * ================================================================
 */
/* USER CODE END Header */

#ifndef GPS_H
#define GPS_H

#include <stdint.h>

typedef struct
{
    double latitude;
    double longitude;
    float altitude;
    float speed;
    float course;
    float vel_n;
    float vel_e;
    float vel_d;
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
bool GPS_IsReady(void);
uint32_t GPS_GetUpdateCount(void);
void GPS_CopyData(GPS_Data_t *out);
const GPS_Data_t *GPS_GetData(void);

#endif // GPS_H
