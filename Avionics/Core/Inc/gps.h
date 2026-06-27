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

bool GPS_Init(void);
void GPS_Update(void);

#ifdef __cplusplus
}
#endif

#endif // GPS_H
