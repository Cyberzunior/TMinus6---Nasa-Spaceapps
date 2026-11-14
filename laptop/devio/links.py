"""Device links. A link owns its device's health (RTT, loss, firmware), knows how to say things to it, and
turns its lines into events on the bus. Transports (UDP via the hub, a serial port, a loopback sim) attach to a
link; when two transports reach the same device the one with the lower RTT carries the traffic."""
import collections
import threading
import config as C
from core.clock import now, now_us
from devio import protocol as P


class Transport:
    """One way to reach a device. send(line) must never block for long."""

    def __init__(self, name, send):
        self.name, self._send = name, send
        self.rtt_ms = None
        self.last_rx = 0.0
        self.pings = collections.deque(maxlen=20)    # (seq, answered)
        self.fw = None

    def send(self, line):
        try:
            self._send(line)
            return True
        except Exception:
            return False

    def alive(self, t, timeout=None):
        return t - self.last_rx < (C.LINK_TIMEOUT_S if timeout is None else timeout)

    def loss(self):
        old = [a for (s, a, ts) in self.pings if now() - ts > 1.0]
        return 0.0 if not old else 1.0 - sum(old) / len(old)


class Link:
    role = "device"
    timeout = None            # seconds of silence before the device counts as lost (None = LINK_TIMEOUT_S)

    def __init__(self, state, bus, log):
        self.state, self.bus, self.log = state, bus, log
        self.lock = threading.RLock()
        self.transports = {}
        self.connected = False
        self.seq = 0
        self.tx = self.rx = 0
        self._t_ping = 0.0

    # ---- transports
    def attach(self, name, send, fw=None):
        with self.lock:
            tr = self.transports.get(name)
            if tr is None:
                tr = self.transports[name] = Transport(name, send)
                self.log("%s: transport %s attached" % (self.role, name))
            else:
                tr._send = send
            if fw is not None:
                tr.fw = fw
            tr.last_rx = max(tr.last_rx, now())
        return tr

    def detach(self, name):
        with self.lock:
            self.transports.pop(name, None)

    def best(self):
        t = now()
        live = [tr for tr in self.transports.values() if tr.alive(t, self.timeout)]
        if not live:
            return None
        return min(live, key=lambda tr: tr.rtt_ms if tr.rtt_ms is not None else 999.0)

    def send(self, line):
        with self.lock:
            tr = self.best()
            if tr is None:
                return False
            ok = tr.send(line)
        if ok:
            self.tx += 1
        return ok

    def one_way_s(self):
        tr = self.best()
        return (tr.rtt_ms or 0.0) / 2000.0 if tr else 0.0

    # ---- receiving (called from the hub / serial / sim threads)
    def on_line(self, name, line):
        msg = P.decode(line)
        if msg is None:
            return
        with self.lock:
            tr = self.transports.get(name)
            if tr is None:
                return
            tr.last_rx = now()
            if msg[0] == "Q":
                for i, (s, a, ts) in enumerate(tr.pings):
                    if s == msg[1] and not a:
                        tr.pings[i] = (s, True, ts)
                        rtt = (now_us() - msg[2]) / 1000.0
                        tr.rtt_ms = rtt if tr.rtt_ms is None else 0.8 * tr.rtt_ms + 0.2 * rtt
                        break
                return
            if msg[0] in ("HELLO", "I"):
                tr.fw = msg[2]
                return
        self.rx += 1
        self.handle(msg)

    def handle(self, msg):
        pass

    # ---- health, called about 20 times a second from the link thread
    def tick(self):
        t = now()
        with self.lock:
            if t - self._t_ping >= C.PING_MS / 1000.0:
                self._t_ping = t
                self.seq = (self.seq + 1) % 100000
                for tr in self.transports.values():
                    tr.pings.append((self.seq, False, t))
                    tr.send(P.encode("P", self.seq, now_us()))
            best = self.best()
            up = best is not None
        if up != self.connected:
            self.connected = up
            self.bus.post("device_up" if up else "device_down", self.role)
            self.log("%s %s" % (self.role, "connected via " + best.name if up else "lost"))
            if up:
                self.resync()
            else:
                self.on_lost()
        with self.state.lock:
            d = self.state.devices[self._dev_name()]
            d.connected = up
            d.where = best.name if best else ", ".join(self.transports) or "searching"
            d.rtt_ms = best.rtt_ms if best else None
            d.loss = best.loss() if best else 0.0
            d.fw = best.fw if best else None

    def _dev_name(self):
        return self.role

    def resync(self):
        pass

    def on_lost(self):
        pass


