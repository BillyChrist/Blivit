/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * Core avionics application entry and high-level system control.
 * ================================================================
 */
/* USER CODE END Header */

#ifndef MAIN_H
#define MAIN_H

extern const int RFD900_TX_PIN;
extern const int RFD900_RX_PIN;
extern const int RFD900_CTS_PIN;
extern const int RFD900_RTS_PIN;
extern const int HWT905_TX_PIN;
extern const int HWT905_RX_PIN;
extern const int GPS_SDA_PIN;
extern const int GPS_SCL_PIN;
extern const int HEARTBEAT_LED_PIN;

extern bool debug_mode;

void Blivit_Init(void);
void Blivit_Run(void);

#endif // MAIN_H
