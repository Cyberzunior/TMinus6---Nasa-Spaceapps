# T-Minus_6

NASA Space Apps Challenge 2026, Toronto (Nov 14 and 15). Team D NOVAS.

A game spacecraft called **T-Minus_6** orbits Earth on a laptop. A four-wheel robot with the same name copies every move
on a cardboard board. One Bluetooth gamepad drives both. An auto-pilot dodges debris, a tower fires paper-ball asteroids,
a weather station warns the crew when the craft is in a hot or cold space, and the craft has 15 lives.

## What is in this repo
| Folder | What |
|---|---|
| `docs/` | The full project document (PDF and editable .docx) and every wiring / circuit diagram (`docs/diagrams/`) |
| `hardware/` | Pin maps and the short parts list |
| `firmware/weather_station/` | UNO R3: DHT11, 16-pin LCD, LEDs, buzzers, warnings |
| `firmware/robot/` | UNO Q #1: 4 motors (TB6612), turret stepper, ultrasonic, bumpers |
| `firmware/tower/` | UNO Q #2: push servo, test button, armed LED |
| `laptop/` | Python: gamepad test, movement model, links to robot / tower / weather station |

## Status (be honest, update this as you test)
| Part | Status |
|---|---|
| Weather station sketch | Written, 16-pin LCD only. I2C lives display not added yet |
| Robot sketch | Written, **untested** |
| Tower sketch | Written, **untested** |
| Laptop starter | Gamepad to wheel commands. **Missing:** the game, auto-pilot, camera, tower control, lives |
| UNO Q Wi-Fi bridge | **Not written.** Day-one check. Fallback: USB-C cable to the laptop (use `SerialLink`) |

## Setup
1. Arduino IDE libraries: **DHT sensor library** (and **Adafruit Unified Sensor**), **AccelStepper**. For the lives display later: **LiquidCrystal I2C** (Frank de Brabander).
2. Laptop: `cd laptop && pip install -r requirements.txt`
3. Pair the gamepad over Bluetooth, run `python gamepad_test.py`, copy the numbers into `config.py`.
4. Upload `firmware/weather_station` to the UNO R3, set `WEATHER_PORT` in `config.py`.

## Messages (plain text lines, 115200 baud on serial)
| From to | Line | Meaning |
|---|---|---|
| Weather to laptop | `W,temp,hum,state` | reading every 2 s (0 normal, 1 cold, 2 hot) |
| Laptop to weather | `V,temp` / `H,lives` / `G` / `R` | virtual temperature / lives / game over / reset |
| Laptop to robot | `D,left,right,ap` | wheel speeds -255..255, auto-pilot flag, 50 per second |
| Laptop to robot | `X` / `R` | game-over latch / release |
| Robot to laptop | `S,angle,cm,flags` / `B,L` or `B,R` | scan reading / bumper hit |
| Laptop to tower | `F` / `A,angle` / `X` / `R` | fire / aim / disarm / re-arm |
| Tower to laptop | `K` | ball released |

## Safety and rules
Paper balls only, keep people out of the line of fire. Never join two different power supplies except their GND.
UNO Q pins are 3.3 V. Space Apps: no recognizable minors in videos or photos.

## Create the repo
```
cd tminus6
git init
git add .
git commit -m "Initial T-Minus_6 project"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```
Pick a license when you create the repo on GitHub (or add a LICENSE file). Do not commit Wi-Fi passwords.
