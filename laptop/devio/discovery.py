"""Finds the devices by itself.

UdpHub: one UDP socket on port 5005. UNO Q bridges broadcast HELLO,role,fw,ip once a second; the hub records the
sender and attaches it to the robot or tower link. While a device is missing the hub broadcasts WHO? once a second.
A manual ROBOT_ADDR / TOWER_ADDR in config.local.json is used as well (no discovery needed).

SerialScanner: lists serial ports every 3 s, opens new ones, asks I? and expects I,weather,2 (or I,robot,2 /
I,tower,2 for the UNO Q USB-C fallback). Known Arduino / CH340 ports are tried first. Unplug and replug are fine."""
import socket
import threading
import time
import config as C
from core.clock import now
from devio import protocol as P

ARDUINO_VIDS = (0x2341, 0x2A03, 0x1A86, 0x0403, 0x10C4)     # Arduino, Arduino.org, CH340, FTDI, CP210x


def parse_addr(text, default_port=None):
    if not text:
        return None
    text = str(text).strip()
    if ":" in text:
        host, port = text.rsplit(":", 1)
        return host, int(port)
    return text, default_port or C.UDP_PORT


class UdpHub:
    def __init__(self, links, log, port=None):
        self.links = links                     # role -> Link
        self.log = log
        self.peers = {}                        # (ip, port) -> role
        self.stop = threading.Event()
        self.extra_hello_targets = []          # sim devices on loopback
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            self.sock.bind(("0.0.0.0", C.UDP_PORT if port is None else port))
        except OSError as e:
            self.log("UDP port %d busy (%s): using a free port, discovery broadcasts will still work" % (C.UDP_PORT, e))
            self.sock.bind(("0.0.0.0", 0))
        self.port = self.sock.getsockname()[1]
        self.sock.settimeout(0.05)
        self.rx_count = 0
        for role, key in (("robot", "ROBOT_ADDR"), ("tower", "TOWER_ADDR")):
            addr = parse_addr(getattr(C, key))
            if addr and role in self.links:
                self._attach(addr, role, None)

    def _attach(self, addr, role, fw):
        if self.peers.get(addr) != role:
            self.peers[addr] = role
            self.log("found %s at %s:%d" % (role, addr[0], addr[1]))
        sock = self.sock
        self.links[role].attach("%s:%d" % addr, lambda line, a=addr: sock.sendto((line + "\n").encode(), a), fw)

    def run(self):
        t_who = 0.0
        while not self.stop.is_set():
            try:
                data, addr = self.sock.recvfrom(512)
            except socket.timeout:
                data = None
            except OSError:                         # Windows: ICMP port unreachable from a vanished device
                data = None
                time.sleep(0.01)
            if data:
                self.rx_count += 1
                for line in P.split_datagram(data):
                    msg = P.decode(line)
                    if msg and msg[0] in ("HELLO", "I") and msg[1] in self.links:
                        self._attach(addr, msg[1], msg[2])
                    role = self.peers.get(addr)
                    if role:
                        self.links[role].on_line("%s:%d" % addr, line)
            t = now()
            if t - t_who >= 1.0:
                t_who = t
                if any(not self.links[r].connected for r in self.links):
                    for target in [("255.255.255.255", C.UDP_PORT)] + self.extra_hello_targets:
                        try:
                            self.sock.sendto(b"WHO?\n", target)
                        except OSError:
                            pass

    def close(self):
        self.stop.set()
        try:
            self.sock.close()
        except OSError:
            pass


class SerialPortTransport:
    """A serial port (or anything with read/write/close, like the simulated station) carrying protocol lines."""

    def __init__(self, port, name):
        self.port, self.name, self.buf, self.dead = port, name, b"", False
        self.lock = threading.Lock()

    def send(self, line):
        with self.lock:
            self.port.write((line + "\n").encode())

    def read_lines(self):
        try:
            data = self.port.read(512)
        except Exception:
            self.dead = True
            return []
        if not data:
            return []
        self.buf += data
        *lines, self.buf = self.buf.split(b"\n")
        if len(self.buf) > 256:
            self.buf = b""
        return [l.decode("ascii", "ignore").strip() for l in lines if l.strip()]

    def close(self):
        try:
            self.port.close()
        except Exception:
            pass


