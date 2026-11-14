"""Func mode: barebones, hands-on control of each part.

Stepper / servo / LCD sliders talk to the PinTester sketch on a spare UNO (the
production firmware has no commands for them). Tower, robot and weather talk to
their own firmware using the line protocol from docs/T-Minus_6_Project_Document.pdf.
"""
import math
import re
import threading
import time
from collections import deque

from PyQt5 import QtCore, QtGui, QtWidgets

import gamepad_io
from gui_common import (DEVICE_LABEL, bgr_to_qimage, laptop_config, open_capture, parse_line)
from gui_widgets import CubeWidget, RadarWidget, SparkLine, VideoWidget

Qt = QtCore.Qt
PIN_RE = re.compile(r"^[DdAa]?\d{1,2}$")
WARN_STYLE = "background:#fff4d6; color:#7a5200; padding:6px; border-radius:4px;"
HINT_STYLE = "color:#666;"


def hint(text):
    lab = QtWidgets.QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet(HINT_STYLE)
    return lab


def big(text, px=28, bold=True):
    lab = QtWidgets.QLabel(text)
    f = lab.font()
    f.setPixelSize(px)
    f.setBold(bold)
    lab.setFont(f)
    return lab


class FuncTab(QtWidgets.QWidget):
    """A tab whose body is greyed out (with a banner) until its devices are connected."""
    needs = ()      # link keys that must be open

    def __init__(self, shared):
        super().__init__()
        self.shared = shared
        self.links = shared.links
        outer = QtWidgets.QVBoxLayout(self)
        self.banner = QtWidgets.QLabel()
        self.banner.setStyleSheet(WARN_STYLE)
        self.banner.setWordWrap(True)
        outer.addWidget(self.banner)
        self.body = QtWidgets.QWidget()
        outer.addWidget(self.body, 1)

    def watch(self, *keys):
        for k in keys:
            self.links[k].state_changed.connect(self._refresh)

    def ready(self):
        return all(self.links[k].is_open for k in self.needs)

    def missing(self):
        return [k for k in self.needs if not self.links[k].is_open]

    def finish_init(self):
        self.watch(*self.needs)
        self._refresh()

    def _refresh(self, *_):
        ok = self.ready()
        self.body.setEnabled(ok)
        self.banner.setVisible(not ok)
        names = ", ".join(DEVICE_LABEL[k] for k in self.missing())
        self.banner.setText(f"Not connected: {names}. Connect it in the Connections panel.")
        self.on_ready_changed(ok)

    def on_ready_changed(self, ok):
        pass

    def stop_motion(self):
        """Called by STOP ALL and when the app closes."""

    def deactivate(self):
        """Called when the user leaves Func mode: nothing that moves may keep running."""


# --------------------------------------------------------------------- stepper
class StepperTab(FuncTab):
    needs = ("bench",)
    PER_MS = 2          # ms per half step

    def __init__(self, shared):
        super().__init__(shared)
        self.cur = self.target = 0
        self.busy = False
        self.moving = 0
        self.deadline = 0.0

        lay = QtWidgets.QVBoxLayout(self.body)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Pins IN1-IN4"))
        self.pins = QtWidgets.QLineEdit("D9,D10,D11,D12")
        row.addWidget(self.pins, 1)
        off = QtWidgets.QPushButton("Release coils")
        off.clicked.connect(self.stop_motion)
        row.addWidget(off)
        lay.addLayout(row)

        self.slider = QtWidgets.QSlider(Qt.Horizontal)
        self.slider.setRange(-4096, 4096)        # raw half steps, 4096 = one turn
        lay.addWidget(self.slider)
        self.label = big("0 steps", 22)
        lay.addWidget(self.label)
        self.status = QtWidgets.QLabel("idle")
        lay.addWidget(self.status)
        lay.addStretch(1)

        self.slider.valueChanged.connect(self._changed)
        self.slider.sliderReleased.connect(self._commit)
        self.links["bench"].line_received.connect(self._on_line)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)
        self.finish_init()

    def _changed(self, v):
        self.label.setText(f"{v} steps   (shaft at {self.cur})")
        if not self.slider.isSliderDown():
            self._commit()

    def _commit(self):
        self.target = self.slider.value()

    def _tick(self):
        if not self.ready():
            return
        now = time.monotonic()
        if self.busy and now > self.deadline:
            self.busy = False
            self.status.setText("no DONE from the board (timeout)")
        if self.busy or self.target == self.cur:
            return
        pins = self.pins.text().replace(" ", "").upper()
        parts = pins.split(",")
        if len(parts) != 4 or not all(PIN_RE.match(p) for p in parts):
            self.status.setText("pins must be four like D9,D10,D11,D12")
            self.target = self.cur
            return
        delta = self.target - self.cur
        if self.links["bench"].send(f"STEP,{pins},{delta},{self.PER_MS}"):
            self.busy, self.moving = True, delta
            self.deadline = now + abs(delta) * self.PER_MS / 1000.0 + 3.0
            self.status.setText(f"moving {delta:+d} steps ...")

    def _on_line(self, line):
        if line.startswith("DONE,STEP"):
            self.cur += self.moving
            self.busy = False
            self.status.setText("idle")
            self.label.setText(f"{self.slider.value()} steps   (shaft at {self.cur})")
        elif line.startswith("ERR,STEP,busy"):
            self.busy = True
            self.deadline = time.monotonic() + 1.0
        elif line.startswith("ERR,STEP"):
            self.busy = False
            self.target = self.cur
            self.status.setText(line)

    def stop_motion(self):
        if self.links["bench"].send("ALLOFF"):
            self.busy = False
            self.target = self.cur
            self.status.setText("coils released")

