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
 * Core avionics application entry and high-level system control.
 * ================================================================
 */
/* USER CODE END Header */

#ifndef BLIVIT_MAIN_H
#define BLIVIT_MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>

void Blivit_Init(void);
void Blivit_Run(void);

#ifdef __cplusplus
}
#endif

#endif // BLIVIT_MAIN_H
