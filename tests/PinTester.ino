/*
  PinTester - checks every wire of T-Minus_6 one command at a time (115200 baud, text lines).
  Upload to the board you want to test INSTEAD of its normal sketch, then use the
  "Wiring (pin tester)" tab of tests/run_tester.py. Protocol: tests/tminus6_test/protocol.py.

  Needs only built-in libraries: Wire, Servo, LiquidCrystal.
  Set USE_LCD_I2C to 1 to also use the LiquidCrystal_I2C library (LCDI2C command).
*/
#include <Wire.h>
#include <Servo.h>
#include <LiquidCrystal.h>

#define USE_LCD_I2C 0
#if USE_LCD_I2C
#include <LiquidCrystal_I2C.h>
#endif

#define VERSION "1.0"
#if defined(ARDUINO_AVR_UNO)
#define BOARD_NAME "UNO_R3"
#elif defined(ARDUINO_UNOR4_WIFI) || defined(ARDUINO_UNO_Q) || defined(ARDUINO_ARCH_ZEPHYR)
#define BOARD_NAME "UNO_Q"
#else
#define BOARD_NAME "OTHER"
#endif

#define MAXP 24            // pin numbers 0..23 are tracked
#define LINE_MAX 96
#define NBLINK 4
#define NSERVO 4
#define NMOTOR 2
#define DEBOUNCE_MS 20

char line[LINE_MAX];
uint8_t lineLen = 0;
char *v[8];                // tokens of the current command
uint8_t argc;

// ---------------------------------------------------------------- state
struct Blink { int8_t pin; bool lvl; unsigned long half, next, end; } blinks[NBLINK];
int8_t tonePin = -1;
unsigned long toneEnd = 0;
struct Mot { int8_t pwm, a, b; unsigned long end; } motors[NMOTOR];
bool stepBusy = false, stepFinishing = false;
int8_t stepPin[4];
long stepsLeft = 0;
int8_t stepDir = 1;
uint8_t stepIdx = 0;
unsigned long stepPer = 2, stepNext = 0;
const uint8_t COIL[4] = {0, 2, 1, 3};   // ULN2003 coil order is IN1, IN3, IN2, IN4 (as AccelStepper 9,11,10,12)
const uint8_t HALF[8] = {0b0001, 0b0011, 0b0010, 0b0110, 0b0100, 0b1100, 0b1000, 0b1001};
Servo servos[NSERVO];
int8_t servoPin[NSERVO];
uint32_t outMask = 0;      // pins we drove as outputs
bool watched[MAXP], wRaw[MAXP], wRep[MAXP];
unsigned long wT[MAXP];
LiquidCrystal *lcd = nullptr;
#if USE_LCD_I2C
LiquidCrystal_I2C *lcdI2C = nullptr;
#endif

// ---------------------------------------------------------------- helpers
void printPin(int p) {
  if (p >= A0) { Serial.print('A'); Serial.print(p - A0); }
  else { Serial.print('D'); Serial.print(p); }
}

int pinOf(const char *s) {   // "D2", "A0" or "13" -> pin number, -1 if bad
  if (!s || !*s) return -1;
  char c = *s;
  bool dig = (c == 'D' || c == 'd'), an = (c == 'A' || c == 'a');
  const char *d = (dig || an) ? s + 1 : s;
  if (!*d) return -1;
  int n = 0;
  for (; *d; d++) {
    if (*d < '0' || *d > '9') return -1;
    n = n * 10 + (*d - '0');
    if (n > 99) return -1;
  }
  if (an) return n <= 5 ? A0 + n : -1;
  if (dig) return n <= 13 ? n : -1;
  return n < 20 ? n : -1;
}

bool num(const char *s, long &out) {
  if (!s || !*s) return false;
  char *e;
  out = strtol(s, &e, 10);
  return *e == 0;
}

void ok(const __FlashStringHelper *c) { Serial.print(F("OK,")); Serial.println(c); }
void err(const char *c, const __FlashStringHelper *why) {
  Serial.print(F("ERR,")); Serial.print(c); Serial.print(','); Serial.println(why);
}

