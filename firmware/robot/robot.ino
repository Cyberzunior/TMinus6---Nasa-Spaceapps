// T-Minus_6 robot, firmware v2. Arduino UNO Q #1, microcontroller (STM32) side. 3.3 V pins.
//
// DRV8833 motor drivers, one module per side, A and B channels joined (inputs tied, outputs tied) so each side
// carries two motors. Forward = PWM on IN1 with IN2 low, reverse = PWM on IN2 with IN1 low, stop = both low.
// nSLEEP of both modules goes to 3V3.
//
// Talks to the Linux side through the Arduino Bridge: the Linux program (linux_bridge/robot_bridge.py) calls "line"
// with one protocol line, and this sketch answers with Bridge.notify("mcu_line", line). Protocol: laptop/devio/protocol.py.
//   in : D,left,right,ap   X   R           out: S,angle,cm,flags   B,L / B,R   T,temp,hum (optional)
//   flags bit0 = front stop active (something closer than 8 cm ahead), bit1 = game-over latch active (confirms X)
//
// UNTESTED on hardware. Check before the demo: D3, D5, D6, D9 give PWM (the UNO Q pinout lists PWM on D3 D5 D6 D9 D10 D11),
// and that Bridge.provide_safe / notify behave as described in the current Arduino docs.
#include <Arduino_RouterBridge.h>
#include <AccelStepper.h>
#define FW_VERSION 2
#define HAS_ROBOT_DHT 0                    // 1 = second DHT11 on D10 (robot air)
#if HAS_ROBOT_DHT
#include <DHT.h>
DHT airDht(10, DHT11);
#endif

// ---- pins (do not change without updating docs/pin_map.md)
const int L_IN1 = 3, L_IN2 = 5, R_IN1 = 6, R_IN2 = 9;          // DRV8833, left and right sides
const int TRIG = A0, ECHO = A1, BUMP_L = A2, BUMP_R = A3, LED = 13;   // A0 and A1 are not 5 V tolerant: ECHO goes through 1k + 2k
const int SPEED_CAP = 120;                // 0..255: the motors are fast, keep the robot slow
const unsigned long CMD_TIMEOUT = 300;    // ms without D: stop all four wheels
const unsigned long LINK_LOST = 2000;     // ms without any D: park the turret, blink the LED slowly
const int STOP_CM = 8;                    // anything closer than this ahead: no forward motion
const int SWEEP_LIMIT = 45, SWEEP_STEP = 5;

AccelStepper turret(AccelStepper::HALF4WIRE, 2, 7, 4, 8);      // ULN2003 IN1..IN4 on D2 D4 D7 D8, order IN1 IN3 IN2 IN4
const float STEPS_PER_DEG = 4096.0 / 360.0;

int sweepDeg = -SWEEP_LIMIT, sweepDir = 1;
float frontCm = 400, lastCm = 400;
int cmdL = 0, cmdR = 0;
bool ap = false, latched = false, linkLost = false;
unsigned long tCmd = 0, tScan = 0, tBumpL = 0, tBumpR = 0, tAir = 0, tLatchMsg = 0;
float frontByAngle[19];                   // last reading for -45..45 in steps of 5

// ---- lines from Linux (set variables only; replies come from loop)
volatile bool pendingD = false;
volatile int newL = 0, newR = 0, newAp = 0;
volatile bool pendingX = false, pendingR = false;

void onLine(String s) {                   // runs between two passes of loop() (provide_safe)
  if (s.startsWith("D,")) {
    int a = s.indexOf(',', 2), b = s.indexOf(',', a + 1);
    if (a > 0 && b > 0) { newL = s.substring(2, a).toInt(); newR = s.substring(a + 1, b).toInt(); newAp = s.substring(b + 1).toInt(); pendingD = true; }
  } else if (s == "X") pendingX = true;
  else if (s == "R") pendingR = true;
}
void send(const String& s) { Bridge.notify("mcu_line", s); }

// ---- motors
void setSide(int in1, int in2, int v) {
  v = constrain(v, -255, 255) * SPEED_CAP / 255;
  if (v > 0)      { analogWrite(in1, v);  analogWrite(in2, 0); }
  else if (v < 0) { analogWrite(in1, 0);  analogWrite(in2, -v); }
  else            { analogWrite(in1, 0);  analogWrite(in2, 0); }
}
void drive(int l, int r) {
  if (frontCm < STOP_CM) { if (l > 0) l = 0; if (r > 0) r = 0; }        // hardware safety, always on, even without auto-pilot
  setSide(L_IN1, L_IN2, l);
  setSide(R_IN1, R_IN2, r);
}

