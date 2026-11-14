"""Case mode: acceptance tests per sector, written from docs/T-Minus_6_Project_Document.pdf.

Each sector function below follows the "Test it" lists and the "Test checklist" of the
project document. Automatic checks read the board's replies; things only a person can
judge (an LED colour, a wheel direction) are asked in the prompt panel.
Wiring (PinTester) is the wire-by-wire check from the original triage.py.
"""
import datetime
import os
import statistics
import threading
import time
import traceback
from dataclasses import dataclass

from PyQt5 import QtCore, QtGui, QtWidgets

import gamepad_io
from gui_common import (CAMERA_URLS, DEVICE_LABEL, REPORT_DIR, StopRequested, bgr_to_qimage,
                        laptop_config, open_capture, parse_line)
from gui_widgets import VideoWidget

Qt = QtCore.Qt
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
COLOURS = {PASS: "#1a7f37", FAIL: "#cf222e", SKIP: "#9a6700"}


# ============================================================ test context
class Ctx(QtCore.QObject):
    """What a sector function uses to talk to the operator and record results."""
    result = QtCore.pyqtSignal(str, str, str, str)       # sector key, check, status, note
    say = QtCore.pyqtSignal(str)
    ask_user = QtCore.pyqtSignal(str, object)            # text, [(label, value)]
    clear_prompt = QtCore.pyqtSignal()
    frame = QtCore.pyqtSignal(QtGui.QImage)
    sector_started = QtCore.pyqtSignal(str, str)
    sector_finished = QtCore.pyqtSignal(str)
    finished_all = QtCore.pyqtSignal()

    def __init__(self, links, opts):
        super().__init__()
        self.links, self.opts = links, opts
        self.stop = threading.Event()
        self.sector = ""
        self._answer = None
        self._answered = threading.Event()

    # -- called from the GUI thread
    def answer(self, value):
        self._answer = (value, time.monotonic())
        self._answered.set()

    # -- called from the test thread
    def check_stop(self):
        if self.stop.is_set():
            raise StopRequested()

    def sleep(self, seconds):
        if self.stop.wait(seconds):
            raise StopRequested()

    def _record(self, name, status, note=""):
        self.result.emit(self.sector, name, status, note)

    def check(self, name, ok, note=""):
        self._record(name, PASS if ok else FAIL, note)
        return bool(ok)

    def skip(self, name, note=""):
        self._record(name, SKIP, note)

    def need(self, key):
        link = self.links[key]
        if link.is_open:
            return link
        self._record("connection", SKIP, f"{DEVICE_LABEL[key]} is not connected")
        return None

    def prompt(self, text, buttons, until=None, timeout=None):
        """Show text with buttons. Returns (value, time). value is 'auto' when `until()` became
        true and None on timeout."""
        self.check_stop()
        self._answered.clear()
        self._answer = None
        self.ask_user.emit(text, buttons)
        end = None if timeout is None else time.monotonic() + timeout
        try:
            while True:
                self.check_stop()
                if self._answered.wait(0.05):
                    return self._answer
                if until is not None and until():
                    return ("auto", time.monotonic())
                if end is not None and time.monotonic() > end:
                    return (None, time.monotonic())
        finally:
            self.clear_prompt.emit()

    def ask(self, name, question):
        """Yes / No / Skip. Returns True, False or None (skipped)."""
        value, _ = self.prompt(question, [("Yes", "y"), ("No", "n"), ("Skip", "s")])
        if value == "y":
            self._record(name, PASS)
            return True
        if value == "n":
            self._record(name, FAIL, "operator answered no")
            return False
        self._record(name, SKIP, "skipped by operator")
        return None

    def pause(self, text):
        self.prompt(text, [("Continue", "c")])

    def wait_event(self, name, text, predicate, timeout=20.0):
        """Show text until predicate() is true. PASS when seen, FAIL on timeout, SKIP if skipped."""
        value, _ = self.prompt(text, [("Skip", "s")], until=predicate, timeout=timeout)
        if value == "auto":
            self._record(name, PASS)
            return True
        if value == "s":
            self._record(name, SKIP, "skipped by operator")
            return None
        self._record(name, FAIL, f"not seen within {timeout:.0f} s")
        return False


@dataclass
class Sector:
    key: str
    title: str
    needs: tuple
    fn: object
    blurb: str


# ============================================================ helpers
def robot_stop(link):
    for _ in range(3):
        link.send("D,0,0,0", quiet=True)


class Driver:
    """Keeps resending D,left,right,ap at 20 Hz (the robot stops 300 ms after the last one)
    while the operator answers a question, then stops the wheels."""

    def __init__(self, link, left, right, ap=0):
        self.link, self.left, self.right, self.ap = link, left, right, ap

    def __enter__(self):
        self._stop = threading.Event()
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()
        return self

    def _loop(self):
        while True:
            self.link.send(f"D,{self.left},{self.right},{self.ap}", quiet=True)
            if self._stop.wait(0.05):
                return

    def __exit__(self, *_):
        self._stop.set()
        self._th.join(1.0)
        robot_stop(self.link)
        return False


def median_or_none(values):
    return statistics.median(values) if values else None


# ============================================================ weather
def w_after(ctx, cur, sent_t, timeout=4.5):
    """First W reading that the board sent after it had processed a command sent at sent_t."""
    end = time.monotonic() + timeout
    while True:
        remaining = end - time.monotonic()
        if remaining <= 0:
            return None
        line = cur.next("W,", remaining)
        if line is None:
            return None
        if cur.last_t >= sent_t + 0.15:
            return parse_line(line, "W", 3)


