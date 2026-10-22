/*
  ir_sender.ino  -  transmit half of the IRRemoteCloner firmware

  Role      : replays raw or decoded IR codes received over serial.
  Boards    : AVR (Uno/Nano/Mega/Leonardo/Micro), ESP32 family, ESP8266.
  Library   : IRremote 4.x
  Wiring    : IR LED (via NPN transistor, e.g. 2N2222, + ~100 ohm) -> IR_SEND_PIN
              (D3 on AVR; see app/boards.py for the ESP pins)

  Build-time overrides (-D flags): RAW_BUFFER_LENGTH, IR_SEND_PIN, SERIAL_BAUD, CHIP_NAME

  Serial protocol (SERIAL_BAUD, default 115200, newline terminated commands)
    P                                   -> PONG SENDER
    V                                   -> VER sender 1.1
    I                                   -> INFO fw=1.1 role=sender chip=<chip> buf=<slots> baud=<baud> pin=<pin>
    S <khz> <count> <v1,v2,...>         -> OK sent | ERR size
    D <protocol> <address> <command> <repeats> -> OK sent
*/

#define FW_VERSION "1.1"
#ifndef RAW_BUFFER_LENGTH
#define RAW_BUFFER_LENGTH 200      // the firmware build overrides this (750 on Mega/ESP32, 512 on ESP8266)
#endif
#ifndef IR_SEND_PIN
#define IR_SEND_PIN 3
#endif
#ifndef SERIAL_BAUD
#define SERIAL_BAUD 115200
#endif
#ifndef CHIP_NAME
#define CHIP_NAME unknown
#endif
#define STR_(x) #x
#define STR(x) STR_(x)
#include <IRremote.hpp>

static uint16_t sendBuf[RAW_BUFFER_LENGTH];

void sendRawCommand() {
  int khz = Serial.parseInt();
  int n   = Serial.parseInt();
  if (n <= 0 || n > RAW_BUFFER_LENGTH) {
    Serial.readStringUntil('\n');   // discard the oversized payload so it is not parsed as commands
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
    case 'V': Serial.println(F("VER sender " FW_VERSION)); break;
    case 'I':
      Serial.print(F("INFO fw=" FW_VERSION " role=sender chip=" STR(CHIP_NAME) " buf="));
      Serial.print(RAW_BUFFER_LENGTH);
      Serial.print(F(" baud="));
      Serial.print(SERIAL_BAUD);
      Serial.print(F(" pin="));
      Serial.println(IR_SEND_PIN);
      break;
    case 'S': sendRawCommand(); break;
    case 'D': sendDecodedCommand(); break;
    default: break;   // ignore newlines and unknown bytes
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial.setTimeout(300);
  IrSender.begin();
}

void loop() {
  if (Serial.available()) handleCommand(Serial.read());
}
