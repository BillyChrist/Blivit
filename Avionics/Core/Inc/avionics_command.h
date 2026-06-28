#ifndef AVIONICS_COMMAND_H
#define AVIONICS_COMMAND_H

void Blivit_SendLine(const char *line);
bool AvionicsCommand_HandleLine(const char *line);
void AvionicsCommand_PollUsb(void);
void AvionicsCommand_Tick(void);

#endif // AVIONICS_COMMAND_H