class RobotLink(Link):
    role = "robot"

    def __init__(self, *a):
        super().__init__(*a)
        self.latched = False
        self.latch_confirmed = False
        self.front_stop = False
        self.last_drive = None
        self._t_x = 0.0

    def send_drive(self, left, right, ap):
        if self.latched:
            return False
        self.last_drive = (left, right, ap)
        return self.send(P.encode("D", int(left), int(right), int(ap)))

    def latch(self, on):
        self.latched, self.latch_confirmed = on, False
        self.send("X" if on else "R")
        self.log("robot %s" % ("latch (game over)" if on else "release"))

    def tick(self):
        super().tick()
        t = now()
        if self.latched and not self.latch_confirmed and t - self._t_x >= 0.2:     # 5 per second until confirmed
            self._t_x = t
            self.send("X")

    def handle(self, msg):
        k = msg[0]
        if k == "S":
            self.front_stop = bool(msg[3] & 1)
            if msg[3] & 2 and self.latched:
                self.latch_confirmed = True
            self.bus.post("scan", msg[1], msg[2], msg[3])
        elif k == "B":
            self.bus.post("bumper", msg[1])
        elif k == "T":
            self.bus.post("robot_air", msg[1], msg[2])

    def resync(self):
        self.send("X" if self.latched else "R")

    def on_lost(self):
        self.front_stop = False


class TowerLink(Link):
    role = "tower"

    def __init__(self, *a):
        super().__init__(*a)
        self.armed = True
        self.allowed = False
        self.last_fire = -99.0
        self.last_k = -99.0
        self.last_aim = None

    def allow(self, ok):
        self.allowed = ok

    def set_armed(self, on):
        self.armed = on
        self.send("R" if on else "X")

    def can_fire(self):
        return self.connected and self.armed and self.allowed and now() - self.last_fire >= C.TOWER_MIN_FIRE_GAP_S

    def fire(self, test=False):
        """Safety: only while flying (allowed), armed, and 2 s after the previous F. test=True is the Hardware
        Check button, which still needs the tower armed and the 2 s gap."""
        if not (self.connected and self.armed and (self.allowed or test)) or now() - self.last_fire < C.TOWER_MIN_FIRE_GAP_S:
            return False
        self.last_fire = now()
        return self.send("F")

    def aim(self, angle):
        self.last_aim = int(angle)
        return self.send(P.encode("A", int(angle)))

    def tune(self, rest, push, ms):
        return self.send(P.encode("T", int(rest), int(push), int(ms)))

    def handle(self, msg):
        if msg[0] == "K":
            self.last_k = now()
            self.bus.post("tower_k")

    def resync(self):
        self.tune(C.TOWER_REST_DEG, C.TOWER_PUSH_DEG, C.TOWER_PUSH_MS)
        self.send("R" if self.armed else "X")
        if C.TOWER_HAS_PAN:
            self.aim(self.last_aim if self.last_aim is not None else int(C.AIM_CENTER_DEG))


class StationLink(Link):
    """The weather station (UNO R3) over USB serial. No ping: it streams W every 2 s, so silence for 5 s = lost."""
    role = "station"
    timeout = 5.0

    def __init__(self, *a):
        super().__init__(*a)
        self.zone = 0
        self.lives = C.LIVES
        self.over = False
        self._zone_sent, self._t_zone = None, 0.0

    def tick(self):
        t = now()
        with self.lock:
            best = self.best()
        if best is not None and (self._zone_sent != self.zone or t - self._t_zone >= C.ZONE_KEEPALIVE_S):
            self._zone_sent, self._t_zone = self.zone, t
            self.send(P.encode("Z", self.zone))
        up = best is not None
        if up != self.connected:
            self.connected = up
            self.bus.post("device_up" if up else "device_down", self.role)
            self.log("station %s" % ("connected on " + best.name if up else "lost"))
            if up:
                self.resync()
        with self.state.lock:
            d = self.state.devices["station"]
            d.connected, d.where = up, best.name if best else "searching"
            d.fw, d.rtt_ms = (best.fw if best else None), None

    def set_zone(self, z):
        self.zone = int(z)

    def set_lives(self, n):
        self.lives = n
        return self.send(P.encode("H", n))

    def game_over(self):
        self.over = True
        return self.send("G")

    def reset(self):
        self.over, self.lives = False, C.LIVES
        return self.send("R")

    def virtual_temp(self, c):
        return self.send(P.encode("V", "%.1f" % c))

    def handle(self, msg):
        if msg[0] == "W":
            self.bus.post("weather", msg[1], msg[2], msg[3])

    def resync(self):
        if self.over:
            self.send("G")
        else:
            self.send("R")
            self.send(P.encode("H", self.lives))
        self._zone_sent = None


def link_thread(links, stop, state):
    """Pings, timeouts and the X repeat for every link, 20 times a second. Never raises."""
    import time
    while not stop.is_set():
        for link in links:
            try:
                link.tick()
            except Exception as e:                      # keep the thread alive whatever happens
                link.log("link tick error (%s): %r" % (link.role, e))
        state.beat("links", now())
        time.sleep(0.05)
