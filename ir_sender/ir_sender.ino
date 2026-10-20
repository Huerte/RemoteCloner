/*
  ir_sender.ino  -  transmit half of the IR Swiss Knife firmware

  Role      : replays raw or decoded IR codes received over serial.
  Board     : Uno/Nano (200 raw slots). Use 750 on Mega/ESP32 for AC remotes.
  Library   : IRremote 4.x
  Wiring    : IR LED (via NPN transistor, e.g. 2N2222, + ~100 ohm) -> D3

  Serial protocol (115200 baud, newline terminated commands)
    P                                   -> PONG SENDER
    V                                   -> VER sender 1.0
    S <khz> <count> <v1,v2,...>         -> OK sent | ERR size
    D <protocol> <address> <command> <repeats> -> OK sent
*/

#ifndef RAW_BUFFER_LENGTH
#define RAW_BUFFER_LENGTH 200      // the firmware build overrides this to 750 on Mega
#endif
#define IR_SEND_PIN 3
#include <IRremote.hpp>

static uint16_t sendBuf[RAW_BUFFER_LENGTH];

void sendRawCommand() {
  int khz = Serial.parseInt();
  int n   = Serial.parseInt();
  if (n <= 0 || n > RAW_BUFFER_LENGTH) {
    Serial.println(F("ERR size"));
    return;
  }
  for (int i = 0; i < n; i++) sendBuf[i] = Serial.parseInt();
  IrSender.sendRaw(sendBuf, n, khz);
  Serial.println(F("OK sent"));
}

void sendDecodedCommand() {
  IRData d;
  d.protocol = (decode_type_t)Serial.parseInt();
  d.address  = Serial.parseInt();
  d.command  = Serial.parseInt();
  d.flags    = IRDATA_FLAGS_EMPTY;
  int rep    = Serial.parseInt();
  IrSender.write(&d, rep);
  Serial.println(F("OK sent"));
}

void handleCommand(char c) {
  switch (c) {
    case 'P': Serial.println(F("PONG SENDER")); break;
    case 'V': Serial.println(F("VER sender 1.0")); break;
    case 'S': sendRawCommand(); break;
    case 'D': sendDecodedCommand(); break;
    default: break;   // ignore newlines and unknown bytes
  }
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(300);
  IrSender.begin();
}

void loop() {
  if (Serial.available()) handleCommand(Serial.read());
}
