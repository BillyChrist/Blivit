/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * Component: RFD900x US long-range modem
 *
 * Transparent serial link @ 57600 baud (SiK / RFDesign factory default).
 * Blivit application framing documented in README.md and
 * Documentation/esp32_build_and_libraries.md
 * ================================================================
 */
/* USER CODE END Header */

#include "rfd900.h"
#include "heartbeat.h"
#include "main.h"
#include "serial_debug.h"

#include <Arduino.h>

#include <cstdio>
#include <cstring>

#define RFD900_BAUD 57600
#define RFD900_BUFFER_SIZE 256
#define RFD900_HELLO_INTERVAL_MS 2000U
#define RFD900_HELLO_FRAME "Blivit,HELLO,1"

enum class RFD900_LinkState
{
    Init,
    Handshaking,
    Linked,
};

static HardwareSerial &radio_serial = Serial1;
static char rfd900_tx_buffer[RFD900_BUFFER_SIZE];
static char rfd900_line_buffer[RFD900_BUFFER_SIZE];
static size_t rfd900_line_length = 0;

static bool rfd900_ready = false;
static RFD900_LinkState rfd900_link_state = RFD900_LinkState::Init;
static uint32_t rfd900_last_hello_ms = 0;
static uint32_t rfd900_last_telemetry_ms = 0;

static bool RFD900_Write(const char *data);
static bool RFD900_ReadLine(char *line, size_t length);
static void RFD900_PollIncoming(void);
static void RFD900_HandleLine(const char *line);
static bool RFD900_LineIsAck(const char *line);
static void RFD900_SendHello(void);
static bool RFD900_SendHeartbeatTelemetry(void);
static void RFD900_BytesToHex(const uint8_t *data, size_t length, char *out, size_t out_length);

bool RFD900_Init(void)
{
    std::memset(rfd900_tx_buffer, 0, sizeof(rfd900_tx_buffer));
    std::memset(rfd900_line_buffer, 0, sizeof(rfd900_line_buffer));
    rfd900_line_length = 0;
    rfd900_last_hello_ms = 0;
    rfd900_last_telemetry_ms = 0;
    rfd900_link_state = RFD900_LinkState::Handshaking;

    radio_serial.setPins(RFD900_RX_PIN, RFD900_TX_PIN, RFD900_CTS_PIN, RFD900_RTS_PIN);
    radio_serial.begin(RFD900_BAUD, SERIAL_8N1);
    radio_serial.setTimeout(10);

    rfd900_ready = true;

    SerialDebug_Print(
        "[RFD900] ready on UART1 (TX=%d RX=%d @ %d baud, HW flow optional)",
        RFD900_TX_PIN,
        RFD900_RX_PIN,
        RFD900_BAUD);

    RFD900_SendHello();
    rfd900_last_hello_ms = millis();

    return rfd900_ready;
}

bool RFD900_SendFrame(const char *payload)
{
    if (!payload || !rfd900_ready)
    {
        return false;
    }

    int written = std::snprintf(rfd900_tx_buffer, RFD900_BUFFER_SIZE, "%s\r\n", payload);
    if (written <= 0 || written >= RFD900_BUFFER_SIZE)
    {
        return false;
    }

    return RFD900_Write(rfd900_tx_buffer);
}

bool RFD900_ReceiveFrame(char *frame, int length)
{
    if (!frame || length <= 0 || !rfd900_ready)
    {
        return false;
    }

    return RFD900_ReadLine(frame, static_cast<size_t>(length));
}

void RFD900_Process(void)
{
    if (!rfd900_ready)
    {
        return;
    }

    RFD900_PollIncoming();

    const uint32_t now = millis();

    if (rfd900_link_state == RFD900_LinkState::Handshaking)
    {
        if ((now - rfd900_last_hello_ms) >= RFD900_HELLO_INTERVAL_MS)
        {
            RFD900_SendHello();
            rfd900_last_hello_ms = now;
        }
        return;
    }

    if (rfd900_link_state == RFD900_LinkState::Linked &&
        (now - rfd900_last_telemetry_ms) >= TELEMETRY_OUTPUT_INTERVAL_MS)
    {
        if (RFD900_SendHeartbeatTelemetry())
        {
            rfd900_last_telemetry_ms = now;
        }
    }
}