# ----------------------------------------------------------------------- servo
class ServoTab(FuncTab):
    needs = ()

    def __init__(self, shared):
        super().__init__(shared)
        self.pending = None
        lay = QtWidgets.QVBoxLayout(self.body)
        lay.addWidget(hint("SG90 servo. Bench mode drives any pin through the PinTester sketch "
                           "(power the servo from its own 5 V, share GND). The tower's push servo is "
                           "fired from the Tower tab; only its optional pan servo takes angles."))
        row = QtWidgets.QHBoxLayout()
        self.target = QtWidgets.QComboBox()
        self.target.addItem("Bench board: SERVO,pin,angle", "bench")
        self.target.addItem("Tower pan servo: A,angle (needs HAS_PAN 1)", "tower")
        self.pin = QtWidgets.QComboBox()
        self.pin.setEditable(True)
        self.pin.addItems([f"D{i}" for i in (9, 10, 3, 5, 6, 11, 2, 4, 7, 8, 12, 13)])
        row.addWidget(self.target, 1)
        row.addWidget(QtWidgets.QLabel("Pin"))
        row.addWidget(self.pin)
        lay.addLayout(row)

        self.slider = QtWidgets.QSlider(Qt.Horizontal)
        self.slider.setRange(0, 180)
        self.slider.setValue(90)
        self.slider.setTickInterval(30)
        self.slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        lay.addWidget(self.slider)
        self.angle_lab = big("90 deg", 36)
        lay.addWidget(self.angle_lab)

        btns = QtWidgets.QHBoxLayout()
        for a in (0, 45, 90, 135, 180):
            b = QtWidgets.QPushButton(f"{a}")
            b.clicked.connect(lambda _, a=a: self.slider.setValue(a))
            btns.addWidget(b)
        detach = QtWidgets.QPushButton("Detach (SERVOOFF)")
        detach.clicked.connect(self._detach)
        btns.addWidget(detach)
        lay.addLayout(btns)
        self.status = QtWidgets.QLabel("")
        lay.addWidget(self.status)
        lay.addStretch(1)

        self.slider.valueChanged.connect(self._changed)
        self.target.currentIndexChanged.connect(self._refresh)
        self.links["bench"].line_received.connect(self._on_line)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._flush)
        self.timer.start(40)        # at most 25 commands a second while dragging
        self.watch("bench", "tower")
        self._refresh()

    def _key(self):
        return self.target.currentData()

    def ready(self):
        return self.links[self._key()].is_open

    def missing(self):
        return [self._key()] if not self.ready() else []

    def on_ready_changed(self, ok):
        self.pin.setEnabled(self._key() == "bench")

    def _changed(self, v):
        self.angle_lab.setText(f"{v} deg")
        self.pending = v

    def _flush(self):
        if self.pending is None or not self.ready():
            return
        v, self.pending = self.pending, None
        if self._key() == "bench":
            pin = self.pin.currentText().strip().upper()
            if not PIN_RE.match(pin):
                self.status.setText("bad pin")
                return
            self.links["bench"].send(f"SERVO,{pin},{v}", quiet=True)
        else:
            self.links["tower"].send(f"A,{v}", quiet=True)

    def _detach(self):
        if self._key() == "bench":
            self.links["bench"].send(f"SERVOOFF,{self.pin.currentText().strip().upper()}")
        else:
            self.status.setText("the tower has no detach command")

    def _on_line(self, line):
        if line.startswith("ERR,"):
            self.status.setText(line)
        elif line.startswith("OK,SERVO"):
            self.status.setText("")

    def stop_motion(self):
        if self.links["bench"].is_open:
            self.links["bench"].send("ALLOFF")