def weather_sim(ctx, link, temp):
    cur = link.cursor(ctx.stop)
    link.send(f"V,{temp:g}")
    return w_after(ctx, cur, time.monotonic())


def sector_weather(ctx):
    link = ctx.need("weather")
    if not link:
        return
    try:
        link.send("R")                      # leave simulation mode, 15 lives
        ctx.say.emit("waiting for real DHT11 readings ...")
        ctx.sleep(2.5)
        cur = link.cursor(ctx.stop)
        readings = []
        for _ in range(4):
            line = cur.next("W,", 5.0)
            if line is None:
                break
            readings.append((cur.last_t, line, parse_line(line, "W", 3)))
        if not ctx.check("W line arrives", bool(readings),
                         f"{len(readings)} lines" if readings else "nothing in 5 s: check port, 115200 baud, sketch"):
            return
        if not ctx.check("W parses as W,temp,hum,state", all(r[2] for r in readings), readings[-1][1]):
            return
        gaps = [b[0] - a[0] for a, b in zip(readings, readings[1:])]
        if gaps:
            ctx.check("reports every 2 s", all(1.5 <= g <= 2.6 for g in gaps),
                      ", ".join(f"{g:.1f} s" for g in gaps))
        temp, hum, state = readings[-1][2]
        real_temp = temp
        ctx.check("DHT11 temperature in range 0-50 C", 0 <= temp <= 50, f"{temp:.1f} C")
        ctx.check("DHT11 humidity in range 20-90 %", 20 <= hum <= 90, f"{hum:.0f} %")
        ctx.check("state is 0, 1 or 2", state in (0, 1, 2), f"state {state:.0f}")
        if 19 <= temp <= 29:
            ctx.check("18-30 C reports state 0 (NORMAL)", state == 0, f"{temp:.1f} C, state {state:.0f}")
        if state == 0:
            ctx.ask("NORMAL: green LED solid, silent, LCD shows temperature",
                    "NORMAL state: is the GREEN LED solid, both buzzers silent, and does the LCD show "
                    "'T xx.xC NORMAL' on line 1 and 'H nn%' on line 2?")

        if ctx.opts.get("weather_real"):
            for label, want, how in (("hot", 2, "Aim a hair dryer (low, about 30 cm) at the DHT11"),
                                     ("cold", 1, "Hold a sealed cold pack on the DHT11")):
                cur = link.cursor(ctx.stop)
                seen = {"ok": False}

                def reached(cur=cur, want=want, seen=seen):
                    while True:
                        line = cur.next("W,", 0)
                        if line is None:
                            return seen["ok"]
                        v = parse_line(line, "W", 3)
                        if v and v[2] == want:
                            seen["ok"] = True
                            return True
                ctx.wait_event(f"real {label} air moves the sensor to state {want}",
                               f"{how}. Waiting for the state to change (up to 60 s) ...", reached, 60)
            ctx.pause("Remove the hair dryer / cold pack and let the sensor settle, then Continue.")

        # --- simulation mode (V,temp): thresholds and hysteresis from the spec
        v = weather_sim(ctx, link, 35)
        ctx.check("V,35 gives state 2 (HOT)", v is not None and v[2] == 2 and abs(v[0] - 35) < 0.2, str(v))
        ctx.ask("HOT: warning text at once, red LED fast, active buzzer fast beeps",
                "HOT state: LCD shows '!! HOT SPACE !!' / 'CREW: HEAT WARN', the RED LED blinks fast "
                "(about 5 times a second), the ACTIVE buzzer beeps fast, green LED is off?")
        v = weather_sim(ctx, link, 29.5)
        ctx.check("HOT holds at 29.5 C (clears only 1 C below 30)", v is not None and v[2] == 2, str(v))
        v = weather_sim(ctx, link, 28.5)
        ctx.check("HOT clears at 28.5 C", v is not None and v[2] == 0, str(v))

        v = weather_sim(ctx, link, 10)
        ctx.check("V,10 gives state 1 (COLD)", v is not None and v[2] == 1 and abs(v[0] - 10) < 0.2, str(v))
        ctx.ask("COLD: warning text at once, blue LED fast, passive buzzer low tone",
                "COLD state: LCD shows '!! COLD SPACE !!' / 'CREW: COLD WARN', the BLUE LED blinks fast, the "
                "PASSIVE buzzer gives a low tone, and it sounds different from the hot buzzer?")
        v = weather_sim(ctx, link, 18.5)
        ctx.check("COLD holds at 18.5 C (clears only 1 C above 18)", v is not None and v[2] == 1, str(v))
        v = weather_sim(ctx, link, 19.5)
        ctx.check("COLD clears at 19.5 C", v is not None and v[2] == 0, str(v))

        # --- lives, hit LED, game over
        link.send("H,14")
        ctx.ask("hit LED: yellow LED flashes for about 1 s", "Did the YELLOW hit LED flash for about 1 second?")
        if ctx.opts.get("i2c"):
            ctx.ask("lives display: 14 full hearts + 1 outline, 'T-Minus_6 L14/15'",
                    "I2C lives display: line 1 shows 14 full hearts and 1 outline heart, line 2 reads "
                    "'T-Minus_6 L14/15'?")
        else:
            ctx.skip("lives display shows hearts", "I2C lives display not fitted (tick the option when it is)")
        link.send("G")
        ctx.sleep(0.5)
        link.send("V,35")                   # warnings must stay quiet after game over
        ctx.sleep(0.8)
        ctx.ask("game over: SIGNAL LOST / GAME OVER, LEDs and buzzers quiet",
                "Game over (G): LCD shows 'SIGNAL LOST' / 'GAME OVER', green LED off, and with a hot "
                "temperature sent the red LED and buzzers stay quiet?")
        link.send("R")
        ctx.sleep(2.5)
        cur = link.cursor(ctx.stop)
        line = cur.next("W,", 4.0)
        v = parse_line(line, "W", 3) if line else None
        ctx.check("R ends simulation: real temperature returns", v is not None and abs(v[0] - real_temp) < 4,
                  f"{v[0]:.1f} C now, {real_temp:.1f} C before" if v else "no W line")
        ctx.ask("R: green LED back, LCD shows temperature", "After R: GREEN LED solid and the LCD shows the temperature again?")
    finally:
        link.send("R")


