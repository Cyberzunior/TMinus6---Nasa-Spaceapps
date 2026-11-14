"""T-Minus_6 tower bridge: runs on the UNO Q's Linux side and joins the Wi-Fi network to the microcontroller.

  laptop --UDP 5005--> this program --Arduino Bridge "line"--> sketch (tower.ino)
  laptop <--UDP------- this program <--Bridge "mcu_line"------ sketch

What it does:
  * answers P,seq,t with Q,seq,t at once (the laptop measures the round trip with this)
  * broadcasts HELLO,tower,2,<ip> once a second to the subnet so the laptop finds it by itself; answers WHO? and I?
  * passes F, A, X, R and T (pusher tuning) to the sketch in order
  * sends every line the sketch reports back to the laptop's last-seen address
  * treats 2 s of silence as "laptop gone": stops sending to it and keeps broadcasting HELLO
Latest value wins: nothing is queued, a late command is worse than a new one.

Run it as the Python part of an Arduino App Lab app (the sketch goes in the same app) so it starts on boot.
UNVERIFIED on a real board: the Bridge API names below (arduino.app_utils App / Bridge, Bridge.notify, Bridge.provide) come
from the community write-ups of the UNO Q; check them against the current Arduino documentation.

Test without a board:  python tower_bridge.py --selftest
"""
import socket
import subprocess
import sys
import threading
import time

ROLE = "tower"
FW = 2
PORT = 5005
FORWARD = ("F", "A", "X", "R", "T")          # lines passed to the microcontroller as they arrive
LATEST = ()           # lines where only the newest is kept and sent at most every 20 ms
LAPTOP_TIMEOUT = 2.0

try:
    from arduino.app_utils import App, Bridge
    REAL = True
except ImportError:                                  # running on a PC: a stand-in that records what it would do
    REAL = False

    class _FakeBridge:
        def __init__(self):
            self.sent, self.provided = [], {}

        def notify(self, name, *args):
            self.sent.append((name,) + args)

        def provide(self, name, fn):
            self.provided[name] = fn

    class _FakeApp:
        @staticmethod
        def run(*a, **k):
            while True:
                time.sleep(1)

    Bridge, App = _FakeBridge(), _FakeApp()


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))             # no packet is sent: this only picks the Wi-Fi interface
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


class RelayBridge:
    def __init__(self, port=PORT, hello_to=None, bridge=None, ip=None):
        self.bridge = bridge or Bridge
        self.ip = ip or local_ip()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.bind(("0.0.0.0", port))
        self.sock.settimeout(0.02)
        self.port = self.sock.getsockname()[1]
        self.laptop, self.t_rx = None, 0.0
        self.latest = {}                                # first character -> newest line
        self.lock = threading.Lock()                     # one thread at a time talks to the Bridge
        self.stop = threading.Event()
        self.hello_to = hello_to                         # tests: extra HELLO target
        self.bridge.provide("mcu_line", self.on_mcu_line)

    # ---- sketch -> laptop (runs on the Bridge's own thread: only sendto here, never Bridge.call)
    def on_mcu_line(self, line):
        if self.laptop and time.time() - self.t_rx < LAPTOP_TIMEOUT:
            try:
                self.sock.sendto((str(line).strip() + "\n").encode(), self.laptop)
            except OSError:
                pass

    def to_mcu(self, line):
        with self.lock:
            self.bridge.notify("line", line)

    def reply(self, text, addr):
        try:
            self.sock.sendto((text + "\n").encode(), addr)
        except OSError:
            pass

    # ---- laptop -> sketch
    def handle(self, line, addr):
        line = line.strip()
        if not line or len(line) > 64:
            return
        kind = line.split(",", 1)[0]
        if kind == "P":
            self.laptop, self.t_rx = addr, time.time()
            self.reply("Q" + line[1:], addr)                    # echo seq and timestamp straight back
        elif kind in ("WHO?", "I?"):
            self.reply("HELLO,%s,%d,%s" % (ROLE, FW, self.ip), addr)
            self.reply("I,%s,%d" % (ROLE, FW), addr)
        elif kind in LATEST:
            self.laptop, self.t_rx = addr, time.time()
            self.latest[kind] = line                            # the sender thread passes on only the newest
        elif kind in FORWARD:
            self.laptop, self.t_rx = addr, time.time()
            self.to_mcu(line)

    def rx_loop(self):
        while not self.stop.is_set():
            try:
                data, addr = self.sock.recvfrom(256)
            except socket.timeout:
                continue
            except OSError:
                time.sleep(0.01)
                continue
            if addr[0] == self.ip and addr[1] == self.port:
                continue                                        # our own broadcast
            for line in data.decode("ascii", "ignore").replace("\r", "").split("\n"):
                self.handle(line, addr)

    def send_loop(self):
        while not self.stop.is_set():
            for kind in list(self.latest):
                line = self.latest.pop(kind, None)
                if line:
                    self.to_mcu(line)
            time.sleep(0.02)                                    # at most 50 per second

    def hello_loop(self):
        a, b, c, _ = (self.ip.split(".") + ["0"] * 4)[:4]
        targets = ["255.255.255.255", "%s.%s.%s.255" % (a, b, c)]
        while not self.stop.is_set():
            msg = ("HELLO,%s,%d,%s\n" % (ROLE, FW, self.ip)).encode()
            for t in targets:
                try:
                    self.sock.sendto(msg, (t, PORT))
                except OSError:
                    pass
            if self.hello_to:
                try:
                    self.sock.sendto(msg, self.hello_to)
                except OSError:
                    pass
            self.stop.wait(1.0)

    def start(self):
        for fn in (self.rx_loop, self.send_loop, self.hello_loop):
            threading.Thread(target=fn, daemon=True).start()


