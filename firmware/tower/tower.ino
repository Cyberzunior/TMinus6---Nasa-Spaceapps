// T-Minus_6 asteroid tower, firmware v2. Arduino UNO Q #2, microcontroller side. 3.3 V pins.
//   in : F (fire one ball)  A,angle (pan servo)  X (disarm)  R (re-arm)  T,rest,push,ms (tune the pusher)
//   out: K (ball released)
// F is ignored when disarmed or within 1.5 s of the last fire. The three pusher numbers are NOT stored: the laptop
// resends them (T,...) every time it connects. The test button on D2 fires too (and answers K, so the laptop sees it).
// UNTESTED on hardware. Check: the Servo library works on the UNO Q core, and D9 / D10 can drive servos.
#include <Arduino_RouterBridge.h>
#include <Servo.h>
#define FW_VERSION 2
#define HAS_PAN 1                         // 1 once the second SG90 (pan) is fitted

const int PUSH_PIN = 9, PAN_PIN = 10, LED = 13, BTN = 2;
const unsigned long MIN_GAP_MS = 1500;
int restDeg = 20, pushDeg = 100;          // tune: how far the pusher swings to release one ball
unsigned long pushMs = 350;

Servo pusher;
#if HAS_PAN
Servo pan;
#endif
bool armed = true, pushing = false;
unsigned long tPush = 0, tFire = 0, tBtn = 0;
volatile bool pendingF = false, pendingX = false, pendingR = false, pendingA = false, pendingT = false;
volatile int newAngle = 90, tRest = 20, tPushDeg = 100;
volatile long tMs = 350;

void onLine(String s) {                   // sets flags only; loop() does the work
  if (s == "F") pendingF = true;
  else if (s == "X") pendingX = true;
  else if (s == "R") pendingR = true;
  else if (s.startsWith("A,")) { newAngle = constrain(s.substring(2).toInt(), 0, 180); pendingA = true; }
  else if (s.startsWith("T,")) {
    int a = s.indexOf(',', 2), b = s.indexOf(',', a + 1);
    if (a > 0 && b > 0) { tRest = s.substring(2, a).toInt(); tPushDeg = s.substring(a + 1, b).toInt(); tMs = s.substring(b + 1).toInt(); pendingT = true; }
  }
}
void send(const String& s) { Bridge.notify("mcu_line", s); }

void fire(unsigned long now) {
  if (!armed || pushing || (tFire != 0 && now - tFire < MIN_GAP_MS)) return;
  pusher.write(pushDeg); pushing = true; tPush = now; tFire = now;
  send("K");
}
void setup() {
  pinMode(LED, OUTPUT); pinMode(BTN, INPUT_PULLUP);
  pusher.attach(PUSH_PIN); pusher.write(restDeg);
#if HAS_PAN
  pan.attach(PAN_PIN); pan.write(90);
#endif
  Bridge.begin();
  Bridge.provide_safe("line", onLine);
}
void loop() {
  unsigned long now = millis();
  if (pendingT) { pendingT = false; restDeg = constrain(tRest, 0, 180); pushDeg = constrain(tPushDeg, 0, 180); pushMs = constrain(tMs, 100, 1500); if (!pushing) pusher.write(restDeg); }
  if (pendingX) { pendingX = false; armed = false; }
  if (pendingR) { pendingR = false; armed = true; }
#if HAS_PAN
  if (pendingA) { pendingA = false; pan.write(newAngle); }
#else
  pendingA = false;
#endif
  if (pendingF) { pendingF = false; fire(now); }
  if (pushing && now - tPush > pushMs) { pusher.write(restDeg); pushing = false; }
  if (digitalRead(BTN) == LOW && now - tBtn > 500) { tBtn = now; fire(now); }   // test-fire button
  digitalWrite(LED, armed);
}
