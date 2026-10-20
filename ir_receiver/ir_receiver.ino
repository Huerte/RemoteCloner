/*
  ir_receiver.ino  -  capture half of the IR Swiss Knife firmware

  Role      : listens for one IR key press and reports it over serial.
  Board     : Uno/Nano (200 raw slots). Use 750 on Mega/ESP32 for AC remotes.
  Library   : IRremote 4.x
  Wiring    : IR receiver (VS1838B / TSOP38238) OUT -> D11

  Serial protocol (115200 baud, newline terminated commands)
    P  -> PONG RECEIVER
    V  -> VER receiver 1.0
    L  -> OK learning       (then one capture is reported)
    C  -> OK cancelled
  Capture output
    DEC <protocol> <name> <address> <command>
    RAW 38 <count> <us,us,us,...>
    ERR overflow
*/

#ifndef RAW_BUFFER_LENGTH
#define RAW_BUFFER_LENGTH 200      // the firmware build overrides this to 750 on Mega
#endif
#define IR_RECEIVE_PIN 11
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
    case 'V': Serial.println(F("VER receiver 1.0")); break;
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
  Serial.begin(115200);
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