# ============================================================ robot
def sector_robot(ctx):
    link = ctx.need("robot")
    if not link:
        return
    ctx.pause("SAFETY: put the robot on blocks so the wheels spin in the air and keep hands clear of them. "
              "Continue when ready.")
    try:
        link.send("R")
        link.send("D,0,0,0")
        cur = link.cursor(ctx.stop)
        lines = cur.collect(3.0, "S,")
        if not ctx.check("S line arrives", bool(lines),
                         "" if lines else "nothing in 3 s: Wi-Fi, bridge program or USB fallback?"):
            return
        vals = [parse_line(t, "S", 3) for t, _ in lines]
        if not ctx.check("S parses as S,angle,dist,flags", all(vals), lines[-1][0]):
            return
        rate = len(lines) / 3.0
        ctx.check("scan rate at least 4 per second", rate >= 4, f"{rate:.1f}/s (spec target about 15/s)")

        ctx.say.emit("watching one full sweep ...")
        sweep = [parse_line(t, "S", 3) for t, _ in cur.collect(10.0, "S,")]
        sweep = [s for s in sweep if s]
        angles = [s[0] for s in sweep]
        ctx.check("sweep covers about +/-45 deg", bool(angles) and min(angles) <= -40 and max(angles) >= 40
                  and all(abs(a) <= 50 for a in angles),
                  f"{min(angles):.0f}..{max(angles):.0f} deg" if angles else "no data")
        ctx.check("distances plausible (0-400 cm)", bool(sweep) and all(0 <= s[1] <= 400 for s in sweep),
                  f"{min(s[1] for s in sweep):.0f}..{max(s[1] for s in sweep):.0f} cm" if sweep else "no data")

        # ultrasonic accuracy, forward cone only (the sensor is swinging)
        ctx.pause("Hold a flat hand about 10 cm in front of the HC-SR04 and keep it still while it sweeps. "
                  "Continue, then hold for 10 s.")
        got = [parse_line(t, "S", 3) for t, _ in cur.collect(10.0, "S,")]
        fwd = [s[1] for s in got if s and abs(s[0]) <= 15]
        med = median_or_none(fwd)
        ctx.check("ultrasonic reads about 10 cm for a hand at 10 cm", med is not None and 6 <= med <= 14,
                  f"median {med:.0f} cm of {len(fwd)} forward readings" if med is not None else "no forward readings")

        # hardware safety stop at 8 cm, always on
        ctx.pause("Now hold your hand about 5 cm from the sensor (closer than 8 cm) and keep it there. "
                  "Continue, then hold for the next steps.")
        got = [parse_line(t, "S", 3) for t, _ in cur.collect(8.0, "S,")]
        ctx.check("stop flag is set when something is closer than 8 cm",
                  any(s and s[2] >= 1 for s in got), f"flags seen: {sorted({int(s[2]) for s in got if s})}")
        with Driver(link, 120, 120):
            ctx.ask("forward drive refused with an obstacle under 8 cm",
                    "Hand still under 8 cm and the laptop commanding FORWARD: do the wheels stay still?")
        ctx.pause("Take your hand away. Continue.")
        got = [parse_line(t, "S", 3) for t, _ in cur.collect(8.0, "S,")]
        got = [s for s in got if s]
        ctx.check("stop flag clears when the path is clear", bool(got) and got[-1][2] == 0,
                  f"last flag {got[-1][2]:.0f}" if got else "no data")

        # wheels
        with Driver(link, 120, 120):
            ctx.ask("all four wheels turn forward together", "D,120,120: do ALL FOUR wheels turn forward, the same way?")
        with Driver(link, -120, -120):
            ctx.ask("all four wheels turn backward together", "D,-120,-120: do ALL FOUR wheels turn backward?")
        with Driver(link, 120, 0):
            ctx.ask("left side forward (two wheels), right side still",
                    "D,120,0: do only the two LEFT wheels turn, forward?")
        with Driver(link, 0, 120):
            ctx.ask("right side forward (two wheels), left side still",
                    "D,0,120: do only the two RIGHT wheels turn, forward?")
        with Driver(link, 120, -120):
            ctx.ask("tank turn on the spot", "D,120,-120: left side forward and right side backward (turning on the spot)?")
        link.send("D,120,120,0")                           # one command only
        ctx.ask("wheels stop by themselves 300 ms after the last command",
                "One single D,120,120 was sent: did the wheels twitch for a split second and then stop on their own?")

        # bumpers
        for side, label in (("L", "LEFT"), ("R", "RIGHT")):
            c = link.cursor(ctx.stop)
            ctx.wait_event(f"{label.lower()} bumper sends B,{side}", f"Press and release the {label} bumper button.",
                           lambda c=c, side=side: c.next(f"B,{side}", 0) is not None, 20)

        # auto-pilot LED
        link.send("D,0,0,1")
        ctx.ask("status LED steady on with auto-pilot flag", "Auto-pilot flag on (D,0,0,1): is the status LED steady ON?")
        link.send("D,0,0,0")
        ctx.ask("status LED off without the flag", "Flag cleared (D,0,0,0): is the status LED OFF?")

        # game over latch
        for _ in range(3):
            link.send("X")
            ctx.sleep(0.2)
        cur = link.cursor(ctx.stop)
        ctx.check("X: scan stops and turret parks", cur.next("S,", 2.0) is None, "no S lines for 2 s")
        ctx.ask("X: status LED blinks fast", "Game over latch (X): is the status LED blinking FAST?")
        with Driver(link, 120, 120):
            ctx.ask("X: wheel commands are ignored", "Latched, with D,120,120 being sent: do the wheels stay still?")
        link.send("R")
        cur = link.cursor(ctx.stop)
        ctx.check("R: scan resumes after reset", cur.next("S,", 4.0) is not None)
        with Driver(link, 120, 120):
            ctx.ask("R: wheels respond again", "After R, with D,120,120 being sent: do the wheels turn again?")
    finally:
        robot_stop(link)
        link.send("R")