# ------------------------------------------------------------------------- LCD
class LcdTab(FuncTab):
    needs = ("bench",)
    TARGETS = [
        ("Weather LCD1602, 16-pin (RS,E,D4,D5,D6,D7 = D8..D13)", "pins", "D8,D9,D10,D11,D12,D13"),
        ("Lives display, I2C 16x2", "i2c", "0x27"),
        ("Custom 16-pin wiring", "pins", "D8,D9,D10,D11,D12,D13"),
    ]
    PRESETS = [
        ("(type your own)", "", ""),
        ("Weather: normal", "T 24.0C NORMAL", "H 40%"),
        ("Weather: HOT", "!! HOT SPACE !!", "CREW: HEAT WARN"),
        ("Weather: COLD", "!! COLD SPACE !!", "CREW: COLD WARN"),
        ("Game over: weather", "SIGNAL LOST", "GAME OVER"),
        ("Lives: 15", "T-Minus_6", "L15/15"),
    ]

    def __init__(self, shared):
        super().__init__(shared)
        lay = QtWidgets.QVBoxLayout(self.body)
        lay.addWidget(hint("Shows text on a 16x2 display through the PinTester sketch. The sketch "
                           "re-initialises the display on every send. The I2C option needs PinTester "
                           "built with USE_LCD_I2C 1, otherwise the board answers 'disabled'."))
        row = QtWidgets.QHBoxLayout()
        self.target = QtWidgets.QComboBox()
        for label, _, _ in self.TARGETS:
            self.target.addItem(label)
        self.param = QtWidgets.QLineEdit(self.TARGETS[0][2])
        row.addWidget(self.target, 1)
        row.addWidget(self.param, 1)
        lay.addLayout(row)

        self.preset = QtWidgets.QComboBox()
        for label, _, _ in self.PRESETS:
            self.preset.addItem(label)
        lay.addWidget(self.preset)

        mono = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        mono.setPointSize(16)
        self.l1, self.l2 = QtWidgets.QLineEdit(), QtWidgets.QLineEdit()
        for e in (self.l1, self.l2):
            e.setMaxLength(16)
            e.setFont(mono)
            e.setPlaceholderText("up to 16 characters")
            lay.addWidget(e)
        row2 = QtWidgets.QHBoxLayout()
        send = QtWidgets.QPushButton("Send")
        send.setDefault(True)
        clear = QtWidgets.QPushButton("Clear display")
        self.live = QtWidgets.QCheckBox("send as I type")
        row2.addWidget(send)
        row2.addWidget(clear)
        row2.addWidget(self.live)
        row2.addStretch(1)
        lay.addLayout(row2)
        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addStretch(1)

        self.debounce = QtCore.QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(400)
        self.debounce.timeout.connect(self._send)
        self.target.currentIndexChanged.connect(lambda i: self.param.setText(self.TARGETS[i][2]))
        self.preset.currentIndexChanged.connect(self._load_preset)
        send.clicked.connect(self._send)
        self.l1.returnPressed.connect(self._send)
        self.l2.returnPressed.connect(self._send)
        clear.clicked.connect(self._clear)
        for e in (self.l1, self.l2):
            e.textEdited.connect(lambda _: self.live.isChecked() and self.debounce.start())
        self.links["bench"].line_received.connect(self._on_line)
        self.finish_init()

    def _load_preset(self, i):
        _, a, b = self.PRESETS[i]
        if i:
            self.l1.setText(a)
            self.l2.setText(b)
            self._send()

    def _clear(self):
        self.l1.clear()
        self.l2.clear()
        self._send()

    def _send(self):
        text = self.l1.text().replace("|", "/") + "|" + self.l2.text().replace("|", "/")
        kind = self.TARGETS[self.target.currentIndex()][1]
        param = self.param.text().replace(" ", "").upper()
        if kind == "pins":
            pins = param.split(",")
            if len(pins) != 6 or not all(PIN_RE.match(p) for p in pins):
                self.status.setText("need six pins: RS,E,D4,D5,D6,D7")
                return
            cmd = f"LCD,{param},{text}"
        else:
            if not re.fullmatch(r"(0X)?[0-9A-F]{1,2}", param):
                self.status.setText("I2C address like 0x27 or 0x3F")
                return
            cmd = f"LCDI2C,{param},{text}"
        self.links["bench"].send(cmd)

    def _on_line(self, line):
        if line.startswith(("OK,LCD", "ERR,LCD")):
            self.status.setText(line)