// ---- non-blocking HC-SR04 (a small state machine; driving never waits for the echo)
// Polled, not interrupt driven: loop() runs fast, so the error is about 1 to 2 cm. Fine for a 10 cm check and an 8 cm stop.
enum Us { US_IDLE, US_TRIG, US_WAIT_RISE, US_WAIT_FALL } us = US_IDLE;
unsigned long usT0 = 0;
float usCm = 400;
bool usDone = false;
void usStart()  { digitalWrite(TRIG, HIGH); usT0 = micros(); us = US_TRIG; usDone = false; }
void usUpdate() {
  unsigned long t = micros();
  switch (us) {
    case US_TRIG:      if (t - usT0 >= 10) { digitalWrite(TRIG, LOW); usT0 = t; us = US_WAIT_RISE; } break;
    case US_WAIT_RISE: if (digitalRead(ECHO)) { usT0 = t; us = US_WAIT_FALL; }
                       else if (t - usT0 > 4000) { usCm = 400; usDone = true; us = US_IDLE; } break;
    case US_WAIT_FALL: if (!digitalRead(ECHO)) { usCm = (t - usT0) / 58.0; usDone = true; us = US_IDLE; }
                       else if (t - usT0 > 12000) { usCm = 400; usDone = true; us = US_IDLE; } break;     // about 2 m: nothing there
    default: break;
  }
}

void setup() {
  pinMode(L_IN1, OUTPUT); pinMode(L_IN2, OUTPUT); pinMode(R_IN1, OUTPUT); pinMode(R_IN2, OUTPUT);
  pinMode(TRIG, OUTPUT); digitalWrite(TRIG, LOW); pinMode(ECHO, INPUT);
  pinMode(BUMP_L, INPUT_PULLUP); pinMode(BUMP_R, INPUT_PULLUP); pinMode(LED, OUTPUT);
  drive(0, 0);
  for (int i = 0; i < 19; i++) frontByAngle[i] = 400;
  turret.setMaxSpeed(700); turret.setAcceleration(1500);
  turret.setCurrentPosition(0);                         // pointing straight ahead at power-up = zero
  turret.moveTo(sweepDeg * STEPS_PER_DEG);
#if HAS_ROBOT_DHT
  airDht.begin();
#endif
  Bridge.begin();
  Bridge.provide_safe("line", onLine);
  tCmd = millis();
}

void loop() {
  unsigned long now = millis();
  if (pendingD) { pendingD = false; if (!latched) { cmdL = newL; cmdR = newR; ap = newAp; } tCmd = now; }
  if (pendingX) { pendingX = false; latched = true; cmdL = cmdR = 0; }
  if (pendingR) { pendingR = false; latched = false; cmdL = cmdR = 0; sweepDeg = -SWEEP_LIMIT; sweepDir = 1; turret.moveTo(sweepDeg * STEPS_PER_DEG); }

  if (now - tCmd > CMD_TIMEOUT) cmdL = cmdR = 0;                         // laptop or Wi-Fi gone: stop within 300 ms
  linkLost = (now - tCmd > LINK_LOST);
  if (latched || linkLost) { cmdL = cmdR = 0; turret.moveTo(0); }       // game over or link lost: stop, park the stepper
  drive(cmdL, cmdR);
  turret.run();                                                         // never waits for the stepper
  usUpdate();

  if (!latched && !linkLost) {
    if (turret.distanceToGo() == 0 && us == US_IDLE && !usDone && now - tScan >= 60) { tScan = now; usStart(); }
    if (usDone) {
      usDone = false;
      lastCm = usCm;
      frontByAngle[(sweepDeg + 45) / 5] = usCm;
      frontCm = 400;
      for (int a = -15; a <= 15; a += 5) frontCm = min(frontCm, frontByAngle[(a + 45) / 5]);   // the forward cone drives the safety stop
      send("S," + String(sweepDeg) + "," + String((int)min(usCm, 400.0f)) + "," + String(frontCm < STOP_CM ? 1 : 0));
      sweepDeg += SWEEP_STEP * sweepDir;
      if (sweepDeg >= SWEEP_LIMIT) { sweepDeg = SWEEP_LIMIT; sweepDir = -1; }
      if (sweepDeg <= -SWEEP_LIMIT) { sweepDeg = -SWEEP_LIMIT; sweepDir = 1; }
      turret.moveTo(sweepDeg * STEPS_PER_DEG);
    }
  } else if (latched && now - tLatchMsg >= 200) {                       // confirm the latch: S with flags bit1, 5 per second
    tLatchMsg = now;
    send("S,0," + String((int)min(frontCm, 400.0f)) + ",2");
  }

  if (digitalRead(BUMP_L) == LOW && now - tBumpL > 200) { tBumpL = now; send("B,L"); }
  if (digitalRead(BUMP_R) == LOW && now - tBumpR > 200) { tBumpR = now; send("B,R"); }
#if HAS_ROBOT_DHT
  if (now - tAir >= 2000) {                                             // at most once every 2 s (the DHT11 is slow)
    tAir = now;
    float t = airDht.readTemperature(), h = airDht.readHumidity();
    if (!isnan(t) && !isnan(h)) send("T," + String(t, 1) + "," + String((int)h));
  }
#endif
  // status LED: steady = auto-pilot on, fast blink = game over, slow blink = link lost
  if (latched)       digitalWrite(LED, (now / 100) % 2);
  else if (linkLost) digitalWrite(LED, (now / 500) % 2);
  else               digitalWrite(LED, ap);
}