# ============================================================ tower
def sector_tower(ctx):
    link = ctx.need("tower")
    if not link:
        return
    ctx.pause("SAFETY: nobody in the line of fire. Each fire drops a real paper ball, so load at least 4. "
              "Continue when ready.")
    try:
        link.send("R")
        ctx.sleep(0.3)
        ctx.ask("armed LED lit", "Is the ARMED LED lit?")

        cur = link.cursor(ctx.stop)
        t0 = time.monotonic()
        link.send("F")
        k = cur.next("K", 2.0)
        ctx.check("F is answered by K within 2 s", k is not None,
                  f"{(cur.last_t - t0) * 1000:.0f} ms" if k else "no K")
        ctx.check("exactly one K per F", cur.next("K", 1.5) is None)
        ctx.ask("exactly one ball dropped", "Did exactly ONE paper ball drop?")

        ctx.sleep(0.6)
        cur = link.cursor(ctx.stop)
        link.send("F")
        link.send("F")                                      # second F lands inside the push window
        ks = cur.collect(1.5, "K")
        ctx.check("a second F during the push is ignored", len(ks) == 1, f"K count {len(ks)} (drops one more ball)")

        link.send("X")
        ctx.sleep(0.4)
        cur = link.cursor(ctx.stop)
        link.send("F")
        ctx.check("disarmed (X): F is ignored", cur.next("K", 1.5) is None)
        ctx.ask("disarmed: armed LED off", "Is the ARMED LED now OFF?")
        link.send("R")
        ctx.sleep(0.4)
        cur = link.cursor(ctx.stop)
        link.send("F")
        ctx.check("re-armed (R): F answered again", cur.next("K", 2.0) is not None)
        ctx.sleep(0.8)

        cur = link.cursor(ctx.stop)
        ctx.wait_event("test-fire button fires (K)", "Press the tower's test-fire button once.",
                       lambda: cur.next("K", 0) is not None, 20)
        ctx.ask("button fired exactly one ball, board did not reset",
                "Did the button drop exactly one ball, and is the ARMED LED still lit (the servo did not reset the board)?")

        ctx.pause("Ball flight timing. Continue, the tower fires, then click 'Ball landed' the moment the ball "
                  "reaches the orbit lane.")
        cur = link.cursor(ctx.stop)
        t0 = time.monotonic()
        link.send("F")
        if cur.next("K", 2.0) is not None:
            t0 = cur.last_t
        value, t = ctx.prompt("Ball released. Click when it reaches the orbit lane.",
                              [("Ball landed", "m"), ("Skip", "s")], timeout=15)
        if value == "m":
            dt = t - t0
            ctx.check("ball flight takes 2-3 s to the lane", 2.0 <= dt <= 3.0, f"{dt:.1f} s")
        else:
            ctx.skip("ball flight takes 2-3 s to the lane", "not timed")

        if ctx.opts.get("pan"):
            for angle in (0, 90, 180):
                link.send(f"A,{angle}")
                ctx.ask(f"pan servo moves to {angle} deg", f"A,{angle}: did the tower turn to {angle} deg (0 and 180 are the two ends)?")
        else:
            ctx.skip("pan servo aims", "optional pan servo not fitted")
    finally:
        link.send("R")