# ----------------------------------------------------------------------- tower
class TowerTab(FuncTab):
    needs = ("tower",)

    def __init__(self, shared):
        super().__init__(shared)
        self.shots = self.acks = 0
        self.t_fire = None
        lay = QtWidgets.QVBoxLayout(self.body)
        lay.addWidget(hint("F fires one paper ball, the tower answers K when it is released. X disarms "
                           "(F is ignored, armed LED off), R re-arms."))
        self.safe = QtWidgets.QCheckBox("Line of fire is clear: nobody in front of the tower")
        lay.addWidget(self.safe)
        self.fire = QtWidgets.QPushButton("FIRE  (F)")
        self.fire.setMinimumHeight(90)
        self.fire.setStyleSheet("QPushButton{background:#b3261e;color:white;font-size:28px;font-weight:bold;"
                                "border-radius:8px;} QPushButton:disabled{background:#e6b9b6;color:#888;}")
        self.fire.setEnabled(False)
        lay.addWidget(self.fire)
        row = QtWidgets.QHBoxLayout()
        arm = QtWidgets.QPushButton("Arm (R)")
        disarm = QtWidgets.QPushButton("Disarm (X)")
        row.addWidget(arm)
        row.addWidget(disarm)
        lay.addLayout(row)
        self.stats = QtWidgets.QLabel()
        lay.addWidget(self.stats)

        self.pan_box = QtWidgets.QGroupBox("Pan servo (optional)")
        pl = QtWidgets.QVBoxLayout(self.pan_box)
        self.pan_fit = QtWidgets.QCheckBox("Pan servo fitted (HAS_PAN 1 in tower.ino)")
        self.pan = QtWidgets.QSlider(Qt.Horizontal)
        self.pan.setRange(0, 180)
        self.pan.setValue(90)
        self.pan.setEnabled(False)
        self.pan_lab = QtWidgets.QLabel("aim 90 deg")
        pl.addWidget(self.pan_fit)
        pl.addWidget(self.pan)
        pl.addWidget(self.pan_lab)
        lay.addWidget(self.pan_box)
        lay.addStretch(1)

        self.safe.toggled.connect(self.fire.setEnabled)
        self.fire.clicked.connect(self._fire)
        arm.clicked.connect(lambda: self.links["tower"].send("R"))
        disarm.clicked.connect(lambda: self.links["tower"].send("X"))
        self.pan_fit.toggled.connect(self.pan.setEnabled)
        self.pan.valueChanged.connect(self._pan)
        self.links["tower"].line_received.connect(self._on_line)
        self._show()
        self.finish_init()

    def _show(self, extra=""):
        self.stats.setText(f"F sent: {self.shots}    K received: {self.acks}    {extra}")

    def _fire(self):
        self.t_fire = time.monotonic()
        if self.links["tower"].send("F"):
            self.shots += 1
            self._show("waiting for K ...")

    def _pan(self, v):
        self.pan_lab.setText(f"aim {v} deg")
        self.links["tower"].send(f"A,{v}", quiet=True)

    def _on_line(self, line):
        if line.strip() == "K":
            self.acks += 1
            if self.t_fire is not None:
                self._show(f"last F to K: {(time.monotonic() - self.t_fire) * 1000:.0f} ms")
                self.t_fire = None
            else:
                self._show("K without F (test-fire button)")

    def stop_motion(self):
        self.safe.setChecked(False)


