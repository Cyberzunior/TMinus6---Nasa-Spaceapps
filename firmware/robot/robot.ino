// T-Minus_6 robot, UNO Q #1 (microcontroller side). UNTESTED starting point.
// Talks in text lines over Serial (USB-C cable fallback). For Wi-Fi, a small program on the
// Linux side must pass the laptop's lines to this Serial/Bridge. Check on day one.
// UNO Q pins are 3.3 V. ECHO must go through the 1k + 2k divider.
#include <AccelStepper.h>

const int TRIG = A0, ECHO = A1, BUMP_L = A2, BUMP_R = A3, LED = 13;
const int PWMA = 5, AIN1 = 4, AIN2 = 2, PWMB = 6, BIN1 = 7, BIN2 = 8;   // TB6612
const int SPEED_CAP = 120;              // 0..255: the TT motors are fast, keep the robot slow
const unsigned long CMD_TIMEOUT = 300;  // ms without commands -> stop
const int STOP_CM = 8;                  // anything closer than this ahead: no forward motion

AccelStepper turret(AccelStepper::HALF4WIRE, 9, 11, 10, 12);   // IN1, IN3, IN2, IN4
const float STEPS_PER_DEG = 4096.0 / 360.0;
int sweepDeg = -45, sweepDir = 1;
float frontCm = 400;
int cmdL = 0, cmdR = 0;
bool ap = false, latched = false;
unsigned long tCmd = 0, tLed = 0, tBumpL = 0, tBumpR = 0;
String rx = "";

void setMotor(int pwm, int in1, int in2, int v) {
  v = constrain(v, -255, 255) * SPEED_CAP / 255;
  digitalWrite(in1, v > 0); digitalWrite(in2, v < 0);
  analogWrite(pwm, abs(v));
}
void drive(int l, int r) {
  if (frontCm < STOP_CM) { if (l > 0) l = 0; if (r > 0) r = 0; }   // hardware safety, always on
  setMotor(PWMA, AIN1, AIN2, l);
  setMotor(PWMB, BIN1, BIN2, r);
}
float ping() {
  digitalWrite(TRIG, LOW); delayMicroseconds(2);
  digitalWrite(TRIG, HIGH); delayMicroseconds(10); digitalWrite(TRIG, LOW);
  unsigned long d = pulseIn(ECHO, HIGH, 12000);        // about 2 m max, blocks up to 12 ms
  return d == 0 ? 400 : d / 58.0;
}
void handleLine(const String& s) {
  if (s.startsWith("D,")) {
    int a = s.indexOf(',', 2), b = s.indexOf(',', a + 1);
    if (a > 0 && b > 0 && !latched) {
      cmdL = s.substring(2, a).toInt(); cmdR = s.substring(a + 1, b).toInt();
      ap = s.substring(b + 1).toInt(); tCmd = millis();
    }
  } else if (s == "X") { latched = true; cmdL = cmdR = 0; }
  else if (s == "R") { latched = false; cmdL = cmdR = 0; }
}
void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { rx.trim(); if (rx.length()) handleLine(rx); rx = ""; }
    else if (c != '\r' && rx.length() < 40) rx += c;
  }
}
void setup() {
  Serial.begin(115200);
  pinMode(TRIG, OUTPUT); pinMode(ECHO, INPUT);
  pinMode(BUMP_L, INPUT_PULLUP); pinMode(BUMP_R, INPUT_PULLUP); pinMode(LED, OUTPUT);
  pinMode(AIN1, OUTPUT); pinMode(AIN2, OUTPUT); pinMode(BIN1, OUTPUT); pinMode(BIN2, OUTPUT);
  pinMode(PWMA, OUTPUT); pinMode(PWMB, OUTPUT);
  turret.setMaxSpeed(500); turret.setAcceleration(400);
  turret.setCurrentPosition(0);                         // pointing straight ahead at power-up = zero
  turret.moveTo(sweepDeg * STEPS_PER_DEG);
}
void loop() {
  unsigned long now = millis();
  readSerial();
  if (now - tCmd > CMD_TIMEOUT) { cmdL = cmdR = 0; }    // link lost -> stop
  if (latched) { cmdL = cmdR = 0; turret.moveTo(0); }   // game over: stop, park the stepper
  drive(cmdL, cmdR);

  turret.run();                                         // never wait for the stepper
  if (!latched && turret.distanceToGo() == 0) {         // reached an angle: read and send
    float cm = ping();
    if (abs(sweepDeg) <= 15) frontCm = cm;              // the forward cone drives the safety stop
    Serial.print("S,"); Serial.print(sweepDeg); Serial.print(','); Serial.print(cm, 0);
    Serial.print(','); Serial.println(frontCm < STOP_CM ? 1 : 0);
    sweepDeg += 5 * sweepDir;
    if (sweepDeg >= 45) sweepDir = -1;
    if (sweepDeg <= -45) sweepDir = 1;
    turret.moveTo(sweepDeg * STEPS_PER_DEG);
  }
  if (digitalRead(BUMP_L) == LOW && now - tBumpL > 200) { tBumpL = now; Serial.println("B,L"); }
  if (digitalRead(BUMP_R) == LOW && now - tBumpR > 200) { tBumpR = now; Serial.println("B,R"); }
  // status LED: steady = auto-pilot on, fast blink = game over
  if (latched) digitalWrite(LED, (now / 100) % 2); else digitalWrite(LED, ap);
}
