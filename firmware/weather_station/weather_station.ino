// T-Minus_6 weather station, firmware v2. ELEGOO UNO R3 (5 V). Protocol: see laptop/devio/protocol.py.
// Lines in : I?   Z,state   V,temp   H,lives   G   R          (state 0 normal, 1 cold, 2 hot)
// Lines out: I,weather,2   W,temp,hum,state  (every 2 s AND at once on every state change)
// Effective state = the more severe of (DHT11 with 1 C hysteresis, the game's zone Z). V overrides the sensor for tests.
// No delay() anywhere: the loop never waits.
#include <DHT.h>
#include <LiquidCrystal.h>                 // the 16-pin weather LCD (built in)

#define FW_VERSION 2
#define HAS_LIVES_LCD 0                    // set to 1 when the I2C 16x2 lives display is fitted (needs LiquidCrystal_I2C)
#if HAS_LIVES_LCD
#include <Wire.h>
#include <LiquidCrystal_I2C.h>             // Frank de Brabander's library
#endif

const float COLD_C = 18.0, HOT_C = 30.0, HYST = 1.0;
enum State { NORMAL = 0, COLD = 1, HOT = 2 };      // numbers match the protocol, and a bigger number is more severe
State sensorState = NORMAL, zoneState = NORMAL, state = NORMAL;

// Pins (do not change: they match docs/pin_map.md and the wiring diagrams)
const int PIN_DHT = 2, GREEN = 3, BLUE = 4, RED = 5, HIT_LED = A0, ACTIVE_BUZZ = 6, PASSIVE_BUZZ = 7;
DHT dht(PIN_DHT, DHT11);
LiquidCrystal weatherLcd(8, 9, 10, 11, 12, 13);    // RS, E, D4, D5, D6, D7

unsigned long tSensor = 0, tLcd = 0, tBlink = 0, tHit = 0;
float temp = 22.0, hum = 40.0, virtualTemp = 0.0;
bool useVirtual = false, blinkOn = false, gameOver = false;
int lives = 15;
char rx[40];
byte rxLen = 0;

#if HAS_LIVES_LCD
LiquidCrystal_I2C livesLcd(0x27, 16, 2);
byte heartFull[8]  = {0x00, 0x0A, 0x1F, 0x1F, 0x1F, 0x0E, 0x04, 0x00};
byte heartEmpty[8] = {0x00, 0x0A, 0x15, 0x11, 0x11, 0x0A, 0x04, 0x00};
bool livesLcdOk = false;
bool i2cPresent(byte addr) { Wire.beginTransmission(addr); return Wire.endTransmission() == 0; }
void showLives() {
  if (!livesLcdOk) return;
  livesLcd.setCursor(0, 0);
  for (int i = 0; i < 15; i++) livesLcd.write(byte(i < lives ? 0 : 1));
  livesLcd.write(' ');
  livesLcd.setCursor(0, 1);
  if (gameOver) { livesLcd.print("GAME OVER       "); return; }
  char line[17];
  snprintf(line, sizeof(line), "T-Minus_6 L%2d/15", lives);
  livesLcd.print(line);
}
#else
void showLives() {}
#endif