# ----------------------------------------------------------------------- robot
class RobotTab(FuncTab):
    needs = ("robot",)

    def __init__(self, shared):
        super().__init__(shared)
        self.cmd = (0, 0)
        self.s_times = deque(maxlen=40)
        lay = QtWidgets.QHBoxLayout(self.body)

        left = QtWidgets.QVBoxLayout()
        left.addWidget(hint("Hold a button to drive: D,left,right,ap is resent 20 times a second and "
                            "the robot stops 300 ms after the commands stop. The firmware caps speed "
                            "itself and always refuses forward motion closer than 8 cm."))
        self.safe = QtWidgets.QCheckBox("Wheels are off the ground / the area is clear")
        left.addWidget(self.safe)
        grid = QtWidgets.QGridLayout()
        self.pad = {}
        for name, (r, c), (sl, sr) in (("Forward", (0, 1), (1, 1)), ("Left", (1, 0), (-1, 1)),
                                       ("Right", (1, 2), (1, -1)), ("Back", (2, 1), (-1, -1))):
            b = QtWidgets.QPushButton(name)
            b.setMinimumSize(90, 60)
            b.pressed.connect(lambda sl=sl, sr=sr: self._hold(sl, sr))
            b.released.connect(self._release)
            grid.addWidget(b, r, c)
            self.pad[name] = b
        stop = QtWidgets.QPushButton("STOP")
        stop.setMinimumSize(90, 60)
        stop.setStyleSheet("background:#b3261e; color:white; font-weight:bold;")
        stop.clicked.connect(self.stop_motion)
        grid.addWidget(stop, 1, 1)
        left.addLayout(grid)
        left.addWidget(QtWidgets.QLabel("Speed (0-255, the firmware scales it down)"))
        self.speed = QtWidgets.QSlider(Qt.Horizontal)
        self.speed.setRange(0, 255)
        self.speed.setValue(120)
        self.speed_lab = QtWidgets.QLabel("120")
        self.speed.valueChanged.connect(lambda v: self.speed_lab.setText(str(v)))
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.speed)
        row.addWidget(self.speed_lab)
        left.addLayout(row)
        self.ap = QtWidgets.QCheckBox("auto-pilot flag (status LED on)")
        self.ap.toggled.connect(lambda: self.links["robot"].send(f"D,0,0,{int(self.ap.isChecked())}"))
        left.addWidget(self.ap)
        row2 = QtWidgets.QHBoxLayout()
        latch = QtWidgets.QPushButton("Game over latch (X)")
        reset = QtWidgets.QPushButton("Reset (R)")
        latch.clicked.connect(lambda: self.links["robot"].send("X"))
        reset.clicked.connect(lambda: self.links["robot"].send("R"))
        row2.addWidget(latch)
        row2.addWidget(reset)
        left.addLayout(row2)
        left.addStretch(1)
        lay.addLayout(left, 1)

        right = QtWidgets.QVBoxLayout()
        self.radar = RadarWidget()
        right.addWidget(self.radar, 1)
        self.readout = QtWidgets.QLabel("no scan yet")
        right.addWidget(self.readout)
        flags = QtWidgets.QHBoxLayout()
        self.ind = {}
        for key, text in (("L", "bumper L"), ("R", "bumper R"), ("stop", "< 8 cm STOP")):
            lab = QtWidgets.QLabel(text)
            lab.setAlignment(Qt.AlignCenter)
            lab.setMinimumHeight(30)
            self.ind[key] = lab
            self._indicator(key, False)
            flags.addWidget(lab)
        right.addLayout(flags)
        clr = QtWidgets.QPushButton("Clear radar")
        clr.clicked.connect(self.radar.clear)
        right.addWidget(clr)
        lay.addLayout(right, 2)

        self.links["robot"].line_received.connect(self._on_line)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._resend)
        self.timer.start(50)
        self.finish_init()

    def _indicator(self, key, on):
        colour = {"stop": "#b3261e"}.get(key, "#e6a100")
        self.ind[key].setStyleSheet(
            f"border-radius:4px; padding:4px; background:{colour if on else '#e4e7ec'}; "
            f"color:{'white' if on else '#778'};")

    def _hold(self, sl, sr):
        if not self.safe.isChecked():
            self.readout.setText("tick the safety box first")
            return
        s = self.speed.value()
        self.cmd = (sl * s, sr * s)
        self._resend()

    def _release(self):
        self.stop_motion()

    def _resend(self):
        if self.cmd != (0, 0) and self.links["robot"].is_open:
            self.links["robot"].send(f"D,{self.cmd[0]},{self.cmd[1]},{int(self.ap.isChecked())}", quiet=True)

    def stop_motion(self):
        self.cmd = (0, 0)
        if self.links["robot"].is_open:
            for _ in range(2):
                self.links["robot"].send(f"D,0,0,{int(self.ap.isChecked())}", quiet=True)

    def on_ready_changed(self, ok):
        if not ok:
            self.cmd = (0, 0)

    def deactivate(self):
        self.stop_motion()

    def _on_line(self, line):
        v = parse_line(line, "S", 3)
        if v:
            angle, cm, flag = v
            self.radar.add(angle, cm)
            self.s_times.append(time.monotonic())
            rate = ""
            if len(self.s_times) > 4:
                span = self.s_times[-1] - self.s_times[0]
                rate = f"   {(len(self.s_times) - 1) / span:.1f} scans/s" if span > 0 else ""
            echo = "no echo" if cm >= 400 else f"{cm:.0f} cm"
            self.readout.setText(f"angle {angle:+.0f} deg   distance {echo}{rate}")
            self._indicator("stop", flag >= 1)
        elif line.startswith("B,"):
            side = line.split(",")[1].strip()[:1]
            if side in self.ind:
                self._indicator(side, True)
                QtCore.QTimer.singleShot(600, lambda s=side: self._indicator(s, False))