// pin argument i of the command; prints ERR and returns -1 if bad
int pinArg(uint8_t i) {
  int p = (i < argc) ? pinOf(v[i]) : -1;
  if (p < 0) { err(v[0], F("bad pin")); return -1; }
  if (p <= 1) { err(v[0], F("reserved pin")); return -1; }
  return p;
}

void drive(int p, uint8_t level) {
  pinMode(p, OUTPUT);
  digitalWrite(p, level);
  outMask |= (1UL << p);
}

void stopBlink(int p) {
  for (uint8_t i = 0; i < NBLINK; i++)
    if (blinks[i].pin == p) blinks[i].pin = -1;
}

void stopTone() {
  if (tonePin >= 0) { noTone(tonePin); digitalWrite(tonePin, LOW); tonePin = -1; }
}

void stopMotor(Mot &m) {
  if (m.pwm < 0) return;
  digitalWrite(m.a, LOW); digitalWrite(m.b, LOW); analogWrite(m.pwm, 0);
  m.pwm = -1;
}

void stopStep() {
  if (stepBusy) for (uint8_t i = 0; i < 4; i++) digitalWrite(stepPin[i], LOW);
  stepBusy = false; stepFinishing = false;
}

int servoSlot(int p, bool create) {
  for (uint8_t i = 0; i < NSERVO; i++) if (servoPin[i] == p) return i;
  if (!create) return -1;
  for (uint8_t i = 0; i < NSERVO; i++) if (servoPin[i] < 0) { servoPin[i] = p; servos[i].attach(p); return i; }
  return -1;
}

void allOff() {
  for (uint8_t i = 0; i < NBLINK; i++) blinks[i].pin = -1;
  stopTone();
  for (uint8_t i = 0; i < NMOTOR; i++) stopMotor(motors[i]);
  stopStep();
  for (uint8_t i = 0; i < NSERVO; i++) if (servoPin[i] >= 0) { servos[i].detach(); servoPin[i] = -1; }
  for (uint8_t p = 2; p < MAXP; p++)
    if (outMask & (1UL << p)) digitalWrite(p, LOW);
}

// ---------------------------------------------------------------- DHT11 (own bit-bang reader)
// counts loop passes instead of microseconds, so it also works with interrupts off
uint32_t pulseCount(int p, uint8_t level) {
  uint32_t n = 0;
#ifdef ARDUINO_ARCH_AVR
  const uint32_t lim = 400UL;
#else
  const uint32_t lim = 40000UL;
#endif
  while (digitalRead(p) == level) if (++n > lim) return 0;
  return n;
}

void cmdDHT(int p) {
  uint8_t d[5] = {0, 0, 0, 0, 0};
  pinMode(p, INPUT_PULLUP);
  delay(2);
  pinMode(p, OUTPUT); digitalWrite(p, LOW);
  delay(20);                          // start signal: low for at least 18 ms
  pinMode(p, INPUT_PULLUP);
  delayMicroseconds(40);
#ifdef ARDUINO_ARCH_AVR
  noInterrupts();
#endif
  pulseCount(p, HIGH);                    // let the pull-up high end (sensor pulls low)
  bool good = pulseCount(p, LOW) && pulseCount(p, HIGH);   // 80 us low + 80 us high answer
  for (uint8_t i = 0; good && i < 40; i++) {
    uint32_t lo = pulseCount(p, LOW), hi = pulseCount(p, HIGH);
    if (!lo || !hi) { good = false; break; }
    d[i / 8] <<= 1;
    if (hi > lo) d[i / 8] |= 1;
  }
#ifdef ARDUINO_ARCH_AVR
  interrupts();
#endif
  pinMode(p, INPUT_PULLUP);
  if (!good) { err("DHT", F("timeout (no sensor answer)")); return; }
  if ((uint8_t)(d[0] + d[1] + d[2] + d[3]) != d[4]) { err("DHT", F("checksum")); return; }
  Serial.print(F("OK,DHT,")); Serial.print(d[2]); Serial.print('.'); Serial.print(d[3] % 10);
  Serial.print(','); Serial.println(d[0]);
}

// ---------------------------------------------------------------- command handlers
void cmdPing(int trig, int echo) {
  drive(trig, LOW);
  pinMode(echo, INPUT);
  delayMicroseconds(2);
  digitalWrite(trig, HIGH); delayMicroseconds(10); digitalWrite(trig, LOW);
  unsigned long us = pulseIn(echo, HIGH, 25000UL);
  Serial.print(F("OK,PING,")); Serial.println(us / 58.0, 1);
}

