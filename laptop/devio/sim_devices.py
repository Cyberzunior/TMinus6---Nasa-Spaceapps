"""Software versions of every device. They speak the real line protocol, the robot and tower over UDP on the
loopback interface (so the real discovery and link code runs) and the station over a fake serial port.

SimRobot integrates the SAME model as the game with a configurable delay, raycasts the scenario's real debris and the
border into S readings, and has the firmware's 300 ms timeout, 8 cm front stop and X/R latch.
SimTower answers F with K after SIM_TOWER_K_MS. SimStation is the weather station's logic with keys to force hot,
cold and normal air."""
import collections
import math
import socket
import threading
import time
import config as C
from core.clock import now, now_us
from core.hazards import HazardField
from core.model import Pose, start_pose, step_pose
from devio import protocol as P


class _UdpDevice(threading.Thread):
    role = "device"

    def __init__(self, hub_port, delay_ms=0.0):
        super().__init__(daemon=True, name="sim-" + self.role)
        self.hub = ("127.0.0.1", hub_port)
        self.delay = delay_ms / 1000.0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.003)
        self.stop_flag = threading.Event()
        self.inbox = collections.deque()           # (due, line)
        self.outbox = collections.deque()          # (due, line)
        self.t_hello = 0.0
        self.peer = self.hub

    def out(self, line):
        self.outbox.append((now() + self.delay / 2, line))

    def handle(self, msg, t):
        pass

    def periodic(self, t, dt):
        pass

    def run(self):
        last = now()
        while not self.stop_flag.is_set():
            t = now()
            try:
                data, addr = self.sock.recvfrom(256)
                self.peer = addr
                for line in P.split_datagram(data):
                    self.inbox.append((t + self.delay / 2, line))
            except socket.timeout:
                pass
            except OSError:
                time.sleep(0.003)
            t = now()
            while self.inbox and self.inbox[0][0] <= t:
                line = self.inbox.popleft()[1]
                msg = P.decode(line)
                if msg is None:
                    continue
                if msg[0] == "P":
                    self.out(P.encode("Q", msg[1], msg[2]))
                elif msg[0] in ("WHO?", "I?"):
                    self.t_hello = 0.0
                else:
                    self.handle(msg, t)
            self.periodic(t, t - last)
            last = t
            if t - self.t_hello >= 1.0:
                self.t_hello = t
                try:
                    self.sock.sendto(P.encode("HELLO", self.role, P.FW, "127.0.0.1").encode() + b"\n", self.hub)
                except OSError:
                    pass
            while self.outbox and self.outbox[0][0] <= t:
                try:
                    self.sock.sendto((self.outbox.popleft()[1] + "\n").encode(), self.peer)
                except OSError:
                    pass

    def stop(self):
        self.stop_flag.set()


def ray_circle(ox, oy, dx, dy, cx, cy, r):
    fx, fy = ox - cx, oy - cy
    b = fx * dx + fy * dy
    c = fx * fx + fy * fy - r * r
    disc = b * b - c
    if disc < 0:
        return None
    s = -b - math.sqrt(disc)
    return s if s > 0 else None


def ray_walls(ox, oy, dx, dy):
    best = 999.0
    for wall, o, d in ((C.BOARD_W / 2, ox, dx), (-C.BOARD_W / 2, ox, dx), (C.BOARD_H / 2, oy, dy), (-C.BOARD_H / 2, oy, dy)):
        if abs(d) > 1e-9:
            s = (wall - o) / d
            if s > 0:
                best = min(best, s)
    return best


