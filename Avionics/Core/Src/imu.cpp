/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * Component: WitMotion HWT905-TTL AHRS / IMU sensor
 *
 * WitMotion standard serial protocol @ 9600 baud (factory default).
 * Frame: 0x55 | TYPE | 8 data bytes | checksum
 * ================================================================
 */
/* USER CODE END Header */

#include "imu.h"
#include "main.h"
#include "serial_debug.h"

#include <Arduino.h>

#include <cstdint>
#include <cstring>

// WitMotion HWT905 defaults (see Documentation + WitMotion SDK protocol)
#define HWT905_BAUD 9600
#define HWT905_FRAME_SIZE 11
#define HWT905_HEADER 0x55
#define HWT905_TYPE_ACCEL 0x51
#define HWT905_TYPE_GYRO 0x52
#define HWT905_TYPE_ANGLE 0x53
#define HWT905_TYPE_MAG 0x54

#define HWT905_GRAVITY_MS2 9.80665f
#define HWT905_ACCEL_RANGE_G 16.0f
#define HWT905_GYRO_RANGE_DPS 2000.0f
#define HWT905_ANGLE_RANGE_DEG 180.0f
#define HWT905_INT16_SCALE 32768.0f

#define IMU_VALID_ACCEL 0x01U
#define IMU_VALID_GYRO  0x02U
#define IMU_VALID_ANGLE 0x04U
#define IMU_VALID_MAG   0x08U
#define IMU_VALID_TEMP  0x10U
#define IMU_TELEMETRY_READY_MASK (IMU_VALID_ACCEL | IMU_VALID_ANGLE | IMU_VALID_TEMP)

static HardwareSerial &imu_serial = Serial2;
static bool imu_ready = false;
static uint32_t imu_frame_count = 0;
static uint32_t imu_byte_count = 0;
static bool imu_no_data_warned = false;
static uint8_t rx_frame[HWT905_FRAME_SIZE];
static uint8_t rx_index = 0;

// Hold-last-good merge — telemetry only reads this snapshot, never partial live imuData.
static IMU_Data_t imuTelemetryHold{};
static uint8_t imuTelemetryValid = 0U;

static int16_t IMU_DecodeInt16(uint8_t low, uint8_t high);
static bool IMU_ValidateFrame(const uint8_t *frame);
static void IMU_ParseFrame(const uint8_t *frame);
static void IMU_ProcessByte(uint8_t byte);
static float IMU_ScaleAccel(int16_t raw);
static float IMU_ScaleGyro(int16_t raw);
static float IMU_ScaleAngle(int16_t raw);

IMU_Data_t imuData{};

bool IMU_Init(void)
{
    imuData = {};
    imuTelemetryHold = {};
    imuTelemetryValid = 0U;

    imu_serial.begin(HWT905_BAUD, SERIAL_8N1, HWT905_RX_PIN, HWT905_TX_PIN);
    rx_index = 0;
    imu_ready = true;

    SerialDebug_Print(
        "[IMU] HWT905 ready on UART2 (TX=%d RX=%d @ %d baud)",
        HWT905_TX_PIN,
        HWT905_RX_PIN,
        HWT905_BAUD);

    return imu_ready;
}

void IMU_Update(void)
{
    if (!imu_ready)
    {
        return;
    }

    while (imu_serial.available() > 0)
    {
        imu_byte_count++;
        IMU_ProcessByte(static_cast<uint8_t>(imu_serial.read()));
    }

    if (!imu_no_data_warned && imu_ready && (millis() >= 5000) && imu_frame_count == 0)
    {
        imu_no_data_warned = true;
        SerialDebug_Print(
            "[IMU] no frames yet (bytes=%lu) — power/GND, UART pins TX=%d->sensor RX, RX=%d<-sensor TX, baud=%d",
            static_cast<unsigned long>(imu_byte_count),
            HWT905_TX_PIN,
            HWT905_RX_PIN,
            HWT905_BAUD);
    }
}

uint32_t IMU_GetByteCount(void)
{
    return imu_byte_count;
}

uint32_t IMU_GetFrameCount(void)
{
    return imu_frame_count;
}

bool IMU_IsTelemetryReady(void)
{
    return (imuTelemetryValid & IMU_TELEMETRY_READY_MASK) == IMU_TELEMETRY_READY_MASK;
}

bool IMU_GetTelemetrySnapshot(IMU_Data_t *out)
{
    if (!out)
    {
        return false;
    }

    *out = imuTelemetryHold;
    return IMU_IsTelemetryReady();
}

static int16_t IMU_DecodeInt16(uint8_t low, uint8_t high)
{
    return static_cast<int16_t>((static_cast<uint16_t>(high) << 8) | low);
}

