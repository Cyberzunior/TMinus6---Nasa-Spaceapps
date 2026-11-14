# T-Minus_6 tests

## Automated tests (pytest)

Headless, no hardware, about a minute:

    python tests/run_tests.py            # built-in runner, no extra packages
    pytest tests                         # same tests with pytest (pip install pytest)

`test_model` (mixer, dead zone, movement model, calibration), `test_protocol_config` (every line, garbage, settings file),
`test_game_rules` (hits, protection, game over, asteroid sequence, weather, zones, auto-pilot dodge 10 of 10),
`test_devices` (discovery, RTT, failsafe, latch, tower safety, unplug and replug over real loopback sockets),
`test_firmware_bridges` (static checks of the sketches, UNO Q bridge self-tests), `test_app_flow` (the whole game in `--sim`).
Soak: `python laptop/tools/soak.py --demos 3`.

# T-Minus_6 hardware triage

Two front ends for the same hardware:

- `triage_gui.py`: a PyQt5 window with a **Case** mode and a **Func** mode (below).
- `triage.py`: the original terminal script that walks every piece of hardware and
  prints a PASS / FAIL / SKIP line per check, plus a summary at the end.

Also here: the bench sketches `PinTester.ino`, `ServoTest.ino`, `StepperTest.ino`
(upload to the board named in the filename, 115200 baud).

## Install

    pip install -r tests/requirements.txt      # pyserial, pygame, opencv-python, PyQt5

## GUI

    python tests/triage_gui.py

Connect devices in the left panel (COM port for USB boards, `ip:port` for the UNO Qs;
any of them accepts either), then pick a mode with the toggle at the top. **STOP ALL**
stops the wheels, releases the stepper, disarms the tower and stops a running test.

**Case mode** runs acceptance tests per sector, written from
`docs/T-Minus_6_Project_Document.pdf` (its "Test it" lists and test checklist):

| Sector | Checks |
|---|---|
| Weather station | `W` stream every 2 s, DHT11 ranges, hot/cold states and the 1 C hysteresis (via `V,temp`), LCD/LED/buzzer prompts, hit LED, game over, reset |
| Robot (UNO Q #1) | scan rate and +/-45 deg sweep, 10 cm accuracy, 8 cm stop flag and forward refusal, four wheels, tank turn, 300 ms timeout, bumpers, auto-pilot LED, `X`/`R` latch |
| Tower (UNO Q #2) | `F` answered by `K`, one ball per shot, double `F` ignored, disarm/re-arm, test button, 2-3 s ball flight (you click when it lands), optional pan |
| Camera | stream opens, 320x240, 15-20 fps, live picture and delay |
| Gamepad | controller found, stick rest inside the 8% dead zone, full travel, Y/B/Start numbers match `laptop/config.py` |
| Wiring | wire by wire with the PinTester board (weather / robot / tower list) |

Automatic checks read the board's replies; things only a person can judge are asked in
the prompt panel (keys: Y / N / S / Enter). **Save report** writes `tests/reports/`.

**Func mode** has one tab per part: Stepper and Servo sliders, LCD text, Tower fire,
Robot drive with a live radar, Weather readout, Camera, and Gamepad (the stick/trigger
vector in an XYZ cube; optionally forwarded to the robot as `D,left,right,0`).
Stepper, Servo (bench target) and LCD go through the PinTester sketch on a spare UNO,
because the production firmware has no commands for them; the Servo tab can also drive
the tower's pan servo (`A,angle`).

## Command line

    python tests/triage.py                     # everything, asks before each board
    python tests/triage.py weather --port COM5 # just one board
    python tests/triage.py robot               # UDP 192.168.1.50:5005 (or --port for serial)
    python tests/triage.py tower               # UDP 192.168.1.51:5005 (or --port for serial)
    python tests/triage.py wiring              # wire-by-wire on the PinTester board
    python tests/triage.py camera [--url http://192.168.1.60:81/stream]
    python tests/triage.py gamepad

The exit code is 1 when any check failed, so it works as a gate before a demo.

## What each board gets

- **weather** (UNO R3, USB): `W,temp,hum,state` line arrives and parses, DHT11
  ranges sane, green LED + LCD normal, hot air turns it HOT (red LED + active
  buzzer), cold pack turns it COLD (blue LED + passive buzzer), back to NORMAL.
- **robot** (UNO Q #1): `S,angle,dist,flags` line, sweep covers about +/-45 deg,
  HC-SR04 sees a hand at 10 cm, wheels forward and back together at `D,...`
  (wheels on blocks!), bumpers send `B,L` / `B,R`, status LED with auto-pilot.
- **tower** (UNO Q #2): armed LED on, `F` answered by `K`, exactly one ball
  drops, board does not reset, ball flight 2-3 s.
- **wiring**: upload `PinTester.ino` to a spare UNO, connect the harness, and it
  steps through every wire of the chosen board (weather / robot / tower):
  LEDs, buzzers, DHT, buttons, ultrasonic, servos, stepper, motors, LCD, I2C.
- **camera**: opens the ESP32-CAM or phone stream, checks 60 frames flow,
  resolution near 320x240 and at least 5 fps (doc wants 15-20).
- **gamepad**: lists the controller, samples axes and buttons for 4 s.

## Safety

- Robot on blocks for drive checks; Esc/Ctrl+C stops the script.
- UNO Q pins are 3.3 V: HC-SR04 ECHO needs the 1k + 2k divider.
- Keep the tower pointed away from people; `F` drops a real ball.
- Hair dryer on low, 30 cm from the DHT11; cold pack in a sealed bag.
- UNO R3 resets when the serial port opens: the script waits 2 s for you.
- Venue Wi-Fi often isolates devices: use the phone hotspot.