class SimRobot(_UdpDevice):
    role = "robot"

    def __init__(self, hub_port, delay_ms=None, field=None):
        super().__init__(hub_port, C.SIM_ROBOT_DELAY_MS if delay_ms is None else delay_ms)
        self.field = field or HazardField()
        self.pose = start_pose()
        self.cmd = (0, 0)
        self.t_cmd = -9.0
        self.latched = False
        self.ap = 0
        self.sweep, self.dir = -45, 1
        self.t_scan = 0.0
        self.front_cm = 400.0
        self.t_bump = 0.0
        self.t_air = 0.0
        self.has_air = False
        self.air = (23.0, 40)
        self.last_dist = {}

    def handle(self, msg, t):
        k = msg[0]
        if k == "D" and not self.latched:
            self.cmd, self.ap, self.t_cmd = (msg[1], msg[2]), msg[3], t
        elif k == "X":
            self.latched, self.cmd = True, (0, 0)
        elif k == "R":
            self.latched, self.cmd = False, (0, 0)
            self.pose = start_pose()                          # a person puts the robot back on its start mark

    def _range(self, deg):
        a = math.radians(self.pose.theta + C.SCAN_SIGN * deg)
        ox = self.pose.x + C.SENSOR_FWD * math.cos(a)
        oy = self.pose.y + C.SENSOR_FWD * math.sin(a)
        ox = max(-C.BOARD_W / 2 + 0.5, min(C.BOARD_W / 2 - 0.5, ox))     # the sensor stays inside the border
        oy = max(-C.BOARD_H / 2 + 0.5, min(C.BOARD_H / 2 - 0.5, oy))
        best = 400.0
        for off in (-6, 0, 6):                                # the HC-SR04 beam is about 15 degrees wide
            b = a + math.radians(off)
            dx, dy = math.cos(b), math.sin(b)
            best = min(best, ray_walls(ox, oy, dx, dy), ray_circle(ox, oy, dx, dy, 0, 0, C.EARTH_R) or 999.0)
            for d in self.field.debris:
                if d.real:
                    best = min(best, ray_circle(ox, oy, dx, dy, d.x, d.y, d.r) or 999.0)
        return best

    def periodic(self, t, dt):
        if dt <= 0 or dt > 0.5:
            return
        timed_out = t - self.t_cmd > 0.3
        left, right = (0, 0) if (timed_out or self.latched) else self.cmd
        speed = (left + right) / 2.0 / C.MAX_PWM
        turn = (left - right) / 2.0 / C.MAX_PWM / C.TURN_GAIN
        if self.front_cm < 8.0 and speed > 0:
            speed = 0.0                                       # the firmware's own safety, always on
        step_pose(self.pose, speed, turn, dt)
        cr = C.CRAFT_R
        self.pose.x = max(-C.BOARD_W / 2 + cr, min(C.BOARD_W / 2 - cr, self.pose.x))
        self.pose.y = max(-C.BOARD_H / 2 + cr, min(C.BOARD_H / 2 - cr, self.pose.y))
        for ox, oy, r, real in [(0.0, 0.0, C.EARTH_R, False)] + [(d.x, d.y, d.r, d.real) for d in self.field.debris]:
            dist = math.hypot(self.pose.x - ox, self.pose.y - oy)
            if dist < r + cr:
                k = (r + cr) / (dist or 1.0)
                self.pose.x, self.pose.y = ox + (self.pose.x - ox) * k, oy + (self.pose.y - oy) * k
                if real and t - self.t_bump > 0.2:
                    self.t_bump = t
                    side = ((math.degrees(math.atan2(oy - self.pose.y, ox - self.pose.x)) - self.pose.theta + 540) % 360) - 180
                    self.out("B," + ("R" if side > 0 else "L"))
        if not self.latched and t - self.t_scan >= 1 / 15.0:
            self.t_scan = t
            cm = self._range(self.sweep)
            self.last_dist[self.sweep] = cm
            if abs(self.sweep) <= 15:
                self.front_cm = min(self.last_dist.get(a, 400.0) for a in range(-15, 16, 5))
            self.out(P.encode("S", self.sweep, min(400, int(cm)), 1 if self.front_cm < 8 else 0))
            self.sweep += 5 * self.dir
            if self.sweep >= 45:
                self.dir = -1
            elif self.sweep <= -45:
                self.dir = 1
        if self.latched and t - self.t_scan >= 0.2:           # the latch confirmation: S with flags bit1
            self.t_scan = t
            self.out(P.encode("S", 0, 0, 2))
        if self.has_air and t - self.t_air >= 2.0:
            self.t_air = t
            self.out("T,%.1f,%d" % self.air)


class SimTower(_UdpDevice):
    role = "tower"

    def __init__(self, hub_port, k_ms=None):
        super().__init__(hub_port, 10.0)
        self.k_delay = (C.SIM_TOWER_K_MS if k_ms is None else k_ms) / 1000.0
        self.armed = True
        self.last_fire = -99.0
        self.balls = 0
        self.aim = 90
        self.tune = (C.TOWER_REST_DEG, C.TOWER_PUSH_DEG, C.TOWER_PUSH_MS)
        self.pending = []

    def handle(self, msg, t):
        k = msg[0]
        if k == "F":
            if self.armed and t - self.last_fire >= 1.5:
                self.last_fire = t
                self.balls += 1
                self.pending.append(t + self.k_delay)
        elif k == "X":
            self.armed = False
        elif k == "R":
            self.armed = True
        elif k == "A":
            self.aim = max(0, min(180, msg[1]))
        elif k == "TUNE":
            self.tune = msg[1:]

    def periodic(self, t, dt):
        while self.pending and self.pending[0] <= t:
            self.pending.pop(0)
            self.out("K")


class FakeSerial:
    """Quacks like serial.Serial for the scanner: write() sends to the device, read() returns what it said."""

    def __init__(self, device):
        self.device, self.buf, self.lock, self.closed = device, bytearray(), threading.Lock(), False

    def write(self, data):
        self.device.feed(bytes(data))

    def read(self, n=1):
        if self.closed:
            raise OSError("device unplugged")                 # what pyserial does when the USB cable is pulled
        with self.lock:
            out, self.buf = bytes(self.buf[:n]), self.buf[n:]
        return out

    def feed_from_device(self, line):
        with self.lock:
            self.buf += (line + "\n").encode()

    def reset_input_buffer(self):
        with self.lock:
            self.buf.clear()

    def close(self):
        self.closed = True