# ============================================================ camera
def sector_camera(ctx):
    try:
        import cv2
    except ImportError:
        ctx.skip("opencv installed", "pip install -r tests/requirements.txt")
        return
    url = (ctx.opts.get("camera_url") or "").strip()
    urls = [url] if url else CAMERA_URLS
    ctx.pause("Point the camera at the table only. Nobody under 18 may appear in the picture "
              "(event rule). Continue.")
    cap, used = None, None
    for u in urls:
        ctx.say.emit(f"trying {u} (max 8 s) ...")
        cap = open_capture(int(u) if u.isdigit() else u, cv2, 8.0, ctx.stop)
        if cap is not None:
            used = u
            break
    if not ctx.check("stream opens", cap is not None, used or "tried " + ", ".join(urls)):
        return
    prev_stop = threading.Event()
    th = None
    try:
        n, t0, w, h = 0, time.monotonic(), 0, 0
        while n < 60:
            ctx.check_stop()
            ok, frame = cap.read()
            if not ok:
                break
            n += 1
            h, w = frame.shape[:2]
            if n % 3 == 0:
                ctx.frame.emit(bgr_to_qimage(frame))
        fps = n / max(1e-6, time.monotonic() - t0)
        ctx.check("60 frames keep flowing", n >= 60, f"read {n}")
        ctx.check("picture size near 320x240", abs(w - 320) <= 80 and abs(h - 240) <= 60, f"{w}x{h}")
        ctx.check("at least 15 fps (spec 15-20)", fps >= 15, f"{fps:.1f} fps")

        def preview():
            while not prev_stop.is_set():
                ok2, fr = cap.read()
                if not ok2:
                    return
                ctx.frame.emit(bgr_to_qimage(fr))
        th = threading.Thread(target=preview, daemon=True)
        th.start()
        ctx.ask("picture is live and shows the table", "Is the preview live and showing the table?")
        ctx.ask("delay is short (spec: a tenth to a third of a second)",
                "Hold a phone stopwatch in front of the camera. Is the preview within about 0.3 s of the real "
                "stopwatch, and does it keep up while you move your hand?")
    finally:
        prev_stop.set()
        if th is not None:
            th.join(2.0)
        cap.release()


# ============================================================ gamepad
def sector_gamepad(ctx):
    if not gamepad_io.available():
        ctx.skip("pygame installed", "pip install -r tests/requirements.txt")
        return
    cfg = laptop_config()
    pads = gamepad_io.rescan()
    if not ctx.check("a controller is found", bool(pads),
                     pads[0][1] if pads else "pair it over Bluetooth, wake it, run again"):
        return
    gamepad_io.select(0)
    st = gamepad_io.read()
    if not ctx.check("controller opens", st is not None):
        return
    ctx.check("has at least 2 axes (left stick)", len(st["axes"]) >= 2, f"{len(st['axes'])} axes")
    ctx.check(f"has at least {cfg['BTN_RESTART'] + 1} buttons (Start is {cfg['BTN_RESTART']})",
              len(st["buttons"]) > cfg["BTN_RESTART"], f"{len(st['buttons'])} buttons")

    ctx.pause("Leave the sticks and triggers alone, then Continue (1 s measurement).")
    drift = 0.0
    end = time.monotonic() + 1.0
    while time.monotonic() < end:
        s = gamepad_io.read()
        if s:
            for i in (cfg["AXIS_TURN"], cfg["AXIS_SPEED"]):
                if i < len(s["axes"]):
                    drift = max(drift, abs(s["axes"][i]))
        ctx.sleep(0.02)
    ctx.check(f"left stick rests inside the {cfg['DEAD_ZONE'] * 100:.0f}% dead zone", drift < cfg["DEAD_ZONE"],
              f"largest rest value {drift:.3f}")

    def axis(i):
        s = gamepad_io.read()
        return s["axes"][i] if s and i < len(s["axes"]) else 0.0

    for label, i, sign in (("LEFT", cfg["AXIS_TURN"], -1), ("RIGHT", cfg["AXIS_TURN"], 1),
                           ("UP", cfg["AXIS_SPEED"], -1), ("DOWN", cfg["AXIS_SPEED"], 1)):
        ctx.wait_event(f"left stick {label} reaches full travel",
                       f"Push the LEFT stick fully {label} and hold it there.",
                       lambda i=i, sign=sign: sign * axis(i) > 0.8, 15)
        ctx.sleep(0.4)

    for label, key in (("Y", "BTN_AUTOPILOT"), ("B", "BTN_CAMERA"), ("Start", "BTN_RESTART")):
        prev = [1] * 64
        pressed = []

        def pred(prev=prev, pressed=pressed):
            s = gamepad_io.read()
            if not s:
                return False
            for i, b in enumerate(s["buttons"]):
                if b and not prev[i]:
                    pressed.append(i)
            prev[:len(s["buttons"])] = s["buttons"]
            return bool(pressed)
        pred()      # swallow buttons that are already held
        pressed.clear()
        value, _ = ctx.prompt(f"Press the {label} button once.", [("Skip", "s")], until=pred, timeout=20)
        name = f"{label} button is number {cfg[key]} (laptop/config.py)"
        if value == "auto":
            ctx.check(name, pressed[0] == cfg[key], f"pressed {pressed[0]}, config.py has {cfg[key]}")
        elif value == "s":
            ctx.skip(name, "skipped by operator")
        else:
            ctx.check(name, False, "no button pressed in 20 s")
        ctx.sleep(0.5)


