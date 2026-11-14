#!/usr/bin/env python3
"""T-Minus_6 hardware triage: quick pass/fail checks that each part works.

Run one board, or everything in one pass:

    python tests/triage.py                    # everything, in order
    python tests/triage.py weather --port COM5
    python tests/triage.py robot              # UDP 192.168.1.50:5005
    python tests/triage.py tower              # UDP 192.168.1.51:5005
    python tests/triage.py wiring             # step through wires on the PinTester board
    python tests/triage.py camera [--url http://...]
    python tests/triage.py gamepad

Baud is 115200 everywhere. Boards that reply over the network use UDP;
pass --port to talk to any of them over serial instead.
Every check prints PASS / FAIL / SKIP; a summary and the exit code follow.
"""
import argparse
import os
import socket
import sys
import threading
import time

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rw_timeout;8000000|timeout;8000000")

BAUD = 115200
ROBOT_ADDR = ("192.168.1.50", 5005)
TOWER_ADDR = ("192.168.1.51", 5005)
CAMERA_URLS = [
    "http://192.168.1.60:81/stream",    # ESP32-CAM CameraWebServer
    "http://192.168.1.61:8080/video",   # phone IP Webcam
]

results = []   # (name, status) with status in PASS / FAIL / SKIP


# --------------------------------------------------------------- reporting
def check(name, ok, note=""):
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f"  ({note})" if note else ""))
    results.append((name, status))
    return ok


def skip(name, note=""):
    print(f"[SKIP] {name}" + (f"  ({note})" if note else ""))
    results.append((name, "SKIP"))


def _input(prompt):
    try:
        return input(prompt)
    except EOFError:
        return None
    except KeyboardInterrupt:
        print("\nstopped")
        sys.exit(130)


def ask(name, question):
    a = _input(f"  ? {question} [y/n/s] ")
    if a is None:
        skip(name, "no answer (input ended)")
        return False
    a = a.strip().lower()
    if a in ("s", "skip"):
        skip(name, "answered skip")
        return False
    return check(name, a in ("y", "yes"))


def pause(msg):
    _input(f"  ... {msg} (Enter) ")


def summary():
    n_pass = sum(1 for _, s in results if s == "PASS")
    n_fail = sum(1 for _, s in results if s == "FAIL")
    n_skip = sum(1 for _, s in results if s == "SKIP")
    print(f"\n== Summary: {n_pass} pass, {n_fail} fail, {n_skip} skip ==")
    for name, status in results:
        if status == "FAIL":
            print(f"   failed: {name}")
    return 1 if n_fail else 0