class SimStation(threading.Thread):
    """The weather station firmware v2 in Python: the sensor with 1 C hysteresis, the Z zone, V override, H / G / R,
    I? and an immediate W on every state change."""
    role = "weather"

    def __init__(self):
        super().__init__(daemon=True, name="sim-station")
        self.port = FakeSerial(self)
        self.stop_flag = threading.Event()
        self.air = 23.0
        self.hum = 40
        self.virtual = None
        self.sensor_state = 0
        self.zone = 0
        self.lives = C.LIVES
        self.over = False
        self.state = 0
        self.rx = bytearray()
        self.hit_until = 0.0
        self.t_w = 0.0
        self.log = []                      # what the LCD / LEDs would show, for the tests

    def set_air(self, c):
        self.air = c

    def feed(self, data):
        self.rx += data
        while b"\n" in self.rx:
            line, _, rest = bytes(self.rx).partition(b"\n")
            self.rx = bytearray(rest)
            self._line(line.decode("ascii", "ignore").strip())

    def _temp(self):
        return self.virtual if self.virtual is not None else self.air

    def _update(self):
        t = self._temp()
        s = self.sensor_state
        if s == 0:
            s = 2 if t > C.HOT_C else 1 if t < C.COLD_C else 0
        elif s == 2 and t < C.HOT_C - C.HYST_C:
            s = 0
        elif s == 1 and t > C.COLD_C + C.HYST_C:
            s = 0
        self.sensor_state = s
        new = max(s, self.zone)
        if new != self.state:
            self.state = new
            self._send_w()

    def _send_w(self):
        self.port.feed_from_device("W,%.1f,%d,%d" % (self._temp(), self.hum, self.state))
        self.t_w = now()

    def lcd(self):
        if self.over:
            return ("SIGNAL LOST", "GAME OVER")
        if self.state == 2:
            return ("!! HOT ZONE !!", "MOVE AWAY NOW!")
        if self.state == 1:
            return ("!! COLD ZONE !!", "MOVE AWAY NOW!")
        return ("T %.1fC NORMAL" % self._temp(), "H %d%%" % self.hum)

    def _line(self, s):
        m = P.decode(s)
        if m is None:
            return
        k = m[0]
        if k == "I?":
            self.port.feed_from_device("I,weather,%d" % P.FW)
        elif k == "Z":
            self.zone = m[1]
        elif k == "V":
            self.virtual = m[1]
        elif k == "H":
            if m[1] < self.lives:
                self.hit_until = now() + 1.0
            self.lives = m[1]
        elif k == "G":
            self.over, self.lives = True, 0
        elif k == "R":
            self.over, self.lives, self.virtual, self.zone = False, C.LIVES, None, 0
        self._update()

    def run(self):
        while not self.stop_flag.is_set():
            self._update()
            if now() - self.t_w >= 2.0:
                self._send_w()
            time.sleep(0.02)

    def stop(self):
        self.stop_flag.set()


def sim_camera_source(get_pose, field):
    """A rendered first-person view (320x240) from the robot's pose: sky, cardboard floor, border, debris, Earth."""
    import numpy as np
    W, H, FOV = 320, 240, math.radians(66)

    def render():
        p = get_pose()
        img = np.zeros((H, W, 3), np.uint8)
        sky = np.linspace((10, 14, 38), (60, 80, 130), H // 2).astype(np.uint8)
        img[:H // 2] = sky[:, None, :]
        floor = np.linspace((120, 92, 60), (168, 130, 88), H - H // 2).astype(np.uint8)
        img[H // 2:] = floor[:, None, :]
        step = 2
        ox = p.x + C.SENSOR_FWD * math.cos(math.radians(p.theta))
        oy = p.y + C.SENSOR_FWD * math.sin(math.radians(p.theta))
        for col in range(0, W, step):
            a = math.radians(p.theta) + (col / W - 0.5) * FOV
            dx, dy = math.cos(a), math.sin(a)
            dist, color = ray_walls(ox, oy, dx, dy), (200, 170, 120)
            e = ray_circle(ox, oy, dx, dy, 0, 0, C.EARTH_R)
            if e is not None and e < dist:
                dist, color = e, (40, 110, 210)
            for d in field.debris:
                s = ray_circle(ox, oy, dx, dy, d.x, d.y, d.r)
                if s is not None and s < dist:
                    dist, color = s, (150, 150, 160)
            h = int(min(H * 0.9, 22 * H / max(dist, 2.0) / 3.0))
            shade = max(0.35, 1.0 - dist / 160.0)
            y0 = H // 2 - h // 2
            img[max(0, y0):min(H, y0 + h), col:col + step] = [int(c * shade) for c in color]
        return img
    return render
