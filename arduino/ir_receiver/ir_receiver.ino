/*
  ir_receiver.ino  -  capture half of the IRRemoteCloner firmware

  Role      : listens for one IR key press and reports it over serial.
  Boards    : AVR (Uno/Nano/Mega/Leonardo/Micro), ESP32 family, ESP8266.
  Library   : IRremote 4.x
  Wiring    : IR receiver (VS1838B / TSOP38238) OUT -> IR_RECEIVE_PIN (D11 on AVR;
              see app/boards.py for the ESP pins, passed in by tools/build_firmware.py)

  Build-time overrides (-D flags): RAW_BUFFER_LENGTH, IR_RECEIVE_PIN, SERIAL_BAUD, CHIP_NAME

  Serial protocol (SERIAL_BAUD, default 115200, newline terminated commands)
    P  -> PONG RECEIVER
    V  -> VER receiver 1.1
    I  -> INFO fw=1.1 role=receiver chip=<chip> buf=<raw slots> baud=<baud> pin=<pin>
    L  -> OK learning       (then one capture is reported)
    C  -> OK cancelled
  Capture output
    DEC <protocol> <name> <address> <command>
    RAW 38 <count> <us,us,us,...>
    ERR overflow
*/

#define FW_VERSION "1.1"
#ifndef RAW_BUFFER_LENGTH
#define RAW_BUFFER_LENGTH 200      // the firmware build overrides this (750 on Mega/ESP32, 512 on ESP8266)
#endif
#ifndef IR_RECEIVE_PIN
#define IR_RECEIVE_PIN 11
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

static bool learning = false;

void printCapture() {
  IRData &d = IrReceiver.decodedIRData;

  if (d.flags & IRDATA_FLAGS_WAS_OVERFLOW) {
    Serial.println(F("ERR overflow"));
    return;
  }

  Serial.print(F("DEC "));
  Serial.print((int)d.protocol); Serial.print(' ');
  Serial.print(getProtocolString(d.protocol)); Serial.print(' ');
  Serial.print(d.address); Serial.print(' ');
  Serial.println(d.command);

  auto *r = &IrReceiver.irparams;   // rawDataPtr was removed in newer IRremote 4.x
  Serial.print(F("RAW 38 "));
  Serial.print(r->rawlen - 1);
  Serial.print(' ');
  for (uint16_t i = 1; i < r->rawlen; i++) {
    uint32_t us = (uint32_t)r->rawbuf[i] * MICROS_PER_TICK;
    // Receivers stretch marks and shrink spaces; compensate.
    if (i & 1) us = us > MARK_EXCESS_MICROS ? us - MARK_EXCESS_MICROS : us;
    else       us += MARK_EXCESS_MICROS;
    Serial.print(us);
    if (i < r->rawlen - 1) Serial.print(',');
  }
  Serial.println();
}

void handleCommand(char c) {
  switch (c) {
    case 'P': Serial.println(F("PONG RECEIVER")); break;
    case 'V': Serial.println(F("VER receiver " FW_VERSION)); break;
    case 'I':
      Serial.print(F("INFO fw=" FW_VERSION " role=receiver chip=" STR(CHIP_NAME) " buf="));
      Serial.print(RAW_BUFFER_LENGTH);
      Serial.print(F(" baud="));
      Serial.print(SERIAL_BAUD);
      Serial.print(F(" pin="));
      Serial.println(IR_RECEIVE_PIN);
      break;
    case 'L':
      IrReceiver.resume();
      learning = true;
      Serial.println(F("OK learning"));
      break;
    case 'C':
      learning = false;
      Serial.println(F("OK cancelled"));
      break;
    default: break;   // ignore newlines and unknown bytes
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  IrReceiver.begin(IR_RECEIVE_PIN, DISABLE_LED_FEEDBACK);
}

void loop() {
  if (learning && IrReceiver.decode()) {
    if (!(IrReceiver.decodedIRData.flags & IRDATA_FLAGS_IS_REPEAT)) {
      printCapture();
      learning = false;
    }
    IrReceiver.resume();
  }

  if (Serial.available()) handleCommand(Serial.read());
}
