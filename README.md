# T-Minus_6

NASA Space Apps Challenge 2026, Toronto (Nov 14 and 15). Team D NOVAS.

A game spacecraft called **T-Minus_6** orbits Earth on a laptop. A four-wheel robot with the same name copies every move
on a cardboard board. One Bluetooth gamepad drives both. An auto-pilot dodges debris, a tower fires paper-ball asteroids,
a weather station warns the crew when the craft is in a hot or cold space, and the craft has 15 lives.

## Try it in 30 seconds (no hardware)
```
pip uninstall pygame          # only if plain "pygame" is installed: it cannot live next to pygame-ce
pip install -r requirements.txt
cd laptop
python main.py --sim
```
Every device is then a software one that speaks the real protocol, so the whole game, the Hardware Check and the demo
are playable. Arrow keys / WASD drive, Space turns the auto-pilot on, keys 1 / 2 / 3 blow hot / cold / normal air at the
simulated weather sensor. `python main.py --sim --demo` plays the scripted rehearsal.

## What is in this repo
| Folder | What |
|---|---|
| `laptop/` | The game and everything on the laptop side (see below) |
| `firmware/weather_station/` | UNO R3: DHT11, 16-pin LCD, LEDs, buzzers, hot / cold warnings, optional I2C lives display |
| `firmware/robot/` | UNO Q #1: `robot.ino` (microcontroller) and `linux_bridge/robot_bridge.py` (Linux side, UDP to Bridge) |
| `firmware/tower/` | UNO Q #2: `tower.ino` and `linux_bridge/tower_bridge.py` |
| `tests/` | `test_*.py` automated tests, plus the hardware triage tools (`triage_gui.py`, `triage.py`, bench sketches) |
| `docs/` | Project document (PDF, docx), game software spec, wiring diagrams, `pin_map.md`, `parts_list.md` |

