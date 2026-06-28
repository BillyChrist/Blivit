/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * USB serial debug output.
 * ================================================================
 */
/* USER CODE END Header */

#ifndef SERIAL_DEBUG_H
#define SERIAL_DEBUG_H

#include <cstdint>

void SerialDebug_Init(void);
uint32_t SerialDebug_Millis(void);
void SerialDebug_Print(const char *fmt, ...);

#endif // SERIAL_DEBUG_H