# --------------------------------------------------------------------- weather
class WeatherTab(FuncTab):
    needs = ("weather",)
    STATE = {0: ("NORMAL", "#2e7d32", "LCD: T xx.xC NORMAL / H nn%   green LED solid   silent"),
             1: ("COLD", "#1565c0", "LCD: !! COLD SPACE !! / CREW: COLD WARN   blue LED blinks   passive buzzer low tone"),
             2: ("HOT", "#c62828", "LCD: !! HOT SPACE !! / CREW: HEAT WARN   red LED blinks   active buzzer fast beeps")}

    def __init__(self, shared):
        super().__init__(shared)
        self.last = None
        lay = QtWidgets.QVBoxLayout(self.body)
        top = QtWidgets.QHBoxLayout()
        self.temp = big("--.- C", 44)
        self.hum = big("-- %", 30, False)
        self.state = big("NO DATA", 30)
        self.state.setAlignment(Qt.AlignCenter)
        self.state.setMinimumWidth(190)
        top.addWidget(self.temp)
        top.addWidget(self.hum)
        top.addStretch(1)
        top.addWidget(self.state)
        lay.addLayout(top)
        self.expect = hint("")
        lay.addWidget(self.expect)
        self.age = QtWidgets.QLabel("")
        lay.addWidget(self.age)
        self.spark = SparkLine()
        lay.addWidget(self.spark)

        box = QtWidgets.QGroupBox("Send to the station")
        g = QtWidgets.QGridLayout(box)
        self.vtemp = QtWidgets.QDoubleSpinBox()
        self.vtemp.setRange(-20, 80)
        self.vtemp.setValue(35.0)
        self.vtemp.setSuffix(" C")
        self.vtemp.setSingleStep(0.5)
        v = QtWidgets.QPushButton("Simulate temperature (V)")
        v.clicked.connect(lambda: self.links["weather"].send(f"V,{self.vtemp.value():g}"))
        self.lives = QtWidgets.QSpinBox()
        self.lives.setRange(0, 15)
        self.lives.setValue(14)
        h = QtWidgets.QPushButton("Set lives (H)")
        h.clicked.connect(lambda: self.links["weather"].send(f"H,{self.lives.value()}"))
        gover = QtWidgets.QPushButton("Game over (G)")
        gover.clicked.connect(lambda: self.links["weather"].send("G"))
        rst = QtWidgets.QPushButton("Reset: real sensor, 15 lives (R)")
        rst.clicked.connect(lambda: self.links["weather"].send("R"))
        g.addWidget(self.vtemp, 0, 0)
        g.addWidget(v, 0, 1)
        g.addWidget(self.lives, 1, 0)
        g.addWidget(h, 1, 1)
        g.addWidget(gover, 2, 0)
        g.addWidget(rst, 2, 1)
        lay.addWidget(box)
        lay.addWidget(hint("V puts the board in simulation mode (it ignores the DHT11) until R. The firmware "
                           "moves one state per V, so going from HOT straight to a cold value shows NORMAL "
                           "first: send it twice. H with a lower number flashes the yellow hit LED for 1 s."))
        lay.addStretch(1)

        self.links["weather"].line_received.connect(self._on_line)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._age)
        self.timer.start(500)
        self.finish_init()

    def _on_line(self, line):
        v = parse_line(line, "W", 3)
        if not v:
            return
        temp, hum, st = v
        self.last = time.monotonic()
        self.temp.setText(f"{temp:.1f} C")
        self.hum.setText(f"{hum:.0f} %")
        name, colour, expect = self.STATE.get(int(st), ("?", "#555", ""))
        self.state.setText(name)
        self.state.setStyleSheet(f"background:{colour}; color:white; border-radius:6px; padding:6px;")
        self.expect.setText("Should be showing: " + expect)
        self.spark.add(temp)

    def _age(self):
        if self.last is not None:
            self.age.setText(f"last reading {time.monotonic() - self.last:.1f} s ago (the board sends one every 2 s)")


# ---------------------------------------------------------------------- camera
class CameraStream(QtCore.QObject):
    frame = QtCore.pyqtSignal(QtGui.QImage)
    status = QtCore.pyqtSignal(str)
    stats = QtCore.pyqtSignal(float, int, int)

    def __init__(self):
        super().__init__()
        self._stop = threading.Event()

    def start(self, url):
        self._stop = threading.Event()
        threading.Thread(target=self._run, args=(url, self._stop), daemon=True).start()

    def stop(self):
        self._stop.set()

    def _run(self, url, stop):
        try:
            import cv2
        except ImportError:
            self.status.emit("opencv missing: pip install -r tests/requirements.txt")
            return
        src = int(url) if url.isdigit() else url
        self.status.emit(f"connecting to {url} (up to 8 s) ...")
        cap = open_capture(src, cv2, 8.0, stop)
        if cap is None:
            if not stop.is_set():
                self.status.emit("could not open the stream")
            return
        self.status.emit("live")
        n, t0, last_emit, w, h = 0, time.monotonic(), 0.0, 0, 0
        while not stop.is_set():
            ok, frame = cap.read()
            if not ok:
                self.status.emit("stream lost")
                break
            n += 1
            now = time.monotonic()
            h, w = frame.shape[:2]
            if now - last_emit >= 1 / 30:
                last_emit = now
                self.frame.emit(bgr_to_qimage(frame))
            if now - t0 >= 1.0:
                self.stats.emit(n / (now - t0), w, h)
                n, t0 = 0, now
        cap.release()