# ============================================================ wiring (PinTester)
def sector_wiring(ctx):
    link = ctx.need("bench")
    if not link:
        return
    from triage import WIRES

    def cmd(text, timeout=2.0):
        cur = link.cursor(ctx.stop)
        link.send(text)
        end = time.monotonic() + timeout
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                return None
            line = cur.next(None, remaining)
            if line is None:
                return None
            if line.startswith(("OK,", "ERR,")):
                return line

    def wait_done(what, timeout):
        cur = link.cursor(ctx.stop)
        cur.next(f"DONE,{what}", timeout)

    hello = cmd("HELLO", 3.0)
    if not ctx.check("HELLO answers OK,HELLO,PINTESTER", hello is not None and "OK,HELLO,PINTESTER" in hello, str(hello)):
        return
    which = ctx.opts.get("wire_list", "weather")
    wires = WIRES[which]
    lcd_pins, stepper_done, i2c_done = [], False, False
    try:
        for name, pins, kind in wires:
            pin = pins.split(",")[0]
            label = f"{which}: {name} on {pins}"
            if kind == "led":
                cmd(f"DW,{pin},1")
                ctx.ask(label, f"{name} (pin {pin}) lit?")
                cmd(f"DW,{pin},0")
            elif kind == "active_buzzer":
                cmd(f"DW,{pin},1")
                ctx.ask(label, f"{name} (pin {pin}) sounding?")
                cmd(f"DW,{pin},0")
            elif kind == "tone":
                cmd(f"TONE,{pin},1000,2500")
                ctx.ask(label, f"Beep heard from {name} (pin {pin})?")
            elif kind == "dht":
                reply = cmd(f"DHT,{pin}", 3.0)
                v = None
                if reply and reply.startswith("OK,DHT"):
                    try:
                        v = [float(x) for x in reply.split(",")[2:4]]
                    except ValueError:
                        v = None
                ctx.check(label + " reads sane", v is not None and 0 <= v[0] <= 50 and 20 <= v[1] <= 90, str(reply))
            elif kind == "button":
                cmd(f"WATCH,{pin}")
                cur = link.cursor(ctx.stop)
                ctx.wait_event(label + " seen", f"Press and release {name} (pin {pin}).",
                               lambda cur=cur: cur.next("EDGE", 0) is not None, 20)
                cmd(f"UNWATCH,{pin}")
            elif kind == "ultrasonic_trig":
                continue            # checked together with the echo wire
            elif kind == "ultrasonic_echo":
                trig = next(p for n, p, k in wires if k == "ultrasonic_trig")
                ctx.pause("Hold a hand or box about 10 cm from the HC-SR04, then Continue.")
                reply = cmd(f"PING,{trig},{pin}", 3.0)
                try:
                    cm = float(reply.split(",")[2])
                except (ValueError, IndexError, AttributeError):
                    cm = -1
                ctx.check("HC-SR04 TRIG+ECHO reads about 10 cm", 3 <= cm <= 20, str(reply))
            elif kind == "servo":
                cmd(f"SERVO,{pin},0")
                ctx.sleep(1.0)
                cmd(f"SERVO,{pin},180")
                ctx.ask(label, f"{name}: did the servo sweep 0 to 180 deg?")
                cmd(f"SERVOOFF,{pin}")
            elif kind == "stepper":
                if stepper_done:
                    continue        # one move exercises all four stepper wires
                pins4 = ",".join(p for n, p, k in wires if k == "stepper")
                cmd(f"STEP,{pins4},512,2", 4.0)
                wait_done("STEP", 4.0)
                ctx.ask(f"{which}: stepper shaft turns (IN1-IN4)", "Did the stepper shaft rotate?")
                stepper_done = True
            elif kind == "motor":
                pwm, in1, in2 = pins.split(",")
                cmd(f"MOTOR,{pwm},{in1},{in2},150,1500", 3.0)
                ctx.ask(label + " forward", "Wheels on blocks: did that side spin FORWARD?")
                wait_done("MOTOR", 3.0)
                cmd(f"MOTOR,{pwm},{in1},{in2},-150,1500", 3.0)
                ctx.ask(label + " reverse", "Did the same side spin BACKWARD?")
                wait_done("MOTOR", 3.0)
            elif kind == "lcd":
                lcd_pins.append(pin)
            elif kind == "i2c":
                if i2c_done:
                    continue
                i2c_done = True
                reply = cmd("I2CSCAN") or ""
                found = [a for a in ("0x27", "0x3F") if a in reply.upper().replace("0X", "0x")]
                if not ctx.check(f"{which}: I2C device found (SDA + SCL)", bool(found), reply):
                    continue
                shown = cmd(f"LCDI2C,{found[0]},I2C|OK", 3.0) or ""
                if "disabled" in shown:
                    ctx.skip(f"{which}: I2C display shows text", "PinTester built without USE_LCD_I2C")
                else:
                    ctx.ask(f"{which}: I2C display shows text", "Does the I2C display show 'I2C' / 'OK'?")
        if lcd_pins:
            cmd(f"LCD,{','.join(lcd_pins)},TRIAGE|OK", 3.0)
            ctx.ask(f"{which}: LCD1602 data wires (RS, E, D4-D7)", "Does the LCD1602 show 'TRIAGE' / 'OK'?")
    finally:
        link.send("ALLOFF")


SECTORS = [
    Sector("weather", "Weather station (UNO R3)", ("weather",), sector_weather,
           "DHT11, hot/cold states and hysteresis, LCD, LEDs, buzzers, hit LED, game over."),
    Sector("robot", "Robot (UNO Q #1)", ("robot",), sector_robot,
           "Scan stream, radar sweep, 8 cm safety stop, four wheels, 300 ms timeout, bumpers, LED, latch."),
    Sector("tower", "Asteroid tower (UNO Q #2)", ("tower",), sector_tower,
           "Fire and K reply, one ball per shot, disarm, test button, 2-3 s ball flight."),
    Sector("camera", "Robot camera", (), sector_camera,
           "Stream opens, 320x240, 15-20 fps, live picture and delay."),
    Sector("gamepad", "Bluetooth gamepad", (), sector_gamepad,
           "Controller found, stick rest and travel, Y / B / Start button numbers match config.py."),
    Sector("wiring", "Wiring (PinTester bench board)", ("bench",), sector_wiring,
           "Wire by wire: LEDs, buzzers, DHT, buttons, ultrasonic, servo, stepper, motors, LCD, I2C."),
]


