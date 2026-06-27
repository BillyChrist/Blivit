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

extern const int RFD900_TX_PIN;
extern const int RFD900_RX_PIN;
extern const int HWT905_TX_PIN;
extern const int HWT905_RX_PIN;
extern const int GPS_SDA_PIN;
extern const int GPS_SCL_PIN;
extern const int HEARTBEAT_LED_PIN;

void Blivit_Init(void);
void Blivit_Run(void);

#ifdef __cplusplus
}
#endif

#endif // BLIVIT_MAIN_H