class CameraTab(FuncTab):
    def __init__(self, shared):
        super().__init__(shared)
        self.stream = CameraStream()
        self.running = False
        lay = QtWidgets.QVBoxLayout(self.body)
        row = QtWidgets.QHBoxLayout()
        self.btn = QtWidgets.QPushButton("Start")
        self.url = QtWidgets.QLabel()
        self.url.setStyleSheet(HINT_STYLE)
        row.addWidget(self.btn)
        row.addWidget(self.url, 1)
        lay.addLayout(row)
        self.video = VideoWidget()
        lay.addWidget(self.video, 1)
        self.info = QtWidgets.QLabel("stopped")
        lay.addWidget(self.info)
        lay.addWidget(hint("The stream URL comes from the Connections panel (a number such as 0 opens a "
                           "local webcam). Spec: 320x240, 15-20 fps, newest frame only. Point it at the "
                           "table, not at people."))
        self.btn.clicked.connect(self._toggle)
        self.stream.frame.connect(self.video.set_image)
        self.stream.status.connect(self.info.setText)
        self.stream.stats.connect(lambda fps, w, h: self.info.setText(f"live   {w}x{h}   {fps:.1f} fps"))
        self.finish_init()

    def showEvent(self, e):
        super().showEvent(e)
        self.url.setText(self.shared.camera_url() or "(set a stream URL in the Connections panel)")

    def _toggle(self):
        if self.running:
            self.stop_motion()
            return
        url = self.shared.camera_url()
        if not url:
            self.info.setText("enter a stream URL in the Connections panel")
            return
        self.url.setText(url)
        self.stream.start(url)
        self.running = True
        self.btn.setText("Stop")

    def stop_motion(self):
        if self.running:
            self.stream.stop()
            self.running = False
            self.btn.setText("Start")
            self.info.setText("stopped")


