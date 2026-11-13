// ServoTest.ino: sweeps a servo 45 to 135 degrees forever.
// Enter the signal pin over Serial; re-enter to retask.

#include <Servo.h>

const int CENTER_DEG = 90;
const int SWING_DEG = 45;
const int MIN_DEG = CENTER_DEG - SWING_DEG;
const int MAX_DEG = CENTER_DEG + SWING_DEG;
const unsigned long BAUD = 115200;
const unsigned long STEP_MS = 15;

Servo servo;
int pos = CENTER_DEG;
int dir = 1;
unsigned long lastStep = 0;

void setup() {
  Serial.begin(BAUD);
  Serial.println();
  Serial.println(F("Servo test"));
  Serial.println(F("Enter the servo signal pin (2-13):"));
}

void loop() {
  if (Serial.available()) {
    int pin = Serial.parseInt();
    if (pin >= 2 && pin <= 13) {
      servo.detach();
      servo.attach(pin);
      pos = CENTER_DEG;
      dir = 1;
      servo.write(pos);
      Serial.print(F("Sweeping on pin "));
      Serial.println(pin);
    } else {
      Serial.println(F("Invalid pin (use 2-13)."));
    }
    while (Serial.available()) Serial.read();
  }

  if (servo.attached() && millis() - lastStep >= STEP_MS) {
    lastStep = millis();
    pos += dir;
    if (pos >= MAX_DEG || pos <= MIN_DEG) {
      dir = -dir;
      pos += 2 * dir;
    }
    servo.write(pos);
  }
}