static bool IMU_ValidateFrame(const uint8_t *frame)
{
    if (!frame || frame[0] != HWT905_HEADER)
    {
        return false;
    }

    uint8_t checksum = 0;
    for (int i = 0; i < HWT905_FRAME_SIZE - 1; ++i)
    {
        checksum += frame[i];
    }

    return checksum == frame[HWT905_FRAME_SIZE - 1];
}

static float IMU_ScaleAccel(int16_t raw)
{
    return (static_cast<float>(raw) / HWT905_INT16_SCALE) * HWT905_ACCEL_RANGE_G * HWT905_GRAVITY_MS2;
}

static float IMU_ScaleGyro(int16_t raw)
{
    return (static_cast<float>(raw) / HWT905_INT16_SCALE) * HWT905_GYRO_RANGE_DPS;
}

static float IMU_ScaleAngle(int16_t raw)
{
    return (static_cast<float>(raw) / HWT905_INT16_SCALE) * HWT905_ANGLE_RANGE_DEG;
}

static void IMU_ParseFrame(const uint8_t *frame)
{
    const uint8_t type = frame[1];

    switch (type)
    {
    case HWT905_TYPE_ACCEL:
    {
        const int16_t ax = IMU_DecodeInt16(frame[2], frame[3]);
        const int16_t ay = IMU_DecodeInt16(frame[4], frame[5]);
        const int16_t az = IMU_DecodeInt16(frame[6], frame[7]);
        const int16_t temp_raw = IMU_DecodeInt16(frame[8], frame[9]);

        imuData.accel.x = IMU_ScaleAccel(ax);
        imuData.accel.y = IMU_ScaleAccel(ay);
        imuData.accel.z = IMU_ScaleAccel(az);
        imuData.temperature = static_cast<float>(temp_raw) / 100.0f;

        imuTelemetryHold.accel = imuData.accel;
        imuTelemetryHold.temperature = imuData.temperature;
        imuTelemetryValid |= IMU_VALID_ACCEL | IMU_VALID_TEMP;
        break;
    }

    case HWT905_TYPE_GYRO:
    {
        const int16_t gx = IMU_DecodeInt16(frame[2], frame[3]);
        const int16_t gy = IMU_DecodeInt16(frame[4], frame[5]);
        const int16_t gz = IMU_DecodeInt16(frame[6], frame[7]);

        imuData.gyro.x = IMU_ScaleGyro(gx);
        imuData.gyro.y = IMU_ScaleGyro(gy);
        imuData.gyro.z = IMU_ScaleGyro(gz);

        imuTelemetryHold.gyro = imuData.gyro;
        imuTelemetryValid |= IMU_VALID_GYRO;
        break;
    }

    case HWT905_TYPE_ANGLE:
    {
        const int16_t roll = IMU_DecodeInt16(frame[2], frame[3]);
        const int16_t pitch = IMU_DecodeInt16(frame[4], frame[5]);
        const int16_t yaw = IMU_DecodeInt16(frame[6], frame[7]);

        imuData.roll = IMU_ScaleAngle(roll);
        imuData.pitch = IMU_ScaleAngle(pitch);
        imuData.yaw = IMU_ScaleAngle(yaw);

        imuTelemetryHold.roll = imuData.roll;
        imuTelemetryHold.pitch = imuData.pitch;
        imuTelemetryHold.yaw = imuData.yaw;
        imuTelemetryValid |= IMU_VALID_ANGLE;
        break;
    }

    case HWT905_TYPE_MAG:
    {
        const int16_t hx = IMU_DecodeInt16(frame[2], frame[3]);
        const int16_t hy = IMU_DecodeInt16(frame[4], frame[5]);
        const int16_t hz = IMU_DecodeInt16(frame[6], frame[7]);

        imuData.mag.x = static_cast<float>(hx);
        imuData.mag.y = static_cast<float>(hy);
        imuData.mag.z = static_cast<float>(hz);

        imuTelemetryHold.mag = imuData.mag;
        imuTelemetryValid |= IMU_VALID_MAG;
        break;
    }

    default:
        break;
    }
}

static void IMU_ProcessByte(uint8_t byte)
{
    if (rx_index == 0)
    {
        if (byte != HWT905_HEADER)
        {
            return;
        }

        rx_frame[rx_index++] = byte;
        return;
    }

    rx_frame[rx_index++] = byte;

    if (rx_index < HWT905_FRAME_SIZE)
    {
        return;
    }

    rx_index = 0;

    if (!IMU_ValidateFrame(rx_frame))
    {
        return;
    }

    imu_frame_count++;
    IMU_ParseFrame(rx_frame);
}
