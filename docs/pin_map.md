# Pin maps (match the wiring diagrams in docs/diagrams and the firmware in firmware/)

## Weather station: ELEGOO UNO R3 (5 V pins)
| Pin | Goes to |
|---|---|
| D2 | DHT11 data |
| D3 | Green LED (220 ohm) |
| D4 | Blue LED (220 ohm) |
| D5 | Red LED (220 ohm) |
| A0 | Yellow hit LED (220 ohm) |
| D6 | PN2222 base through 1 kohm (active buzzer) |
| D7 | Passive buzzer (tone) |
| D8 / D9 | LCD RS / E |
| D10 D11 D12 D13 | LCD D4 D5 D6 D7 |
| A4 / A5 | I2C display SDA / SCL (lives, add later: `HAS_LIVES_LCD 1`) |

## Robot: Arduino UNO Q #1 (3.3 V pins), two DRV8833 modules
Each module drives one side. On each module the A and B channels are joined (inputs tied together, outputs tied
together) so each side carries two motors. nSLEEP of both modules goes to 3V3.

| Pin | Goes to |
|---|---|
| D3 / D5 | Left DRV8833 IN1 / IN2 (forward = PWM on IN1, IN2 low) |
| D6 / D9 | Right DRV8833 IN1 / IN2 |
| D2 D4 D7 D8 | ULN2003 IN1 IN2 IN3 IN4 (turret stepper, code order 2, 7, 4, 8 = IN1, IN3, IN2, IN4) |
| A0 / A1 | HC-SR04 TRIG / ECHO (ECHO through 1k + 2k divider). A0 and A1 are not 5 V tolerant |
| A2 / A3 | Left / right bumper button (other leg to GND) |
| D13 | Status LED (220 ohm) |
| D10 | Optional second DHT11 (robot air), `HAS_ROBOT_DHT 1`. D11 and D12 are spare |
| 3V3 | DRV8833 nSLEEP |

D3, D5, D6 and D9 must give PWM. The UNO Q pinout lists PWM on D3, D5, D6, D9, D10 and D11. D5 is shared with the CAN
bus, which this project does not use.

## Tower: Arduino UNO Q #2
| Pin | Goes to |
|---|---|
| D9 | Push servo signal |
| D10 | Pan servo signal (second SG90, `HAS_PAN 1`) |
| D13 | Armed LED (220 ohm) |
| D2 | Test-fire button (other leg to GND) |

Power: see docs/diagrams/pow.png and rpow.png. Different supplies share only GND.
