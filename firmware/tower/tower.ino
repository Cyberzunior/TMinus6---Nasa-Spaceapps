// T-Minus_6 asteroid tower, UNO Q #2 (microcontroller side). UNTESTED starting point.
// Lines in: F (fire one ball), X (game over, disarm), R (re-arm), A,angle (only with the pan servo)
// Lines out: K (ball released)
#include <Servo.h>

const int PUSH_PIN = 9, PAN_PIN = 10, LED = 13, BTN = 2;
const int REST_DEG = 20, PUSH_DEG = 100;     // tune: how far the pusher swings to release one ball
const unsigned long PUSH_MS = 350;
#define HAS_PAN 0                            // set to 1 if you add the second servo

Servo pusher;
#if HAS_PAN
Servo pan;
#endif
bool armed = true, pushing = false;
unsigned long tPush = 0, tBtn = 0;
String rx = "";

void fire() {
  if (!armed || pushing) return;
  pusher.write(PUSH_DEG); pushing = true; tPush = millis();
  Serial.println("K");
}
void handleLine(const String& s) {
  if (s == "F") fire();
  else if (s == "X") armed = false;
  else if (s == "R") armed = true;
#if HAS_PAN
  else if (s.startsWith("A,")) pan.write(constrain(s.substring(2).toInt(), 0, 180));
#endif
}
void setup() {
  Serial.begin(115200);
  pinMode(LED, OUTPUT); pinMode(BTN, INPUT_PULLUP);
  pusher.attach(PUSH_PIN); pusher.write(REST_DEG);
#if HAS_PAN
  pan.attach(PAN_PIN); pan.write(90);
#endif
}
void loop() {
  unsigned long now = millis();
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { rx.trim(); if (rx.length()) handleLine(rx); rx = ""; }
    else if (c != '\r' && rx.length() < 24) rx += c;
  }
  if (pushing && now - tPush > PUSH_MS) { pusher.write(REST_DEG); pushing = false; }
  if (digitalRead(BTN) == LOW && now - tBtn > 500) { tBtn = now; fire(); }   // test-fire button
  digitalWrite(LED, armed);
}