void printPadded(const char* s) {                  // always writes 16 characters, so no clear() flicker
  char buf[17];
  snprintf(buf, sizeof(buf), "%-16s", s);
  weatherLcd.print(buf);
}
void showWeather() {                               // called every 5 s and at once on every state change
  char l1[20], l2[20];
  if (gameOver)           { strcpy(l1, "SIGNAL LOST"); strcpy(l2, "GAME OVER"); }
  else if (state == HOT)  { strcpy(l1, "!! HOT ZONE !!"); strcpy(l2, "MOVE AWAY NOW!"); }
  else if (state == COLD) { strcpy(l1, "!! COLD ZONE !!"); strcpy(l2, "MOVE AWAY NOW!"); }
  else {
    char t[10];
    dtostrf(temp, 4, 1, t);
    snprintf(l1, sizeof(l1), "T %sC NORMAL", t);
    snprintf(l2, sizeof(l2), "H %d%%", (int)hum);
  }
  weatherLcd.setCursor(0, 0); printPadded(l1);
  weatherLcd.setCursor(0, 1); printPadded(l2);
}
void sendW() {
  Serial.print("W,"); Serial.print(temp, 1); Serial.print(','); Serial.print((int)hum); Serial.print(','); Serial.println((int)state);
}
void updateState() {
  float t = useVirtual ? virtualTemp : temp;
  State s = sensorState;
  if (s == NORMAL)    { if (t > HOT_C) s = HOT; else if (t < COLD_C) s = COLD; }
  else if (s == HOT)  { if (t < HOT_C - HYST) s = NORMAL; }
  else if (s == COLD) { if (t > COLD_C + HYST) s = NORMAL; }
  sensorState = s;
  State eff = (State)max((int)sensorState, (int)zoneState);       // the more severe state wins
  if (eff != state) {
    state = eff;
    showWeather(); tLcd = millis();                // the warning shows at once, not at the next 5 s update
    sendW();                                       // and the laptop hears about it at once
  }
}
void outputs(unsigned long now) {
  if (now - tBlink >= 100) { tBlink = now; blinkOn = !blinkOn; }  // about 5 blinks a second
  bool quiet = gameOver;
  digitalWrite(GREEN, state == NORMAL && !gameOver);
  digitalWrite(BLUE, state == COLD && blinkOn && !quiet);
  digitalWrite(RED,  state == HOT  && blinkOn && !quiet);
  digitalWrite(ACTIVE_BUZZ, !quiet && state == HOT && blinkOn);
  if (!quiet && state == COLD && blinkOn) tone(PASSIVE_BUZZ, 400); else noTone(PASSIVE_BUZZ);
  digitalWrite(HIT_LED, now - tHit < 1000);                       // 1 second hit flash
}
void handleLine(const char* s) {
  if (!strcmp(s, "I?"))             { Serial.println("I,weather,2"); }
  else if (s[0] == 'Z' && s[1] == ',') { int z = atoi(s + 2); zoneState = (State)constrain(z, 0, 2); updateState(); }
  else if (s[0] == 'V' && s[1] == ',') { useVirtual = true; virtualTemp = atof(s + 2); temp = virtualTemp; updateState(); }
  else if (s[0] == 'H' && s[1] == ',') { int n = atoi(s + 2); if (n < lives) tHit = millis(); lives = n; showLives(); }
  else if (!strcmp(s, "G"))         { gameOver = true; lives = 0; showLives(); showWeather(); }
  else if (!strcmp(s, "R"))         { gameOver = false; lives = 15; useVirtual = false; zoneState = NORMAL; updateState(); showLives(); showWeather(); }
}
void readSerial() {                                // collects one line at a time, never blocks
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { rx[rxLen] = 0; if (rxLen) handleLine(rx); rxLen = 0; }
    else if (c != '\r' && rxLen < sizeof(rx) - 1) rx[rxLen++] = c;
  }
}
void setup() {
  Serial.begin(115200);
  dht.begin();
  weatherLcd.begin(16, 2);
  pinMode(GREEN, OUTPUT); pinMode(BLUE, OUTPUT); pinMode(RED, OUTPUT);
  pinMode(HIT_LED, OUTPUT); pinMode(ACTIVE_BUZZ, OUTPUT); pinMode(PASSIVE_BUZZ, OUTPUT);
#if HAS_LIVES_LCD
  Wire.begin();
  byte addr = i2cPresent(0x27) ? 0x27 : (i2cPresent(0x3F) ? 0x3F : 0);   // the I2C scanner: try both addresses
  if (addr) {
    livesLcd = LiquidCrystal_I2C(addr, 16, 2);
    livesLcd.init(); livesLcd.backlight();
    livesLcd.createChar(0, heartFull); livesLcd.createChar(1, heartEmpty);
    livesLcdOk = true;
  }
#endif
  showWeather(); showLives();
}
void loop() {
  unsigned long now = millis();
  if (now - tSensor >= 2000) {                     // read the sensor every 2 s (the DHT11 is slow and about 2 C accurate)
    tSensor = now;
    float t = dht.readTemperature(), h = dht.readHumidity();
    if (!isnan(t) && !useVirtual) { temp = t; hum = isnan(h) ? hum : h; }
    updateState();
    sendW();
  }
  if (now - tLcd >= 5000) { tLcd = now; showWeather(); }          // the temperature shows every 5 s
  readSerial();
  outputs(now);
}