def wifi_full_speed():
    """Best effort: switch Wi-Fi power saving off so packets are not held back (verify the interface name on your board)."""
    for iface in ("wlan0",):
        try:
            subprocess.run(["iw", "dev", iface, "set", "power_save", "off"], timeout=3, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            pass


def selftest():
    fake = _FakeBridge() if REAL else Bridge
    rb = RelayBridge(port=0, bridge=fake, ip="127.0.0.1")
    rb.start()
    t = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    t.settimeout(1.0)
    t.bind(("127.0.0.1", 0))
    dst = ("127.0.0.1", rb.port)
    ok = True

    def check(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print("  %-4s %s" % ("PASS" if cond else "FAIL", name))
    t.sendto(b"P,7,123456\n", dst)
    check("P answered with Q at once", t.recvfrom(100)[0] == b"Q,7,123456\n")
    t.sendto(b"WHO?\n", dst)
    got = t.recvfrom(100)[0] + t.recvfrom(100)[0]
    check("WHO? answered with HELLO and I", b"HELLO,%s,2" % ROLE.encode() in got and b"I,%s,2" % ROLE.encode() in got)
    for line in ["F", "A,100", "X", "R", "T,20,100,350"]:
        t.sendto(line.encode() + b"\n", dst)
    time.sleep(0.15)
    sent = [a[1] for a in fake.sent if a[0] == "line"]
    check("forwarded to the microcontroller: %s" % ", ".join(["F", "A,100", "X", "R", "T,20,100,350"]), all(c in sent for c in ["F", "A,100", "X", "R", "T,20,100,350"]))
    if LATEST:
        for i in range(20):
            t.sendto(("D,%d,%d,0\n" % (i, i)).encode(), dst)
        time.sleep(0.2)
        ds = [a[1] for a in fake.sent if a[0] == "line" and a[1].startswith("D,")]
        check("newest D wins, old ones are dropped (%d of 20 sent on)" % len(ds), ds and ds[-1] == "D,19,19,0" and len(ds) < 20)
    fake.provided["mcu_line"]("K" if ROLE == "tower" else "S,0,100,0")
    check("a line from the sketch reaches the laptop", t.recvfrom(100)[0].startswith(b"K" if ROLE == "tower" else b"S,0,100,0"))
    time.sleep(2.2)
    fake.provided["mcu_line"]("B,L")
    t.settimeout(0.3)
    try:
        t.recvfrom(100)
        check("after 2 s of silence nothing is sent to the laptop", False)
    except socket.timeout:
        check("after 2 s of silence nothing is sent to the laptop", True)
    rb.stop.set()
    print("selftest", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    wifi_full_speed()
    rb = RelayBridge()
    rb.start()
    print("%s bridge up on %s:%d (%s Bridge)" % (ROLE, rb.ip, rb.port, "real" if REAL else "fake"))
    App.run()


if __name__ == "__main__":
    main()