void cmdI2CScan() {
  Wire.begin();
  bool any = false;
  Serial.print(F("OK,I2CSCAN,"));
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      if (any) Serial.print(';');
      Serial.print(F("0x")); if (a < 16) Serial.print('0'); Serial.print(a, HEX);
      any = true;
    }
  }
  Serial.println(any ? F("") : F("NONE"));
}

void showText(Print &lc, char *text, void (*cursor)(uint8_t)) {
  char *bar = strchr(text, '|');
  if (bar) *bar = 0;
  cursor(0); lc.print(String(text).substring(0, 16));
  cursor(1); lc.print(bar ? String(bar + 1).substring(0, 16) : String(F("")));
}
void lcdCursor(uint8_t r) { lcd->setCursor(0, r); }
#if USE_LCD_I2C
void lcdI2CCursor(uint8_t r) { lcdI2C->setCursor(0, r); }
#endif

void cmdLCD() {
  if (argc < 8) { err(v[0], F("args")); return; }
  int p[6];
  for (uint8_t i = 0; i < 6; i++) { p[i] = pinArg(1 + i); if (p[i] < 0) return; }
  if (lcd) delete lcd;
  lcd = new LiquidCrystal(p[0], p[1], p[2], p[3], p[4], p[5]);
  lcd->begin(16, 2);
  lcd->clear();
  showText(*lcd, v[7], lcdCursor);
  ok(F("LCD"));
}

void cmdLCDI2C() {
#if USE_LCD_I2C
  if (argc < 3) { err(v[0], F("args")); return; }
  long a = strtol(v[1], NULL, 16);
  if (a < 1 || a > 126) { err(v[0], F("bad address")); return; }
  if (lcdI2C) delete lcdI2C;
  lcdI2C = new LiquidCrystal_I2C((uint8_t)a, 16, 2);
  lcdI2C->init(); lcdI2C->backlight(); lcdI2C->clear();
  showText(*lcdI2C, v[2], lcdI2CCursor);
  ok(F("LCDI2C"));
#else
  err(v[0], F("disabled"));
#endif
}

void cmdStep() {
  if (argc < 7) { err(v[0], F("args")); return; }
  int8_t pins[4];
  for (uint8_t i = 0; i < 4; i++) { int p = pinArg(1 + i); if (p < 0) return; pins[i] = p; }
  long steps, per;
  if (!num(v[5], steps) || !num(v[6], per) || steps == 0 || per < 1 || per > 1000) { err(v[0], F("args")); return; }
  if (stepBusy) { err(v[0], F("busy")); return; }
  for (uint8_t i = 0; i < 4; i++) { stepPin[i] = pins[i]; drive(pins[i], LOW); }
  stepDir = steps > 0 ? 1 : -1;
  stepsLeft = labs(steps);
  stepPer = per;
  stepNext = millis();
  stepBusy = true; stepFinishing = false;
  ok(F("STEP"));
}

void cmdMotor() {
  if (argc < 6) { err(v[0], F("args")); return; }
  int pw = pinArg(1), a = pinArg(2), b = pinArg(3);
  if (pw < 0 || a < 0 || b < 0) return;
  long sp, ms;
  if (!num(v[4], sp) || !num(v[5], ms) || sp < -255 || sp > 255 || ms < 1) { err(v[0], F("args")); return; }
  uint8_t slot = 0;                     // same channel, else a free one, else slot 0
  for (uint8_t i = 0; i < NMOTOR; i++) if (motors[i].pwm == pw) { slot = i; break; }
  if (motors[slot].pwm != pw)
    for (uint8_t i = 0; i < NMOTOR; i++) if (motors[i].pwm < 0) { slot = i; break; }
  stopMotor(motors[slot]);
  drive(a, sp > 0); drive(b, sp < 0);
  pinMode(pw, OUTPUT); outMask |= (1UL << pw);
  analogWrite(pw, labs(sp));
  motors[slot] = {(int8_t)pw, (int8_t)a, (int8_t)b, millis() + (unsigned long)ms};
  ok(F("MOTOR"));
}