static bool RFD900_Write(const char *data)
{
    if (!data)
    {
        return false;
    }

    const size_t length = std::strlen(data);
    return radio_serial.write(reinterpret_cast<const uint8_t *>(data), length) == length;
}

static bool RFD900_ReadLine(char *line, size_t length)
{
    if (!line || length == 0)
    {
        return false;
    }

    while (radio_serial.available() > 0)
    {
        const char byte = static_cast<char>(radio_serial.read());

        if (byte == '\n')
        {
            rfd900_line_buffer[rfd900_line_length] = '\0';

            if (rfd900_line_length > 0 && rfd900_line_buffer[rfd900_line_length - 1] == '\r')
            {
                rfd900_line_buffer[rfd900_line_length - 1] = '\0';
            }

            std::strncpy(line, rfd900_line_buffer, length);
            line[length - 1] = '\0';

            rfd900_line_length = 0;
            rfd900_line_buffer[0] = '\0';
            return true;
        }

        if (rfd900_line_length < (RFD900_BUFFER_SIZE - 1))
        {
            rfd900_line_buffer[rfd900_line_length++] = byte;
        }
        else
        {
            rfd900_line_length = 0;
        }
    }

    return false;
}

static void RFD900_PollIncoming(void)
{
    char incoming[RFD900_BUFFER_SIZE];

    while (RFD900_ReadLine(incoming, sizeof(incoming)))
    {
        RFD900_HandleLine(incoming);
    }
}

static bool RFD900_LineIsAck(const char *line)
{
    if (!line || line[0] == '\0')
    {
        return false;
    }

    if (std::strcmp(line, "ACK") == 0)
    {
        return true;
    }

    if (std::strncmp(line, "ACK,", 4) == 0)
    {
        return true;
    }

    if (std::strstr(line, "Blivit,READY") != nullptr)
    {
        return true;
    }

    return false;
}

static void RFD900_HandleLine(const char *line)
{
    if (!line || line[0] == '\0')
    {
        return;
    }

    if (RFD900_LineIsAck(line))
    {
        if (rfd900_link_state == RFD900_LinkState::Handshaking)
        {
            rfd900_link_state = RFD900_LinkState::Linked;
            rfd900_last_telemetry_ms = millis();
            SerialDebug_Print("[RFD900] link established (%s)", line);
        }
        return;
    }

    if (std::strcmp(line, "PING") == 0)
    {
        RFD900_SendFrame("ACK");
        return;
    }

    if (std::strncmp(line, "Blivit,HELLO,", 13) == 0)
    {
        RFD900_SendFrame("Blivit,READY");
        return;
    }

    if (std::strncmp(line, "TELEMETRY,", 10) == 0)
    {
        unsigned int remote_seq = 0;
        if (std::sscanf(line, "TELEMETRY,%u", &remote_seq) == 1)
        {
            char ack_frame[32];
            std::snprintf(ack_frame, sizeof(ack_frame), "ACK,%u", remote_seq);
            RFD900_SendFrame(ack_frame);
        }
    }
}

static void RFD900_SendHello(void)
{
    RFD900_SendFrame(RFD900_HELLO_FRAME);
}

static void RFD900_BytesToHex(const uint8_t *data, size_t length, char *out, size_t out_length)
{
    if (!data || !out || out_length == 0)
    {
        return;
    }

    size_t write_index = 0;
    for (size_t i = 0; i < length; ++i)
    {
        if ((write_index + 3) > out_length)
        {
            break;
        }

        std::snprintf(out + write_index, out_length - write_index, "%02X", data[i]);
        write_index += 2;
    }

    out[write_index] = '\0';
}

static bool RFD900_SendHeartbeatTelemetry(void)
{
    Heartbeat_CaptureSnapshot();

    uint8_t packet[HEARTBEAT_PACKET_SIZE];
    size_t packet_length = 0;

    if (!Heartbeat_BuildPacket(packet, sizeof(packet), &packet_length))
    {
        return false;
    }

    char hex_payload[(HEARTBEAT_PACKET_SIZE * 2) + 1];
    RFD900_BytesToHex(packet, packet_length, hex_payload, sizeof(hex_payload));

    char frame[RFD900_BUFFER_SIZE];
    std::snprintf(
        frame,
        sizeof(frame),
        "TELEMETRY,%u,%s,%04X",
        heartbeatPacket.sequence,
        hex_payload,
        heartbeatPacket.crc);

    return RFD900_SendFrame(frame);
}
