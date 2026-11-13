// StepperTest.ino: swings a 28BYJ-48 between -45 and +45 degrees.
// Coil pins are consecutive, starting at the Serial-entered pin.

#include <AccelStepper.h>

const float STEPS_PER_REV = 2048.0;
const float SWING_DEG = 45.0;
const long SWING_STEPS = (long)(STEPS_PER_REV * SWING_DEG / 360.0);

const unsigned long BAUD = 115200;

AccelStepper* stepper = nullptr;
int currentPin = -1;

void setup() {
  Serial.begin(BAUD);
  Serial.println();
  Serial.println(F("Stepper test"));
  Serial.println(F("Enter the first STEP pin (coils on pin..pin+3):"));
}

void loop() {
  if (Serial.available()) {
    int pin = Serial.parseInt();
    if (pin >= 2 && pin <= 12) {
      if (stepper) {
        stepper->disableOutputs();
        delete stepper;
      }
      currentPin = pin;
      // FULL4WIRE pin order (p, p+2, p+1, p+3) suits 28BYJ-48 coils
      stepper = new AccelStepper(AccelStepper::FULL4WIRE, pin, pin + 2, pin + 1, pin + 3);
      stepper->setMaxSpeed(400.0);
      stepper->setAcceleration(200.0);
      Serial.print(F("Swinging on pins "));
      Serial.print(pin); Serial.print('-'); Serial.println(pin + 3);
      stepper->move(SWING_STEPS);
    } else {
      Serial.println(F("Invalid pin (use 2-12)."));
    }
    while (Serial.available()) Serial.read();
  }

  if (stepper) {
    if (stepper->distanceToGo() == 0) {
      stepper->move(-stepper->currentPosition());
    }
    stepper->run();
  }
}
