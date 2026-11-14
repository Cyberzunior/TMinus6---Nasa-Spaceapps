"""Static checks on the Arduino sketches (they cannot be compiled here) and the UNO Q bridge self-tests."""
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def test_no_delay_calls_in_any_sketch():
    for p in (("firmware", "weather_station", "weather_station.ino"), ("firmware", "robot", "robot.ino"), ("firmware", "tower", "tower.ino")):
        code = re.sub(r"//.*", "", read(*p))
        assert not re.search(r"\bdelay\s*\(", code), p


def test_robot_uses_drv8833_pins_and_no_blocking_pulsein():
    s = read("firmware", "robot", "robot.ino")
    code = re.sub(r"//.*", "", s)
    assert "L_IN1 = 3, L_IN2 = 5, R_IN1 = 6, R_IN2 = 9" in s
    assert "AccelStepper turret(AccelStepper::HALF4WIRE, 2, 7, 4, 8)" in s
    assert "TRIG = A0, ECHO = A1, BUMP_L = A2, BUMP_R = A3, LED = 13" in s
    assert "pulseIn" not in code
    assert "SPEED_CAP = 120" in s and "CMD_TIMEOUT = 300" in s and "STOP_CM = 8" in s and "HAS_ROBOT_DHT 0" in s
    assert "TB6612" not in code and "PWMA" not in code


def test_weather_pins_and_texts_match_the_spec():
    s = read("firmware", "weather_station", "weather_station.ino")
    assert "PIN_DHT = 2, GREEN = 3, BLUE = 4, RED = 5, HIT_LED = A0, ACTIVE_BUZZ = 6, PASSIVE_BUZZ = 7" in s
    assert "LiquidCrystal weatherLcd(8, 9, 10, 11, 12, 13)" in s
    for text in ("!! HOT ZONE !!", "!! COLD ZONE !!", "MOVE AWAY NOW!", "SIGNAL LOST", "GAME OVER", "I,weather,2", "HAS_LIVES_LCD 0", "0x27", "0x3F"):
        assert text in s, text
    assert "now - tBlink >= 100" in s and "tone(PASSIVE_BUZZ, 400)" in s


def test_tower_pins_and_rules():
    s = read("firmware", "tower", "tower.ino")
    assert "PUSH_PIN = 9, PAN_PIN = 10, LED = 13, BTN = 2" in s and "MIN_GAP_MS = 1500" in s and "HAS_PAN 1" in s
    assert 'send("K")' in s and "T," in s


def test_docs_pin_map_matches_the_firmware():
    s = read("docs", "pin_map.md")
    assert "DRV8833" in s and "TB6612" not in s.split("## Tower")[0].split("## Robot")[1]


def run_bridge(role):
    p = os.path.join(ROOT, "firmware", role, "linux_bridge", role + "_bridge.py")
    r = subprocess.run([sys.executable, p, "--selftest"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "selftest OK" in r.stdout, r.stdout + r.stderr


def test_robot_bridge_selftest():
    run_bridge("robot")


def test_tower_bridge_selftest():
    run_bridge("tower")
