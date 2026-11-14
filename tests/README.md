# T-Minus_6 hardware triage

One script, `triage.py`, that walks every piece of hardware and prints a
PASS / FAIL / SKIP line per check, plus a summary at the end. No GUI.

Also here: the bench sketches `PinTester.ino`, `ServoTest.ino`, `StepperTest.ino`
(upload to the board named in the filename, 115200 baud).

## Install

    pip install -r tests/requirements.txt      # pyserial, pygame, opencv-python

## Run

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
