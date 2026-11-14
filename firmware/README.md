# Firmware

| Folder | Board | Files |
|---|---|---|
| `weather_station/` | ELEGOO UNO R3 (USB to the laptop) | `weather_station.ino` |
| `robot/` | Arduino UNO Q #1 | `robot.ino` (STM32 side), `linux_bridge/robot_bridge.py` (Linux side) |
| `tower/` | Arduino UNO Q #2 | `tower.ino`, `linux_bridge/tower_bridge.py` |

**None of this has been compiled or run on a board yet.** Every sketch is written against the pin maps in `docs/pin_map.md`.

## Weather station (UNO R3)
Libraries: DHT sensor library (+ Adafruit Unified Sensor). For the lives display later: LiquidCrystal I2C (Frank de Brabander) and `#define HAS_LIVES_LCD 1`.
Replies to `I?` with `I,weather,2`, sends `W,temp,hum,state` every 2 s and at once on every state change.

## UNO Q: how the two halves talk
```
laptop --UDP 5005--> robot_bridge.py --Bridge "line"--> robot.ino
laptop <--UDP------- robot_bridge.py <--Bridge "mcu_line"-- robot.ino
```
An Arduino App Lab app has a sketch and a Python part. Put `robot.ino` as the sketch and `robot_bridge.py` as the Python
`main.py` of one App, and the same for the tower. Then set the App to start when the board powers on (App Lab: "Running an App at Startup").
The sketches need the Arduino_RouterBridge library (comes with the UNO Q core) and `AccelStepper` (robot) / `Servo` (tower).

Test a bridge on a PC without a board: `python firmware/robot/linux_bridge/robot_bridge.py --selftest`.

## Verify on day one (not checked against a real board)
1. The Bridge API names: Python `from arduino.app_utils import App, Bridge`, `Bridge.notify`, `Bridge.provide`; sketch `Bridge.begin`, `Bridge.provide_safe`, `Bridge.notify`. They come from community write-ups; confirm against the current Arduino UNO Q docs.
2. Pins **D3, D5, D6, D9 give PWM** (the pinout lists D3 D5 D6 D9 D10 D11). If any does not, tell the team before wiring.
3. The `Servo` library runs on the UNO Q core and D9 / D10 can drive servos.
4. How the ultrasonic echo pin A1 behaves: `robot.ino` polls it (no interrupt), so expect about 1 to 2 cm of error. A0 and A1 are not 5 V tolerant: keep the 1k + 2k divider.
5. Real turret scan rate: the stepper at 700 steps/s sweeps 5 degrees in about 80 ms, plus 60 ms per ping, so expect 7 to 8 readings a second, not 15.
6. Wi-Fi power saving: the bridge tries `iw dev wlan0 set power_save off`; check the interface name on your board. The UNO Q Wi-Fi is dual band (2.4 / 5 GHz): use the 2.4 GHz hotspot anyway.
7. If the Bridge is awkward: plug a USB-C data cable between the laptop and the UNO Q. The game's serial scan speaks the same lines if the board answers `I?` (the sketch would then need a `Serial` front end).

## Behaviour that must survive a Wi-Fi drop
Robot: wheels stop 300 ms after the last `D`, the turret parks and the LED blinks slowly after 2 s, a game-over latch ignores all `D` until `R`.
Tower: ignores `F` when disarmed or within 1.5 s of the last fire.