Inside `laptop/`: `main.py` (entry), `app.py` (threads, state machine, input), `config.py`, `scenario.json`,
`core/` (rules, model, auto-pilot, weather, hazards, lives, game), `devio/` (gamepad, links, discovery, camera, simulator,
logging, protocol; named `devio` because `io` would shadow Python's own module), `gfx/` (renderer, HUD, screens),
`audio/` (synthesized sound), `tools/` (hardware check, latency test, calibration, gamepad test, soak).

## Status (be honest, update this as you test)
Checked in software only, on a PC with the simulated devices (60 automated tests, run `python tests/run_tests.py`):
rules, hit and protection rules, game over and restart, weather states and hysteresis, spike warning, zones,
auto-pilot (0 hits in 10 random runs of 90 s), discovery and reconnect over real loopback sockets, the 300 ms failsafe,
tower safety rules, the full game flow, three demos back to back with no memory or thread growth.

**Not tested on real hardware yet** (nothing here has met a robot, a tower or a station):
| Part | State |
|---|---|
| Weather station firmware v2 | Written, **not compiled, not uploaded** |
| Robot firmware v2 (DRV8833, non-blocking ultrasonic) | Written, **not compiled, not uploaded**. Verify D3 / D5 / D6 / D9 give PWM |
| Tower firmware v2 | Written, **not compiled, not uploaded**. Verify the Servo library on the UNO Q core |
| UNO Q bridge programs | Logic self-tested with a fake Bridge (`--selftest`). The real Arduino Bridge API names come from community write-ups: verify against the current docs on day one |
| Gamepad thread | Not tried with a real pad. Run `python laptop/tools/gamepad_test.py`, fix the numbers in `config.py` |
| Camera | Reader written, only the simulated view was tried |
| Frame rate | Median frame about 11 ms at 1080p headless on a 16-core dev machine. Not measured on the demo laptop: if it drops under 45 fps for 3 s the game lowers post-processing by itself, F3 changes it by hand |
| Wi-Fi latency target (under 100 ms) | Unmeasured. Run `python laptop/tools/latency_test.py` against the real robot |

## Connect everything (the day-one checklist)
1. **Hotspot.** Turn on a phone hotspot, 2.4 GHz. Copy `laptop/config.local.example.json` to `laptop/config.local.json` (git-ignored) and write the name and password there for the team. Never commit it.
2. **UNO Q boards.** Power each from its power bank, join the hotspot in Arduino App Lab, upload the sketch (`robot.ino` / `tower.ino`) and start the matching `*_bridge.py` as the Python part of the same App Lab app so it runs on boot. See `firmware/README.md`.
3. **Laptop.** Join the same hotspot. Allow Python through Windows Firewall on **Private networks** (UDP 5005).
4. **Weather station.** Upload `firmware/weather_station`, plug the UNO R3 into the laptop with the USB cable. No setup: the game finds the port.
5. **Gamepad.** Pair in Windows Bluetooth settings (Xbox pad: hold the pair button until the light blinks fast).
6. **Camera.** ESP32-CAM: power it from the robot's power bank and put it on the same hotspot. The game scans the robot's subnet for port 81, or set `CAMERA_URL` (ESP32-CAM: `http://<ip>:81/stream`; phone app: the URL it shows).
7. Run `python laptop/main.py`. The status strip (Pad, Robot, Tower, Station, Camera) should turn green within 10 seconds. Open **Hardware Check** (F2 or the pad's Back button) and run every test. **READY FOR DEMO** shows only when all pass.

USB-C fallback: if a UNO Q is plugged in by USB-C and answers `I?` with `I,robot,2` or `I,tower,2`, the game uses that link too and prefers the one with the lower round trip.

## Controls
| Gamepad | Keyboard | Action |
|---|---|---|
| Left stick | Arrows / WASD | Speed and turn (robot and game get the same numbers) |
| Y | Space (or Y) | Auto-pilot on / off. The dodge overrides the stick only in the danger zone |
| B | C | Robot camera: small picture / full screen |
| X | X (or F) | Fire a test asteroid (practice mode only) |
| A | Enter | Confirm |
| Start | Esc or P | Pause. After game over: restart. **Hold 2 s: re-sync** the robot to its start mark and reset |
| Back / View | F2 | Hardware Check |
| Triggers | | Brake (down to 0.5x) and boost |
| | H / K / N | Rehearsal: force the hot zone / cold zone / back to normal |
| | F3 / F4 / F11 / M | Post-processing level / debug overlay / fullscreen / mute |
| Back + Start 1 s | Space + Esc | **Emergency stop**: robot and tower stop, game pauses. Resume releases them |

After game over the stick does nothing; only Start works. Button numbers differ by OS and driver: `laptop/tools/gamepad_test.py` prints them, put them in `config.py` (or `config.local.json`).

## Before the demo
- **Scenario.** `laptop/scenario.json`: Earth and ring, where each debris piece sits (`real: true` = put a real object there on the board), the tower position and the asteroid sector. The ring is 28 cm by default because a 40 cm ring does not fit an 80 cm board: change `ORBIT_R` and `BOARD_W / BOARD_H` in `config.py` to your real board.
- **Calibrate.** Menu > Calibrate (or `python laptop/tools/calibrate_robot.py`): drive 50 cm, turn 360, measure link delay, set the tower pan angle. It writes `V_MAX`, `W_MAX`, `SYNC_DELAY_MS`, `AIM_CENTER_DEG` to `config.local.json`.
- **Paper ball speed.** Time the ball from release to the orbit lane (target 2 to 3 s) and set `ASTEROID_SPEED` (cm/s) in `config.py`.
- **Latency.** `python laptop/tools/latency_test.py` (500 pings, min / median / p95 / max, loss). Target: median one way under 100 ms, loss under 2 percent.
- **Hardware Check** in the game, or `python laptop/tools/hardware_check.py` in a terminal (exit code 1 when anything fails).

## Protocol v2 (text lines, 115200 baud serial, one line per UDP datagram, 64 characters at most)
Full table in `docs/T-Minus_6_Game_Software_Spec.pdf` section 16. Details the spec left open, as built:
- Robot `S,angle,cm,flags`: bit0 = front stop active, **bit1 = game-over latch active** (the robot's confirmation of `X`; the laptop repeats `X` 5 times a second until it sees bit1).
- Tower `T,rest,push,ms` tunes the pusher (resent at every connect, never stored). Robot `T,temp,hum` is the optional robot air sensor.
- Zones: the game sends `Z,state` on change and every 2 s. Discovery: each UNO Q bridge broadcasts `HELLO,role,2,ip` to UDP 5005 once a second; the laptop broadcasts `WHO?` while a device is missing.

## Troubleshooting
| Problem | What to do |
|---|---|
| A dot stays red | Hover the Hardware Check row for the reason. Robot / tower: same hotspot as the laptop? Firewall allows Python on Private networks (UDP 5005)? Venue Wi-Fi isolates devices: use the phone hotspot. Set `ROBOT_ADDR` / `TOWER_ADDR` in `config.local.json` to skip discovery |
| Station not found | Check the USB cable is a data cable. Only one program can hold the port (close the Arduino Serial Monitor). Set `WEATHER_PORT` ("COM4") to force it. The UNO R3 reboots when the port opens: the scan waits 2 s |
| Yellow dot / high RTT | Over 80 ms: move the hotspot closer, use 2.4 GHz, turn the camera stream down. Run `latency_test.py` |
| Robot stops by itself | By design: 300 ms without commands, anything closer than 8 cm ahead, a game over or the emergency stop. Press Start to release |
| A wheel side goes the wrong way | Swap that module's motor wires (OUT1 / OUT2). Do not change the pins |
| Robot and screen drift apart | Hold Start 2 s to re-sync. Re-run Calibrate. Dead reckoning drifts a few cm per minute |
| Craft turns the wrong way on the screen | `ORBIT_DIR`, `SCAN_SIGN` or the sign of the turn in `config.py` |
| Camera lags or shows NO SIGNAL | Frames older than 2 s show NO SIGNAL. Lower the stream resolution, keep the camera off a weak hotspot, check `CAMERA_URL`. The game never waits for it |
| Weather LCD blank | Contrast pot on the 16-pin LCD, then the wiring in `docs/pin_map.md`. Hot / cold warnings appear at the moment the state changes |
| Lives display blank | I2C display address is 0x27 or 0x3F (the sketch tries both). Set `HAS_LIVES_LCD 1` and install LiquidCrystal I2C |
| Windows Firewall | When asked, allow Python on **Private networks**. Without it the laptop never hears the UNO Q broadcasts |
| `pygame` import errors | `pip uninstall pygame` then `pip install pygame-ce` |
| Game stutters | F3 lowers post-processing. The game does this itself under 45 fps |

## Tests
`python tests/run_tests.py` (or `pytest tests`) runs 60 automated tests in about a minute, headless, no hardware.
`python laptop/tools/soak.py --demos 3` plays full demos back to back and watches memory and threads.
The hardware triage tools are in `tests/README.md`.

## Safety and rules
Paper balls only, keep people out of the line of fire. Never join two different power supplies except their GND.
UNO Q pins are 3.3 V (the HC-SR04 ECHO needs the 1k + 2k divider). Space Apps: no recognizable minors in videos or photos.
The camera frames are never saved.