void handle() {
  char *comma = strchr(line, ',');
  uint8_t limit = 8;
  for (char *c = line; *c && *c != ','; c++) *c = toupper(*c);
  if (!strncmp(line, "LCDI2C", 6) && (line[6] == ',' || !line[6])) limit = 3;
  argc = 0;
  v[argc++] = line;
  for (char *s = comma ? comma : line + strlen(line); *s && argc < limit; s++)
    if (*s == ',') { *s = 0; v[argc++] = s + 1; }
  const char *c = v[0];
  long x, y, z;
  int p, q;

  if (!strcmp(c, "HELLO")) {
    Serial.println(F("OK,HELLO,PINTESTER," BOARD_NAME "," VERSION));
  } else if (!strcmp(c, "MODE")) {
    if ((p = pinArg(1)) < 0) return;
    if (argc < 3) { err(c, F("args")); return; }
    for (char *s = v[2]; *s; s++) *s = toupper(*s);
    if (!strcmp(v[2], "OUT")) drive(p, LOW);
    else if (!strcmp(v[2], "IN")) { stopBlink(p); pinMode(p, INPUT); }
    else if (!strcmp(v[2], "PULLUP")) { stopBlink(p); pinMode(p, INPUT_PULLUP); }
    else { err(c, F("bad mode")); return; }
    ok(F("MODE"));
  } else if (!strcmp(c, "DW")) {
    if ((p = pinArg(1)) < 0) return;
    if (argc < 3 || !num(v[2], x) || (x != 0 && x != 1)) { err(c, F("bad level")); return; }
    stopBlink(p); drive(p, x);
    ok(F("DW"));
  } else if (!strcmp(c, "PWM")) {
    if ((p = pinArg(1)) < 0) return;
    if (argc < 3 || !num(v[2], x) || x < 0 || x > 255) { err(c, F("bad value")); return; }
    stopBlink(p); pinMode(p, OUTPUT); outMask |= (1UL << p); analogWrite(p, x);
    ok(F("PWM"));
  } else if (!strcmp(c, "DR")) {
    if ((p = pinArg(1)) < 0) return;
    Serial.print(F("OK,DR,")); printPin(p); Serial.print(','); Serial.println(digitalRead(p));
  } else if (!strcmp(c, "AR")) {
    if ((p = pinArg(1)) < 0) return;
    if (p < A0 || p > A0 + 5) { err(c, F("not analog")); return; }
    Serial.print(F("OK,AR,")); printPin(p); Serial.print(','); Serial.println(analogRead(p));
  } else if (!strcmp(c, "BLINK")) {
    if ((p = pinArg(1)) < 0) return;
    if (argc < 4 || !num(v[2], x) || !num(v[3], y) || x < 1 || x > 100 || y < 1) { err(c, F("args")); return; }
    stopBlink(p);
    for (uint8_t i = 0; i < NBLINK; i++) if (blinks[i].pin < 0) {
      unsigned long now = millis();
      drive(p, HIGH);
      blinks[i] = {(int8_t)p, true, 500UL / x, now + 500UL / x, now + (unsigned long)y};
      if (blinks[i].half < 1) blinks[i].half = 1;
      ok(F("BLINK")); return;
    }
    err(c, F("too many blinks"));
  } else if (!strcmp(c, "TONE")) {
    if ((p = pinArg(1)) < 0) return;
    if (argc < 4 || !num(v[2], x) || !num(v[3], y) || x < 31 || x > 20000 || y < 1) { err(c, F("args")); return; }
    stopTone(); stopBlink(p);
    outMask |= (1UL << p);
    tone(p, (unsigned int)x);
    tonePin = p; toneEnd = millis() + (unsigned long)y;
    ok(F("TONE"));
  } else if (!strcmp(c, "SERVO")) {
    if ((p = pinArg(1)) < 0) return;
    if (argc < 3 || !num(v[2], x) || x < 0 || x > 180) { err(c, F("bad angle")); return; }
    int s = servoSlot(p, true);
    if (s < 0) { err(c, F("too many servos")); return; }
    servos[s].write(x);
    ok(F("SERVO"));
  } else if (!strcmp(c, "SERVOOFF")) {
    if ((p = pinArg(1)) < 0) return;
    int s = servoSlot(p, false);
    if (s >= 0) { servos[s].detach(); servoPin[s] = -1; }
    ok(F("SERVOOFF"));
  } else if (!strcmp(c, "STEP")) {
    cmdStep();
  } else if (!strcmp(c, "MOTOR")) {
    cmdMotor();
  } else if (!strcmp(c, "PING")) {
    if ((p = pinArg(1)) < 0 || (q = pinArg(2)) < 0) return;
    cmdPing(p, q);
  } else if (!strcmp(c, "DHT")) {
    if ((p = pinArg(1)) < 0) return;
    cmdDHT(p);
  } else if (!strcmp(c, "I2CSCAN")) {
    cmdI2CScan();
  } else if (!strcmp(c, "LCD")) {
    cmdLCD();
  } else if (!strcmp(c, "LCDI2C")) {
    cmdLCDI2C();
  } else if (!strcmp(c, "WATCH")) {
    if ((p = pinArg(1)) < 0) return;
    pinMode(p, INPUT_PULLUP);
    watched[p] = true; wRaw[p] = wRep[p] = digitalRead(p); wT[p] = millis();
    ok(F("WATCH"));
  } else if (!strcmp(c, "UNWATCH")) {
    if ((p = pinArg(1)) < 0) return;
    watched[p] = false;
    ok(F("UNWATCH"));
  } else if (!strcmp(c, "ALLOFF")) {
    allOff();
    ok(F("ALLOFF"));
  } else {
    err(c, F("unknown command"));
  }
}