class SerialScanner:
    """Owns every serial device: scanning, the I? handshake, reading lines, unplug detection.
    The scan (opening a port, waiting for the UNO R3 to reboot, asking I?) takes seconds, so it runs in its own thread:
    reading the ports that are already connected never waits for it."""

    def __init__(self, links, log, fixed_port=None, enabled=True):
        self.links, self.log = links, log
        self.fixed_port = fixed_port
        self.enabled = enabled               # False in --sim and in tests: never touch the real serial ports
        self.active = {}                     # port name -> (transport, role)
        self.ignored = {}                    # port name -> retry time (not one of ours)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.status = "starting"
        self._busy = False

    def _candidates(self):
        try:
            from serial.tools import list_ports
        except ImportError:
            self.status = "pyserial missing: pip install pyserial"
            return []
        ports = list(list_ports.comports())
        ports.sort(key=lambda p: 0 if p.vid in ARDUINO_VIDS else 1)
        names = [p.device for p in ports]
        if self.fixed_port:
            names = [self.fixed_port] + [n for n in names if n != self.fixed_port]
        return names

    def _handshake(self, name, port):
        """UNO R3 resets when the port opens: wait for the bootloader, then ask who it is (1.5 s)."""
        tr = SerialPortTransport(port, name)
        self.stop.wait(1.8)
        try:
            port.reset_input_buffer()
        except Exception:
            pass
        tr.send("I?")
        end = now() + 1.5
        while now() < end and not self.stop.is_set():
            for line in tr.read_lines():
                msg = P.decode(line)
                if msg and msg[0] == "I" and msg[1] in self.links:
                    return tr, msg[1], msg[2]
                if msg and msg[0] == "W" and "station" in self.links:      # v1 firmware: no I? reply
                    return tr, "station", 1
            time.sleep(0.02)
        return None

    def _open(self, name):
        import serial
        try:
            port = serial.Serial(name, C.SERIAL_BAUD, timeout=0, write_timeout=0.2)
        except Exception as e:
            self.ignored[name] = now() + 10.0
            if name == self.fixed_port:
                self.log("cannot open %s: %s" % (name, e))
            return
        found = self._handshake(name, port)
        if not found:
            port.close()
            self.ignored[name] = now() + 15.0
            return
        tr, role, fw = found
        self._activate(name, tr, "station" if role == "weather" else role, fw)

    def _activate(self, name, tr, role, fw):
        with self.lock:
            self.active[name] = (tr, role)
        self.links[role].attach(name, tr.send, fw)
        self.log("found %s on %s (firmware v%s)" % (role, name, fw))

    def add_sim(self, name, obj, role):
        self._activate(name, SerialPortTransport(obj, name), role, P.FW)

    def _scan_once(self):
        try:
            for name in self._candidates():
                if self.stop.is_set() or all(self.links[r].connected for r in self.links):
                    break
                with self.lock:
                    if name in self.active:
                        continue
                if self.ignored.get(name, 0) > now():
                    continue
                self._open(name)
            self.status = "%d port(s) open" % len(self.active)
        except Exception as e:
            self.log("serial scan error: %r" % e)
        finally:
            self._busy = False

    def run(self):
        t_scan = -99.0
        while not self.stop.is_set():
            with self.lock:
                items = list(self.active.items())
            for name, (tr, role) in items:
                lines = tr.read_lines()
                if tr.dead:
                    tr.close()
                    with self.lock:
                        self.active.pop(name, None)
                    self.links[role].detach(name)
                    self.log("%s unplugged from %s" % (role, name))
                    continue
                for line in lines:
                    self.links[role].on_line(name, line)
            t = now()
            if self.enabled and not self._busy and t - t_scan >= C.SERIAL_SCAN_S:
                t_scan, self._busy = t, True
                threading.Thread(target=self._scan_once, daemon=True, name="serial-probe").start()
            time.sleep(0.01)

    def close(self):
        self.stop.set()
        with self.lock:
            for tr, _ in self.active.values():
                tr.close()
