/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Ground Station
 *
 * @attention
 * Copyright (c) 2026 Geofabrica. All rights reserved.
 *
 * License: MIT License
 *
 * Author: BillyChrist
 *
 * Ground station core interface.
 * ================================================================
 */
/* USER CODE END Header */

#ifndef GROUND_STATION_H
#define GROUND_STATION_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>

void GroundStation_Init(void);
void GroundStation_Run(void);

#ifdef __cplusplus
}
#endif

#endif // GROUND_STATION_H
