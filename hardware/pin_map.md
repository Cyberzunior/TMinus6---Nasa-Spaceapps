# Pin maps (match the wiring diagrams in docs/diagrams)

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
| A4 / A5 | I2C display SDA / SCL (lives, add later) |

## Robot: Arduino UNO Q #1 (3.3 V pins)
| Pin | Goes to |
|---|---|
| A0 / A1 | HC-SR04 TRIG / ECHO (ECHO through 1k + 2k divider) |
| A2 / A3 | Left / right bumper button (other leg to GND) |
| D13 | Status LED (220 ohm) |
| D9 D10 D11 D12 | ULN2003 IN1 IN2 IN3 IN4 (code order 9, 11, 10, 12) |
| D5 / D4 / D2 | TB6612 PWMA / AIN1 / AIN2 (left side) |
| D6 / D7 / D8 | TB6612 PWMB / BIN1 / BIN2 (right side) |
| 3V3 | TB6612 VCC and STBY |

## Tower: Arduino UNO Q #2
| Pin | Goes to |
|---|---|
| D9 | Push servo signal |
| D10 | Pan servo signal (optional) |
| D13 | Armed LED (220 ohm) |
| D2 | Test-fire button (other leg to GND) |

Power: see docs/diagrams/pow.png and rpow.png. Different supplies share only GND.
