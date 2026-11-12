// T-Minus_6 weather station: UNO R3, 16-pin LCD only (no I2C display yet)
#include <DHT.h>
#include <LiquidCrystal.h>          // the 16-pin weather LCD (built in)

const float COLD_C = 18.0, HOT_C = 30.0, HYST = 1.0;
enum State { NORMAL, COLD, HOT };
State state = NORMAL;

DHT dht(2, DHT11);
LiquidCrystal weatherLcd(8, 9, 10, 11, 12, 13);   // RS, E, D4, D5, D6, D7
const int GREEN = 3, BLUE = 4, RED = 5, HIT_LED = A0;   // matches the wire list
const int ACTIVE_BUZZ = 6, PASSIVE_BUZZ = 7;
unsigned long tSensor = 0, tLcd = 0, tBlink = 0, tHit = 0;
float temp = 22, hum = 40;
bool simMode = false, blinkOn = false, gameOver = false;
int lives = 15;
String rx = "";

void showWeather() {                       // called every 5 s and on every state change
  weatherLcd.clear();
  if (gameOver) { weatherLcd.print("SIGNAL LOST"); weatherLcd.setCursor(0, 1); weatherLcd.print("GAME OVER"); return; }
  if (state == HOT)  { weatherLcd.print("!! HOT SPACE !!");  weatherLcd.setCursor(0, 1); weatherLcd.print("CREW: HEAT WARN"); }
  else if (state == COLD) { weatherLcd.print("!! COLD SPACE !!"); weatherLcd.setCursor(0, 1); weatherLcd.print("CREW: COLD WARN"); }
  else { weatherLcd.print("T "); weatherLcd.print(temp, 1); weatherLcd.print("C NORMAL");
         weatherLcd.setCursor(0, 1); weatherLcd.print("H "); weatherLcd.print((int)hum); weatherLcd.print("%"); }
}
void updateState() {
  State old = state;
  if (state == NORMAL) { if (temp < COLD_C) state = COLD; else if (temp > HOT_C) state = HOT; }
  else if (state == COLD && temp > COLD_C + HYST) state = NORMAL;
  else if (state == HOT  && temp < HOT_C - HYST) state = NORMAL;
  if (state != old) { showWeather(); tLcd = millis(); }     // warning shows at once
}
void outputs(unsigned long now) {
  if (now - tBlink >= 100) { tBlink = now; blinkOn = !blinkOn; }   // about 5 blinks a second
  bool quiet = gameOver;
  digitalWrite(GREEN, state == NORMAL && !gameOver);
  digitalWrite(BLUE, state == COLD && blinkOn && !quiet);
  digitalWrite(RED,  state == HOT  && blinkOn && !quiet);
  digitalWrite(ACTIVE_BUZZ, !quiet && state == HOT && blinkOn);
  if (!quiet && state == COLD && blinkOn) tone(PASSIVE_BUZZ, 400); else noTone(PASSIVE_BUZZ);
  digitalWrite(HIT_LED, now - tHit < 1000);                         // 1 second hit flash
}
void showLives() {}                        // lives display not connected yet (I2C display later)

void setup() {
  Serial.begin(115200);
  dht.begin();
  weatherLcd.begin(16, 2);
  pinMode(GREEN, OUTPUT); pinMode(BLUE, OUTPUT); pinMode(RED, OUTPUT);
  pinMode(HIT_LED, OUTPUT); pinMode(ACTIVE_BUZZ, OUTPUT);
  showWeather();
}
void handleLine(const String& s) {                 // lines from the laptop
  if (s.startsWith("H,")) { int n = s.substring(2).toInt(); if (n < lives) tHit = millis(); lives = n; showLives(); }
  else if (s.startsWith("V,")) { simMode = true; temp = s.substring(2).toFloat(); updateState(); }
  else if (s == "G") { gameOver = true; lives = 0; showLives(); showWeather(); }
  else if (s == "R") { gameOver = false; lives = 15; simMode = false; showLives(); showWeather(); }
}
void readSerial() {                                // collects one line at a time, never blocks
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { rx.trim(); if (rx.length()) handleLine(rx); rx = ""; }
    else if (c != '\r' && rx.length() < 32) rx += c;
  }
}
void loop() {
  unsigned long now = millis();
  if (now - tSensor >= 2000) {                     // read the sensor every 2 s
    tSensor = now;
    float t = dht.readTemperature(), h = dht.readHumidity();
    if (!isnan(t) && !simMode) { temp = t; hum = h; updateState(); }
    Serial.print("W,"); Serial.print(temp, 1); Serial.print(','); Serial.print((int)hum); Serial.print(','); Serial.println((int)state);
  }
  if (now - tLcd >= 5000) { tLcd = now; showWeather(); }   // record every 5 s
  readSerial();
  outputs(now);
}
