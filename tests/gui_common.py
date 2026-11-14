"""Shared plumbing for the triage GUI: serial/UDP links, settings, camera helpers.

A Link owns one device connection (USB serial or UDP, line based, 115200 baud),
reads it in a background thread and keeps the recent lines so a test can wait for
"the next line containing X" without racing the reader (see Cursor).
"""
import json
import os
import re
import socket
import threading
import time
from collections import deque

from PyQt5 import QtCore, QtGui

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rw_timeout;8000000|timeout;8000000")

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(HERE, ".tester_settings.json")   # git-ignored
REPORT_DIR = os.path.join(HERE, "reports")                    # git-ignored
BAUD = 115200

# key, label shown in the UI, default target
DEVICES = [
    ("weather", "Weather station (UNO R3)", ""),
    ("robot", "Robot (UNO Q #1)", "192.168.1.50:5005"),
    ("tower", "Tower (UNO Q #2)", "192.168.1.51:5005"),
    ("bench", "Bench board (PinTester)", ""),
]
DEVICE_LABEL = {k: label for k, label, _ in DEVICES}
CAMERA_URLS = [
    "http://192.168.1.60:81/stream",    # ESP32-CAM CameraWebServer
    "http://192.168.1.61:8080/video",   # phone IP Webcam
]


class StopRequested(Exception):
    """Raised inside a running test when the operator presses Stop."""


# ------------------------------------------------------------------ settings
def load_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(data):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def laptop_config():
    """Gamepad button/axis numbers and robot mixing constants from laptop/config.py."""
    cfg = dict(AXIS_TURN=0, AXIS_SPEED=1, BTN_AUTOPILOT=3, BTN_CAMERA=1, BTN_RESTART=7,
               DEAD_ZONE=0.08, TURN_GAIN=0.6, MAX_PWM=255)
    try:
        import runpy
        ns = runpy.run_path(os.path.join(HERE, "..", "laptop", "config.py"))
        cfg.update({k: v for k, v in ns.items() if k.isupper()})
    except Exception:       # noqa: BLE001 - fall back to the documented defaults
        pass
    return cfg


# ------------------------------------------------------------------ parsing
def parse_line(line, prefix, n):
    """'S,10,35,0' -> [10.0, 35.0, 0.0] when the prefix matches and n numbers follow."""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) != n + 1 or parts[0] != prefix:
        return None
    try:
        return [float(p) for p in parts[1:]]
    except ValueError:
        return None


_UDP_RE = re.compile(r"^(?:udp\s+)?(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})$", re.I)


def parse_target(text):
    """'192.168.1.50:5005' -> ('udp', (host, port)); 'COM5  (Arduino)' -> ('serial', 'COM5')."""
    text = (text or "").strip()
    if not text:
        return None
    m = _UDP_RE.match(text)
    if m:
        return ("udp", (m.group(1), int(m.group(2))))
    return ("serial", text.split()[0])


def list_serial_ports():
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    return [(p.device, p.description or "") for p in list_ports.comports()]


# ------------------------------------------------------------------ link
class Cursor:
    """Reads a link's lines in order from 'now'. Non matching lines are consumed."""

    def __init__(self, link, stop=None):
        self.link = link
        self.stop = stop
        self.seq = link._current_seq()
        self.last_t = 0.0      # arrival time (monotonic) of the last line next() returned

    def next(self, match=None, timeout=2.0):
        """Next line containing `match` (any line if None), or None after `timeout` s."""
        cv = self.link._cv
        end = time.monotonic() + timeout
        with cv:
            while True:
                for seq, t, text in self.link._lines:
                    if seq <= self.seq:
                        continue
                    self.seq = seq
                    if match is None or match in text:
                        self.last_t = t
                        return text
                if self.stop is not None and self.stop.is_set():
                    raise StopRequested()
                remaining = end - time.monotonic()
                if remaining <= 0:
                    return None
                cv.wait(min(remaining, 0.1))

    def collect(self, seconds, match=None):
        """All matching lines for `seconds` s as [(text, arrival_time)]."""
        out = []
        end = time.monotonic() + seconds
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                return out
            text = self.next(match, remaining)
            if text is not None:
                out.append((text, self.last_t))