# --------------------------------------------------------------------- gamepad
class GamepadTab(FuncTab):
    Z_MODES = [("Triggers: RT - LT (axes 5 and 4)", "triggers"),
               ("Right stick up/down (axis 3)", "rstick"),
               ("None (z = 0)", "none")]

    def __init__(self, shared):
        super().__init__(shared)
        self.cfg = laptop_config()
        self.vec = (0.0, 0.0, 0.0)
        self.last_button = None
        self._prev_buttons = []
        lay = QtWidgets.QHBoxLayout(self.body)

        left = QtWidgets.QVBoxLayout()
        row = QtWidgets.QHBoxLayout()
        self.pads = QtWidgets.QComboBox()
        rescan = QtWidgets.QPushButton("Rescan")
        row.addWidget(self.pads, 1)
        row.addWidget(rescan)
        left.addLayout(row)
        self.info = QtWidgets.QLabel("no controller")
        self.info.setWordWrap(True)
        left.addWidget(self.info)

        form = QtWidgets.QFormLayout()
        self.ax_x = QtWidgets.QSpinBox()
        self.ax_y = QtWidgets.QSpinBox()
        self.ax_x.setValue(int(self.cfg["AXIS_TURN"]))
        self.ax_y.setValue(int(self.cfg["AXIS_SPEED"]))
        self.inv_x = QtWidgets.QCheckBox("invert")
        self.inv_y = QtWidgets.QCheckBox("invert")
        self.inv_y.setChecked(True)             # SDL reports stick up as negative
        self.zmode = QtWidgets.QComboBox()
        for label, key in self.Z_MODES:
            self.zmode.addItem(label, key)
        self.dz = QtWidgets.QDoubleSpinBox()
        self.dz.setRange(0, 0.5)
        self.dz.setSingleStep(0.01)
        self.dz.setValue(float(self.cfg["DEAD_ZONE"]))
        for sp in (self.ax_x, self.ax_y):
            sp.setRange(0, 15)
        rx = QtWidgets.QHBoxLayout()
        rx.addWidget(self.ax_x)
        rx.addWidget(self.inv_x)
        ry = QtWidgets.QHBoxLayout()
        ry.addWidget(self.ax_y)
        ry.addWidget(self.inv_y)
        form.addRow("X axis", rx)
        form.addRow("Y axis", ry)
        form.addRow("Z from", self.zmode)
        form.addRow("Dead zone", self.dz)
        left.addLayout(form)

        self.btn_grid = QtWidgets.QGridLayout()
        self.btn_labels = []
        left.addLayout(self.btn_grid)
        self.last_lab = QtWidgets.QLabel("press a button to see its number")
        left.addWidget(self.last_lab)
        left.addWidget(hint(f"laptop/config.py expects: Y = {self.cfg['BTN_AUTOPILOT']} (auto-pilot), "
                            f"B = {self.cfg['BTN_CAMERA']} (camera), Start = {self.cfg['BTN_RESTART']} (restart)."))
        self.axes_lab = QtWidgets.QLabel("")
        self.axes_lab.setStyleSheet("font-family: Consolas, monospace;")
        left.addWidget(self.axes_lab)

        self.fwd = QtWidgets.QCheckBox("Send to the robot as D,left,right,0 (wheels on blocks!)")
        left.addWidget(self.fwd)
        left.addStretch(1)
        lay.addLayout(left, 1)

        self.cube = CubeWidget()
        lay.addWidget(self.cube, 2)

        rescan.clicked.connect(self._rescan)
        self.pads.currentIndexChanged.connect(self._select)
        self.fwd.toggled.connect(self._fwd_toggled)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(16)
        self.watch("robot")
        self.finish_init()
        self._rescan()

    def ready(self):        # reading the pad needs no link
        return True

    def missing(self):
        return []

    def _refresh(self, *_):
        super()._refresh()
        self.fwd.setEnabled(self.links["robot"].is_open)
        if not self.links["robot"].is_open:
            self.fwd.setChecked(False)
        if not gamepad_io.available():
            self.banner.setVisible(True)
            self.banner.setText("pygame is missing: pip install -r tests/requirements.txt")

    def _rescan(self):
        if not gamepad_io.available():
            return
        found = gamepad_io.rescan()
        self.pads.blockSignals(True)
        self.pads.clear()
        for i, name in found:
            self.pads.addItem(f"{i}: {name}", i)
        self.pads.blockSignals(False)
        if found:
            self._select()
        else:
            gamepad_io.select(-1)
            self.info.setText("No controller found. Pair it over Bluetooth, wake it, then press Rescan.")
            self.cube.set_vector(0, 0, 0)

    def _select(self):
        idx = self.pads.currentData()
        if idx is None:
            return
        name = gamepad_io.select(idx)
        st = gamepad_io.read()
        if not name or st is None:
            self.info.setText("could not open that controller")
            return
        self.info.setText(f"{name}\n{len(st['axes'])} axes, {len(st['buttons'])} buttons, {len(st['hats'])} hats")
        for lab in self.btn_labels:
            lab.deleteLater()
        self.btn_labels = []
        for i in range(len(st["buttons"])):
            lab = QtWidgets.QLabel(str(i))
            lab.setAlignment(Qt.AlignCenter)
            lab.setMinimumSize(26, 22)
            self.btn_grid.addWidget(lab, i // 10, i % 10)
            self.btn_labels.append(lab)
        self._prev_buttons = [0] * len(st["buttons"])

    def _dead(self, v):
        return 0.0 if abs(v) < self.dz.value() else v

    def _axis(self, st, i):
        return st["axes"][i] if 0 <= i < len(st["axes"]) else 0.0

    def _poll(self):
        st = gamepad_io.read()
        if st is None:
            return
        x = self._axis(st, self.ax_x.value()) * (-1 if self.inv_x.isChecked() else 1)
        y = self._axis(st, self.ax_y.value()) * (-1 if self.inv_y.isChecked() else 1)
        mode = self.zmode.currentData()
        if mode == "triggers":
            z = (self._axis(st, 5) - self._axis(st, 4)) / 2.0      # triggers rest at -1, press to +1
        elif mode == "rstick":
            z = -self._axis(st, 3)
        else:
            z = 0.0
        self.vec = tuple(max(-1.0, min(1.0, self._dead(v))) for v in (x, y, z))
        self.cube.set_vector(*self.vec)

        for i, b in enumerate(st["buttons"]):
            if i < len(self.btn_labels):
                self.btn_labels[i].setStyleSheet(
                    "background:#ffb020; color:black; border-radius:3px;" if b else "background:#e4e7ec; border-radius:3px;")
            if i < len(self._prev_buttons) and b and not self._prev_buttons[i]:
                self.last_button = i
                self.last_lab.setText(f"last button pressed: {i}")
        self._prev_buttons = list(st["buttons"])
        self.axes_lab.setText("axes  " + "  ".join(f"{i}:{v:+.2f}" for i, v in enumerate(st["axes"])))
        if self.fwd.isChecked():
            self._send_drive()

    def _send_drive(self):
        x, y, _ = self.vec
        k, mx = float(self.cfg["TURN_GAIN"]), int(self.cfg["MAX_PWM"])
        left, right = y + k * x, y - k * x          # same mix as laptop/model.py
        m = max(1.0, abs(left), abs(right))
        self.links["robot"].send(f"D,{int(mx * left / m)},{int(mx * right / m)},0", quiet=True)

    def _fwd_toggled(self, on):
        if not on and self.links["robot"].is_open:
            for _ in range(2):
                self.links["robot"].send("D,0,0,0", quiet=True)

    def stop_motion(self):
        self.fwd.setChecked(False)

    deactivate = stop_motion


TAB_ORDER = [
    ("Stepper", StepperTab),
    ("Servo", ServoTab),
    ("LCD", LcdTab),
    ("Tower", TowerTab),
    ("Robot", RobotTab),
    ("Weather", WeatherTab),
    ("Camera", CameraTab),
    ("Gamepad", GamepadTab),
]


class FuncMode(QtWidgets.QTabWidget):
    def __init__(self, shared):
        super().__init__()
        self.tabs_ = []
        for title, cls in TAB_ORDER:
            tab = cls(shared)
            self.tabs_.append(tab)
            self.addTab(tab, title)

    def stop_all(self):
        for t in self.tabs_:
            t.stop_motion()

    def deactivate(self):
        for t in self.tabs_:
            t.deactivate()