class Runner(threading.Thread):
    def __init__(self, ctx, sectors):
        super().__init__(daemon=True)
        self.ctx, self.sectors = ctx, sectors

    def run(self):
        ctx = self.ctx
        for sec in self.sectors:
            ctx.sector = sec.key
            ctx.sector_started.emit(sec.key, sec.title)
            try:
                sec.fn(ctx)
            except StopRequested:
                break
            except Exception as e:      # noqa: BLE001 - a crashing test must not kill the run
                traceback.print_exc()
                ctx.check("test crashed", False, f"{type(e).__name__}: {e}")
            finally:
                ctx.sector_finished.emit(sec.key)
        ctx.finished_all.emit()


# ============================================================ UI
class CaseMode(QtWidgets.QWidget):
    def __init__(self, shared):
        super().__init__()
        self.shared = shared
        self.ctx = None
        self.runner = None
        self.items = {}         # sector key -> tree item
        self.results = {}       # sector key -> [(check, status, note)]
        self.titles = {s.key: s.title for s in SECTORS}

        root = QtWidgets.QHBoxLayout(self)
        # ---- left: what to run
        left = QtWidgets.QVBoxLayout()
        left.addWidget(QtWidgets.QLabel("Sectors to test"))
        self.list = QtWidgets.QListWidget()
        for s in SECTORS:
            it = QtWidgets.QListWidgetItem(s.title)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            it.setToolTip(s.blurb)
            it.setData(Qt.UserRole, s.key)
            self.list.addItem(it)
        self.list.setMaximumHeight(170)
        left.addWidget(self.list)

        opts = QtWidgets.QGroupBox("Options")
        ol = QtWidgets.QVBoxLayout(opts)
        self.o_real = QtWidgets.QCheckBox("Weather: real hot/cold air")
        self.o_real.setToolTip("Also test the DHT11 with a hair dryer and a cold pack (adds about a minute)")
        self.o_pan = QtWidgets.QCheckBox("Tower: pan servo fitted")
        self.o_i2c = QtWidgets.QCheckBox("Weather: I2C lives display fitted")
        ol.addWidget(self.o_real)
        ol.addWidget(self.o_pan)
        ol.addWidget(self.o_i2c)
        self.o_wire = QtWidgets.QComboBox()
        self.o_wire.addItems(["weather", "robot", "tower"])
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Wiring list"))
        row.addWidget(self.o_wire, 1)
        ol.addLayout(row)
        left.addWidget(opts)

        self.run_btn = QtWidgets.QPushButton("Run selected")
        self.run_btn.setMinimumHeight(40)
        self.run_btn.setStyleSheet("background:#238636; color:white; font-weight:bold;")
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        clear = QtWidgets.QPushButton("Clear results")
        save = QtWidgets.QPushButton("Save report")
        left.addWidget(self.run_btn)
        left.addWidget(self.stop_btn)
        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(clear)
        row2.addWidget(save)
        left.addLayout(row2)
        left.addStretch(1)
        lw = QtWidgets.QWidget()
        lw.setLayout(left)
        lw.setMaximumWidth(320)
        root.addWidget(lw)

        # ---- right: prompt + results
        right = QtWidgets.QVBoxLayout()
        self.prompt_box = QtWidgets.QFrame()
        self.prompt_box.setStyleSheet("QFrame#prompt{background:#eef2f8; border:1px solid #c5cedb; border-radius:6px;}")
        self.prompt_box.setObjectName("prompt")
        pl = QtWidgets.QVBoxLayout(self.prompt_box)
        self.prompt_text = QtWidgets.QLabel("Pick sectors and press Run. Connect the devices first (left panel).")
        self.prompt_text.setWordWrap(True)
        f = self.prompt_text.font()
        f.setPointSize(13)
        self.prompt_text.setFont(f)
        pl.addWidget(self.prompt_text)
        self.btn_row = QtWidgets.QHBoxLayout()
        pl.addLayout(self.btn_row)
        self.progress = QtWidgets.QLabel("")
        self.progress.setStyleSheet("color:#666;")
        pl.addWidget(self.progress)
        right.addWidget(self.prompt_box)

        split = QtWidgets.QSplitter(Qt.Horizontal)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Check", "Result", "Note"])
        self.tree.setColumnWidth(0, 340)
        self.tree.setColumnWidth(1, 60)
        self.tree.setRootIsDecorated(True)
        split.addWidget(self.tree)
        self.video = VideoWidget()
        self.video.setMinimumSize(240, 180)
        self.video.hide()
        split.addWidget(self.video)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        right.addWidget(split, 1)
        self.summary = QtWidgets.QLabel("no results yet")
        right.addWidget(self.summary)
        root.addLayout(right, 1)

        self.run_btn.clicked.connect(self.run_selected)
        self.stop_btn.clicked.connect(self.stop_run)
        clear.clicked.connect(self.clear_results)
        save.clicked.connect(self.save_report)
        for key, val in (("Y", "y"), ("N", "n"), ("S", "s"), ("Return", "c")):
            sc = QtWidgets.QShortcut(QtGui.QKeySequence(key), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(lambda val=val: self._click_value(val))

    # ---- run control
    @property
    def running(self):
        return self.runner is not None and self.runner.is_alive()

    def options(self):
        return {"weather_real": self.o_real.isChecked(), "pan": self.o_pan.isChecked(),
                "i2c": self.o_i2c.isChecked(), "wire_list": self.o_wire.currentText(),
                "camera_url": self.shared.camera_url()}

    def run_selected(self):
        if self.running:
            return
        chosen = [s for s in SECTORS
                  if self.list.item(SECTORS.index(s)).checkState() == Qt.Checked]
        if not chosen:
            self.prompt_text.setText("Tick at least one sector.")
            return
        ctx = Ctx(self.shared.links, self.options())
        ctx.result.connect(self._on_result)
        ctx.say.connect(self._on_say)
        ctx.ask_user.connect(self._show_prompt)
        ctx.clear_prompt.connect(self._hide_prompt)
        ctx.frame.connect(self._on_frame)
        ctx.sector_started.connect(self._on_sector_started)
        ctx.sector_finished.connect(self._on_sector_finished)
        ctx.finished_all.connect(self._on_finished)
        self.ctx = ctx
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.runner = Runner(ctx, chosen)
        self.runner.start()

    def stop_run(self):
        if self.ctx is not None and self.running:
            self.ctx.stop.set()
            self.progress.setText("stopping ...")

    # ---- slots (GUI thread)
    def _on_say(self, text):
        self.progress.setText(text)
        self.shared.log(f"[case] {text}")

    def _on_sector_started(self, key, title):
        old = self.items.pop(key, None)
        if old is not None:
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(old))
        item = QtWidgets.QTreeWidgetItem([title, "", ""])
        f = item.font(0)
        f.setBold(True)
        item.setFont(0, f)
        self.tree.addTopLevelItem(item)
        item.setExpanded(True)
        self.items[key] = item
        self.results[key] = []
        self.progress.setText(f"running: {title}")
        self.shared.log(f"[case] === {title} ===")

    def _on_result(self, key, name, status, note):
        item = self.items.get(key)
        if item is None:
            return
        child = QtWidgets.QTreeWidgetItem([name, status, note])
        child.setForeground(1, QtGui.QBrush(QtGui.QColor(COLOURS[status])))
        item.addChild(child)
        self.results[key].append((name, status, note))
        self._update_sector(key)
        self.tree.scrollToItem(child)
        self.shared.log(f"[case] {status} {self.titles.get(key, key)}: {name}" + (f" ({note})" if note else ""))
        self._update_summary()

    def _update_sector(self, key):
        rs = self.results[key]
        p = sum(1 for r in rs if r[1] == PASS)
        fl = sum(1 for r in rs if r[1] == FAIL)
        sk = sum(1 for r in rs if r[1] == SKIP)
        item = self.items[key]
        item.setText(1, "FAIL" if fl else ("PASS" if p else "SKIP"))
        colour = COLOURS[FAIL] if fl else (COLOURS[PASS] if p else COLOURS[SKIP])
        item.setForeground(1, QtGui.QBrush(QtGui.QColor(colour)))
        item.setText(2, f"{p} pass, {fl} fail, {sk} skip")

    def _on_sector_finished(self, key):
        if key == "camera":
            self.video.hide()
            self.video.clear_image()

    def _on_frame(self, img):
        if not self.video.isVisible():
            self.video.show()
        self.video.set_image(img)

    def _on_finished(self):
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._hide_prompt()
        self.progress.setText("")
        self.prompt_text.setText("Done. Review the results, save a report, or run again.")
        self._update_summary()

    def _update_summary(self):
        allr = [r for rs in self.results.values() for r in rs]
        p = sum(1 for r in allr if r[1] == PASS)
        fl = sum(1 for r in allr if r[1] == FAIL)
        sk = sum(1 for r in allr if r[1] == SKIP)
        self.summary.setText(f"{p} pass   {fl} fail   {sk} skip")
        self.summary.setStyleSheet(f"font-weight:bold; color:{COLOURS[FAIL] if fl else COLOURS[PASS]};")

    # ---- prompt panel
    def _show_prompt(self, text, buttons):
        self.prompt_text.setText(text)
        self._clear_buttons()
        styles = {"y": "#238636", "c": "#238636", "m": "#238636", "n": "#b3261e"}
        for label, value in buttons:
            b = QtWidgets.QPushButton(label)
            b.setMinimumHeight(36)
            b.setProperty("value", value)
            if value in styles:
                b.setStyleSheet(f"background:{styles[value]}; color:white; font-weight:bold;")
            b.clicked.connect(lambda _, v=value: self.ctx.answer(v))
            self.btn_row.addWidget(b)
        self.btn_row.addStretch(1)

    def _clear_buttons(self):
        while self.btn_row.count():
            it = self.btn_row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _hide_prompt(self):
        self._clear_buttons()
        self.prompt_text.setText("working ...")

    def _click_value(self, value):
        for i in range(self.btn_row.count()):
            w = self.btn_row.itemAt(i).widget()
            if w is not None and w.property("value") == value and self.ctx is not None:
                self.ctx.answer(value)
                return

    # ---- results
    def clear_results(self):
        if self.running:
            return
        self.tree.clear()
        self.items.clear()
        self.results.clear()
        self.summary.setText("no results yet")

    def save_report(self):
        if not self.results:
            self.progress.setText("nothing to save yet")
            return
        os.makedirs(REPORT_DIR, exist_ok=True)
        now = datetime.datetime.now()
        path = os.path.join(REPORT_DIR, now.strftime("triage_%Y%m%d_%H%M%S.txt"))
        lines = [f"T-Minus_6 hardware triage report, {now:%Y-%m-%d %H:%M:%S}", ""]
        for s in SECTORS:
            if s.key not in self.results:
                continue
            lines.append(s.title)
            for name, status, note in self.results[s.key]:
                lines.append(f"  [{status}] {name}" + (f"  ({note})" if note else ""))
            lines.append("")
        lines.append(self.summary.text().strip())
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        self.progress.setText(f"report saved: {path}")
        self.shared.log(f"[case] report saved: {path}")