class Link(QtCore.QObject):
    line_received = QtCore.pyqtSignal(str)
    tx = QtCore.pyqtSignal(str)
    state_changed = QtCore.pyqtSignal(str, str)    # closed | connecting | open | error, detail

    def __init__(self, key):
        super().__init__()
        self.key = key
        self.state = "closed"
        self.detail = ""
        self.target = None
        self._ser = None
        self._sock = None
        self._addr = None
        self._thread = None
        self._stop = threading.Event()
        self._cv = threading.Condition()
        self._seq = 0
        self._lines = deque(maxlen=1000)    # (seq, arrival_time, text)
        self._wlock = threading.Lock()

    @property
    def is_open(self):
        return self.state == "open"

    # -- lifecycle
    def open_link(self, text):
        self.close_link()
        target = parse_target(text)
        if target is None:
            self._set("error", "enter a COM port or ip:port")
            return
        self.target = target
        self._stop = threading.Event()
        self._set("connecting", text)
        self._thread = threading.Thread(target=self._run, args=(target, self._stop), daemon=True)
        self._thread.start()

    def close_link(self):
        th = self._thread
        if th is not None and th.is_alive():
            self._stop.set()
            th.join(2.0)
        self._thread = None
        if self.state != "closed":
            self._set("closed", "")

    def _set(self, state, detail=""):
        self.state, self.detail = state, detail
        self.state_changed.emit(state, detail)

    def _run(self, target, stop):
        kind, where = target
        ser = sock = None
        try:
            if kind == "udp":
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(0.1)
                if hasattr(socket, "SIO_UDP_CONNRESET"):    # Windows: ICMP errors must not kill recv
                    try:
                        sock.ioctl(socket.SIO_UDP_CONNRESET, False)
                    except OSError:
                        pass
                self._sock, self._addr = sock, where
            else:
                import serial
                ser = serial.Serial(where, BAUD, timeout=0.05)
                self._set("connecting", "waiting 2 s for the board to reset")
                if stop.wait(2.0):          # UNO R3 resets when the port opens
                    return
                self._ser = ser
        except Exception as e:      # noqa: BLE001 - any open failure goes to the UI
            self._set("error", str(e))
            if ser:
                ser.close()
            if sock:
                sock.close()
            return
        self._set("open", where if kind == "serial" else f"udp {where[0]}:{where[1]}")
        try:
            self._read_loop(stop)
        finally:
            self._ser = self._sock = None
            try:
                (ser or sock).close()
            except Exception:       # noqa: BLE001
                pass

    def _read_loop(self, stop):
        buf = b""
        while not stop.is_set():
            try:
                if self._ser is not None:
                    data = self._ser.read(256)
                else:
                    try:
                        data, _ = self._sock.recvfrom(2048)
                    except socket.timeout:
                        continue
                    except ConnectionResetError:
                        continue
            except Exception as e:      # noqa: BLE001 - unplugged cable etc.
                if not stop.is_set():
                    self._set("error", f"link lost: {e}")
                return
            if not data:
                continue
            if self._sock is not None:      # a datagram is whole lines, no buffering needed
                for raw in data.split(b"\n"):
                    self._push(raw)
                continue
            buf += data
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                self._push(raw)

    def _push(self, raw):
        text = raw.decode(errors="replace").strip()
        if not text:
            return
        with self._cv:
            self._seq += 1
            self._lines.append((self._seq, time.monotonic(), text))
            self._cv.notify_all()
        self.line_received.emit(text)

    # -- helpers for tests
    def _current_seq(self):
        with self._cv:
            return self._seq

    def cursor(self, stop=None):
        return Cursor(self, stop)

    def send(self, line, quiet=False):
        """Send one text line. quiet=True keeps it out of the log (for 50 Hz streams)."""
        if self.state != "open":
            return False
        data = (line + "\n").encode()
        try:
            with self._wlock:
                if self._ser is not None:
                    self._ser.write(data)
                else:
                    self._sock.sendto(data, self._addr)
        except Exception as e:      # noqa: BLE001
            self._set("error", f"send failed: {e}")
            return False
        if not quiet:
            self.tx.emit(line)
        return True


# ------------------------------------------------------------------ camera
def open_capture(src, cv2, timeout_s=8.0, stop=None):
    """cv2.VideoCapture opened in a helper thread. Returns the capture or None."""
    box = {}
    abandoned = threading.Event()

    def run():
        cap = cv2.VideoCapture(src)
        ok = cap.isOpened() and cap.read()[0]
        if abandoned.is_set() or not ok:
            cap.release()
            return
        box["cap"] = cap

    th = threading.Thread(target=run, daemon=True)
    th.start()
    end = time.monotonic() + timeout_s
    while th.is_alive() and time.monotonic() < end:
        if stop is not None and stop.is_set():
            break
        th.join(0.1)
    if th.is_alive():
        abandoned.set()
        return None
    return box.get("cap")


def bgr_to_qimage(frame):
    import cv2
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QtGui.QImage(rgb.data, w, h, 3 * w, QtGui.QImage.Format_RGB888).copy()