// ---------------------------------------------------------------- timers (all non-blocking)
void tickBlink(unsigned long now) {
  for (uint8_t i = 0; i < NBLINK; i++) {
    Blink &b = blinks[i];
    if (b.pin < 0) continue;
    if ((long)(now - b.end) >= 0) { digitalWrite(b.pin, LOW); b.pin = -1; }
    else if ((long)(now - b.next) >= 0) { b.lvl = !b.lvl; digitalWrite(b.pin, b.lvl); b.next += b.half; }
  }
}

void tickTone(unsigned long now) {
  if (tonePin >= 0 && (long)(now - toneEnd) >= 0) stopTone();
}

void tickMotor(unsigned long now) {
  for (uint8_t i = 0; i < NMOTOR; i++)
    if (motors[i].pwm >= 0 && (long)(now - motors[i].end) >= 0) { stopMotor(motors[i]); Serial.println(F("DONE,MOTOR")); }
}

void tickStep(unsigned long now) {
  if (!stepBusy || (long)(now - stepNext) < 0) return;
  if (stepsLeft > 0) {
    uint8_t pat = HALF[stepIdx];
    for (uint8_t i = 0; i < 4; i++) digitalWrite(stepPin[COIL[i]], (pat >> i) & 1);
    stepIdx = (stepIdx + 8 + stepDir) & 7;
    stepsLeft--;
    stepNext = now + stepPer;
  } else {                              // last step had its time; release the coils
    stopStep();
    Serial.println(F("DONE,STEP"));
  }
}

void tickWatch(unsigned long now) {
  for (uint8_t p = 2; p < MAXP; p++) {
    if (!watched[p]) continue;
    bool r = digitalRead(p);
    if (r != wRaw[p]) { wRaw[p] = r; wT[p] = now; }
    else if (r != wRep[p] && now - wT[p] >= DEBOUNCE_MS) {
      wRep[p] = r;
      Serial.print(F("EDGE,")); printPin(p); Serial.print(','); Serial.println(r);
    }
  }
}

void readSerial() {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      line[lineLen] = 0;
      if (lineLen) handle();
      lineLen = 0;
    } else if (lineLen < LINE_MAX - 1) {
      line[lineLen++] = ch;
    }
  }
}

void setup() {
  Serial.begin(115200);
  for (uint8_t i = 0; i < NBLINK; i++) blinks[i].pin = -1;
  for (uint8_t i = 0; i < NMOTOR; i++) motors[i].pwm = -1;
  for (uint8_t i = 0; i < NSERVO; i++) servoPin[i] = -1;
}

void loop() {
  readSerial();
  unsigned long now = millis();
  tickBlink(now);
  tickTone(now);
  tickMotor(now);
  tickStep(now);
  tickWatch(now);
}