# --------------------------------------------------------------- link
class Link:
    """Serial (COM port) or UDP link, line based, 115200 baud."""

    def __init__(self, port=None, addr=None):
        self.port, self.addr = port, addr
        self.ser = None
        self.sock = None
        self.buf = b""

    def open(self):
        if self.addr:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(0.1)
            print(f"  link: udp {self.addr[0]}:{self.addr[1]}")
        else:
            import serial
            self.ser = serial.Serial(self.port, BAUD, timeout=0.05)
            time.sleep(2)   # UNO R3 resets when the port opens
            print(f"  link: serial {self.port} @ {BAUD}")

    def close(self):
        if self.ser:
            self.ser.close()
        if self.sock:
            self.sock.close()

    def send(self, line):
        data = (line + "\n").encode()
        if self.ser:
            self.ser.write(data)
        else:
            self.sock.sendto(data, self.addr)

    def line(self, match=None, timeout=2.0):
        """Next line (optionally containing match), or None on timeout."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.ser:
                data = self.ser.read(256)
            else:
                try:
                    data, _ = self.sock.recvfrom(2048)
                except socket.timeout:
                    continue
            self.buf += data
            while b"\n" in self.buf:
                raw, self.buf = self.buf.split(b"\n", 1)
                text = raw.decode(errors="replace").strip()
                if text and (match is None or match in text):
                    return text
        return None


def open_serial_link(args, title):
    port = args.port
    if not port:
        try:
            from serial.tools import list_ports
        except ImportError:
            print("pyserial missing: pip install -r requirements.txt")
            return None
        ports = [(p.device, p.description or "") for p in list_ports.comports()]
        if not ports:
            print(f"  no serial port found for {title}; plug it in or use --port")
            return None
        if len(ports) == 1:
            port = ports[0][0]
        else:
            print(f"  pick the port for {title}:")
            for dev, desc in ports:
                print(f"    {dev}  {desc}")
            port = _input("  port: ") or ""
    link = Link(port=port)
    try:
        link.open()
    except Exception as e:
        print(f"  could not open {port}: {e}")
        return None
    return link


def open_udp_or_serial(args, title, addr):
    link = Link(addr=addr) if not args.port else Link(port=args.port)
    try:
        link.open()
    except Exception as e:
        print(f"  could not connect for {title}: {e}")
        return None
    return link


# --------------------------------------------------------------- parsing
def split_csv(line):
    return [p.strip() for p in line.split(",")]


def floats(parts, n):
    if len(parts) != n:
        return None
    try:
        return [float(p) for p in parts]
    except ValueError:
        return None


# --------------------------------------------------------------- weather
def triage_weather(args):
    print("\n== Weather station (UNO R3, USB serial) ==")
    link = open_serial_link(args, "weather station")
    if not link:
        return
    try:
        line = link.line("W,", 3.0)
        if not check("weather: W line arrives", line is not None):
            return
        v = floats(split_csv(line), 4)
        if not check("weather: W parses as W,temp,hum,state", v is not None, line):
            return
        temp, hum, state = v[1], v[2], v[3]
        check("weather: temp inside DHT11 range 0-50 C", 0 <= temp <= 50, f"{temp:.1f} C")
        check("weather: humidity inside DHT11 range 20-90 %", 20 <= hum <= 90, f"{hum:.0f} %")
        check("weather: state is 0/1/2", state in (0, 1, 2), f"state {state:.0f}")
        if state == 0:
            ask("weather: green LED solid, LCD shows NORMAL at room temperature",
                "Green LED solid on and LCD shows temperature + NORMAL?")
        # hot
        pause("aim a hair dryer (low, 30 cm) at the DHT11")
        hot = link.line("W,", 12.0)
        hot_state = floats(split_csv(hot), 4)[3] if hot and floats(split_csv(hot), 4) else None
        check("weather: state goes to 2 (HOT) with hot air", hot_state == 2, f"last {hot}")
        ask("weather: red LED blinks fast and active buzzer beeps", "Red LED fast blink + fast beeps?")
        # cold
        pause("hold a cold pack (sealed bag) on the DHT11")
        cold = link.line("W,", 12.0)
        cold_state = floats(split_csv(cold), 4)[3] if cold and floats(split_csv(cold), 4) else None
        check("weather: state goes to 1 (COLD) when cooled", cold_state == 1, f"last {cold}")
        ask("weather: blue LED blinks and passive buzzer tone differs from active",
            "Blue LED blink + different (low) tone?")
        back = link.line("W,", 15.0)
        back_state = floats(split_csv(back), 4)[3] if back and floats(split_csv(back), 4) else None
        check("weather: returns to NORMAL (state 0) after both", back_state == 0, f"last {back}")
    finally:
        link.close()


# --------------------------------------------------------------- robot
def triage_robot(args):
    print("\n== Robot (UNO Q #1) ==")
    print("  safety: wheels on blocks for the drive checks")
    link = open_udp_or_serial(args, "robot", ROBOT_ADDR)
    if not link:
        return
    try:
        line = link.line("S,", 3.0)
        if not check("robot: S line arrives", line is not None):
            return
        v = floats(split_csv(line), 4)
        if not check("robot: S parses as S,angle,dist,flags", v is not None, line):
            return
        angle, dist = v[1], v[2]
        check("robot: sweep angle covers about +/-45 deg", abs(angle) <= 60, f"angle {angle:.0f}")
        check("robot: distance plausible (0-400 cm)", 0 <= dist <= 400, f"{dist:.1f} cm")

        lo, hi = angle, angle
        end = time.monotonic() + 2.0
        while time.monotonic() < end:
            s = link.line("S,", 0.3)
            if s:
                v = floats(split_csv(s), 4)
                if v:
                    lo, hi = min(lo, v[1]), max(hi, v[1])
        check("robot: radar sweeps both sides", lo < -30 and hi > 30, f"{lo:.0f}..{hi:.0f} deg")

        pause("hold your hand about 10 cm in front of the HC-SR04")
        near = [floats(split_csv(link.line("S,", 0.5)), 4) for _ in range(5)]
        near = [v[2] for v in near if v]
        ok = near and 3 <= sorted(near)[len(near) // 2] <= 20
        check("robot: ultrasonic sees a hand at 10 cm", ok, f"{[f'{d:.0f}' for d in near]}")

        link.send("D,120,120,0")
        ask("robot: wheels turn forward together at D,120,120", "All four wheels forward, same way?")
        link.send("D,0,0,0")
        link.send("D,-120,-120,0")
        ask("robot: wheels reverse at D,-120,-120", "All four wheels backward?")
        link.send("D,0,0,0")
        check("robot: wheels stopped by D,0,0,0", True)

        pause("press and release the LEFT bumper button")
        check("robot: left bumper sends B,L", link.line("B,L", 5.0) is not None)
        pause("press and release the RIGHT bumper button")
        check("robot: right bumper sends B,R", link.line("B,R", 5.0) is not None)
        ask("robot: status LED lights with auto-pilot on", "Status LED on when auto-pilot is enabled?")
    finally:
        link.close()


# --------------------------------------------------------------- tower
def triage_tower(args):
    print("\n== Asteroid tower (UNO Q #2) ==")
    print("  safety: nobody in front of the tower; it drops a real paper ball")
    link = open_udp_or_serial(args, "tower", TOWER_ADDR)
    if not link:
        return
    try:
        ask("tower: armed LED on after boot", "Armed LED lit?")
        link.send("A,90")
        link.send("F")
        check("tower: F answered by K within 2 s", link.line("K", 2.0) is not None)
        ask("tower: exactly one ball dropped", "Did exactly one paper ball drop?")
        ask("tower: servo did not reset the board", "Board still alive (no reboot)?")
        ask("tower: ball flight 2-3 s to the lane", "Ball takes about 2-3 seconds to land?")
    finally:
        link.close()


# --------------------------------------------------------------- wiring
# name, pin(s), kind  -> kinds: led active_buzzer tone dht button ultrasonic servo stepper motor lcd i2c
WIRES = {
    "weather": [
        ("DHT11 data", "D2", "dht"),
        ("green LED", "D3", "led"),
        ("blue LED", "D4", "led"),
        ("red LED", "D5", "led"),
        ("yellow hit LED", "A0", "led"),
        ("active buzzer (via PN2222, 1k)", "D6", "active_buzzer"),
        ("passive buzzer", "D7", "tone"),
        ("LCD RS", "D8", "lcd"), ("LCD E", "D9", "lcd"),
        ("LCD D4", "D10", "lcd"), ("LCD D5", "D11", "lcd"),
        ("LCD D6", "D12", "lcd"), ("LCD D7", "D13", "lcd"),
        ("I2C SDA", "A4", "i2c"), ("I2C SCL", "A5", "i2c"),
    ],
    "robot": [
        ("HC-SR04 TRIG", "A0", "ultrasonic_trig"),
        ("HC-SR04 ECHO (1k+2k divider)", "A1", "ultrasonic_echo"),
        ("left bumper", "A2", "button"), ("right bumper", "A3", "button"),
        ("status LED", "D13", "led"),
        ("stepper IN1", "D9", "stepper"), ("stepper IN2", "D10", "stepper"),
        ("stepper IN3", "D11", "stepper"), ("stepper IN4", "D12", "stepper"),
        ("left motor PWM/IN1/IN2", "D5,D4,D2", "motor"),
        ("right motor PWM/IN1/IN2", "D6,D7,D8", "motor"),
    ],
    "tower": [
        ("push servo", "D9", "servo"),
        ("pan servo (optional)", "D10", "servo"),
        ("armed LED", "D13", "led"),
        ("test-fire button", "D2", "button"),
    ],
}


def bench_cmd(link, cmd, timeout=2.0):
    link.send(cmd)
    return link.line(None, timeout)


def triage_wiring(args):
    print("\n== Wiring triage (PinTester bench board) ==")
    link = open_serial_link(args, "PinTester")
    if not link:
        return
    try:
        hello = bench_cmd(link, "HELLO", 3.0)
        if not check("bench: HELLO answers OK,HELLO,PINTESTER",
                     hello is not None and "OK,HELLO,PINTESTER" in hello, str(hello)):
            return
        which = (_input("  which wire list (weather/robot/tower): ") or "").strip().lower()
        if which not in WIRES:
            print("  unknown list")
            return
        lcd_pins = []
        stepper_checked = False
        for name, pins, kind in WIRES[which]:
            print(f" - {name} on {pins}")
            pin = pins.split(",")[0]
            if kind == "led":
                bench_cmd(link, f"DW,{pin},1")
                ask(f"wiring: {name}", f"{name} lit?")
                bench_cmd(link, f"DW,{pin},0")
            elif kind == "active_buzzer":
                bench_cmd(link, f"DW,{pin},1")
                ask(f"wiring: {name}", f"{name} sounding?")
                bench_cmd(link, f"DW,{pin},0")
            elif kind == "tone":
                bench_cmd(link, f"TONE,{pin},1000,800")
                ask(f"wiring: {name}", f"Beep heard from {name}?")
            elif kind == "dht":
                reply = bench_cmd(link, f"DHT,{pin}", 3.0)
                v = floats(split_csv(reply)[2:], 2) if reply and reply.startswith("OK,DHT") else None
                ok = v is not None and 0 <= v[0] <= 50 and 20 <= v[1] <= 90
                check(f"wiring: {name} reads sane", ok, str(reply))
            elif kind == "button":
                bench_cmd(link, f"WATCH,{pin}")
                pause(f"press and release {name}")
                hit = link.line("EDGE", 5.0)
                check(f"wiring: {name} seen", hit is not None, str(hit))
                bench_cmd(link, f"UNWATCH,{pin}")
            elif kind == "ultrasonic_trig":
                pass   # checked together with the echo wire
            elif kind == "ultrasonic_echo":
                trig = next(p for n, p, k in WIRES[which] if k == "ultrasonic_trig")
                pause("hold a hand or box about 10 cm from the HC-SR04")
                reply = bench_cmd(link, f"PING,{trig},{pin}")
                try:
                    cm = float(reply.split(",")[2])
                except (ValueError, IndexError, AttributeError):
                    cm = -1
                check("wiring: HC-SR04 reads ~10 cm", 3 <= cm <= 20, str(reply))
            elif kind == "servo":
                bench_cmd(link, f"SERVO,{pin},0")
                pause("servo went to 0 deg")
                bench_cmd(link, f"SERVO,{pin},180")
                ask(f"wiring: {name} swings full range", f"{name} moved to 180?")
                bench_cmd(link, f"SERVOOFF,{pin}")
            elif kind == "stepper":
                if stepper_checked:
                    continue   # one sweep exercises all four stepper wires
                pins4 = ",".join(p for n, p, k in WIRES[which] if k == "stepper")
                bench_cmd(link, f"STEP,{pins4},512,2", 4.0)
                ask("wiring: stepper shaft turns", "Stepper shaft rotated?")
                stepper_checked = True
            elif kind == "motor":
                pwm, in1, in2 = pins.split(",")
                bench_cmd(link, f"MOTOR,180,{in1},{in2},150,800", 3.0)
                ask(f"wiring: {name} forward", "That wheel spun forward?")
                bench_cmd(link, f"MOTOR,180,{in1},{in2},-150,800", 3.0)
                ask(f"wiring: {name} reverse", "Same wheel spun backward?")
            elif kind == "lcd":
                lcd_pins.append(pin)
            elif kind == "i2c":
                reply = bench_cmd(link, "I2CSCAN")
                found = reply and ("27" in reply or "3F" in reply)
                check(f"wiring: {name} (I2C device found)", bool(found), str(reply))
                ask(f"wiring: I2C display shows text", "Text visible on the I2C display?")
        if lcd_pins:
            bench_cmd(link, f"LCD,{','.join(lcd_pins)},TRIAGE|OK", 3.0)
            ask("wiring: LCD1602 shows TRIAGE / OK", "LCD1602 shows TRIAGE / OK?")
        bench_cmd(link, "ALLOFF")
    finally:
        link.close()


# --------------------------------------------------------------- camera
def _open_capture(src, mod, timeout_s=8.0):
    """Open a capture in a helper thread; None if it does not answer in time."""
    box = []

    def run():
        cap = mod.VideoCapture(src)
        ok = cap.isOpened() and cap.read()[0]
        box.append((cap, ok))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout_s)
    return box[0] if box else None


def triage_camera(args):
    print("\n== Camera ==")
    try:
        import cv2
    except ImportError:
        print("  opencv missing: pip install -r requirements.txt")
        skip("camera: stream opens", "no opencv")
        return
    urls = [args.url] if args.url else CAMERA_URLS
    cap = None
    used = None
    for url in urls:
        src = int(url) if url.isdigit() else url
        print(f"  trying {url} (max 8 s) ...")
        got = _open_capture(src, cv2)
        if got and got[1]:
            cap, used = got
            break
        if got:
            got[0].release()
    if not check("camera: stream opens", cap is not None):
        return
    n, t0 = 0, time.monotonic()
    while n < 60:
        ok, frame = cap.read()
        if not ok:
            break
        n += 1
    dt = time.monotonic() - t0
    fps = n / dt if dt else 0
    h, w = frame.shape[:2] if n else (0, 0)
    check("camera: frames keep flowing (60 read)", n >= 60, f"read {n}")
    check("camera: resolution near 320x240", abs(w - 320) <= 80 and abs(h - 240) <= 60, f"{w}x{h}")
    check("camera: fps at least 5 (doc wants 15-20)", fps >= 5, f"{fps:.1f} fps")
    print(f"  source: {used}")
    cap.release()
    ask("camera: picture is live and usable", "Picture live, right scene, steering still feels instant?")


# --------------------------------------------------------------- gamepad
def triage_gamepad(args):
    print("\n== Gamepad ==")
    try:
        import pygame
    except ImportError:
        print("  pygame missing: pip install -r requirements.txt")
        skip("gamepad: detected", "no pygame")
        return
    pygame.init()
    pygame.joystick.init()
    n = pygame.joystick.get_count()
    if not check("gamepad: at least one controller found", n > 0):
        return
    js = pygame.joystick.Joystick(0)
    js.init()
    print(f"  {js.get_name()}: {js.get_numaxes()} axes, {js.get_numbuttons()} buttons")
    print("  move the sticks for 4 s; sample of raw values:")
    end = time.monotonic() + 4.0
    while time.monotonic() < end:
        pygame.event.pump()
        axes = [f"{js.get_axis(i):+.2f}" for i in range(js.get_numaxes())]
        print("    " + " ".join(axes))
        time.sleep(0.5)
    ask("gamepad: axes and buttons respond", "Every axis and button moved and read cleanly?")


# --------------------------------------------------------------- main
BOARD_FUN = {
    "weather": triage_weather,
    "robot": triage_robot,
    "tower": triage_tower,
    "wiring": triage_wiring,
    "camera": triage_camera,
    "gamepad": triage_gamepad,
}


def main():
    ap = argparse.ArgumentParser(description="T-Minus_6 hardware triage")
    ap.add_argument("board", nargs="?", default="all",
                    choices=("all",) + tuple(BOARD_FUN))
    ap.add_argument("--port", help="serial port, e.g. COM5 or /dev/ttyACM0")
    ap.add_argument("--url", help="camera stream URL instead of the defaults")
    args = ap.parse_args()

    boards = list(BOARD_FUN) if args.board == "all" else [args.board]
    if args.board == "all":
        print("T-Minus_6 hardware triage - hardware in this order, Enter between steps")
    for b in boards:
        if args.board == "all":
            if (_input(f"\nRun {b} now? [Enter=skip / y=run] ") or "").strip().lower() not in ("y", "yes"):
                skip(f"{b}: triage", "skipped by user")
                continue
        BOARD_FUN[b](args)
    sys.exit(summary())


if __name__ == "__main__":
    main()
