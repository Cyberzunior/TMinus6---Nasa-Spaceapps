"""The single shared state object. Device threads and the main loop meet here, always under the lock."""
import threading
import config as C

DEVICES = ("pad", "robot", "tower", "station", "camera")


class DeviceStatus:
    def __init__(self, name):
        self.name = name
        self.connected = False
        self.where = ""          # IP:port, COM port, pad name or URL
        self.fw = None
        self.rtt_ms = None
        self.loss = 0.0
        self.note = ""
        self.sim = False
        self.rx_rate = 0.0
        self.tx_rate = 0.0

    def color(self):
        """green = healthy, yellow = connected but slow / lossy / wrong firmware, red = missing."""
        if not self.connected:
            return "red"
        if self.rtt_ms is not None and self.rtt_ms > C.RTT_WARN_MS:
            return "yellow"
        if self.loss > C.LOSS_WARN or (self.fw is not None and self.fw != C.FW_VERSION):
            return "yellow"
        return "green"

    def problem(self):
        if not self.connected:
            return "missing"
        if self.fw is not None and self.fw != C.FW_VERSION:
            return "firmware mismatch (v%s, want v%s)" % (self.fw, C.FW_VERSION)
        if self.rtt_ms is not None and self.rtt_ms > C.RTT_WARN_MS:
            return "slow link"
        if self.loss > C.LOSS_WARN:
            return "packet loss"
        return ""


class SharedState:
    def __init__(self):
        self.lock = threading.RLock()
        self.devices = {n: DeviceStatus(n) for n in DEVICES}
        # input thread
        self.stick = (0.0, 0.0)          # (speed, turn) after dead zone and curve
        self.raw_axes = []
        self.keys = (0.0, 0.0)           # keyboard fallback, written by the main loop
        self.pad = None                  # pygame joystick, set by the main loop
        # mixer
        self.drive_enabled = False       # False in menus, pause, game over: the robot gets zero
        self.ap_on = False
        self.ap_cmd = (0.0, 0.0)         # written by the auto-pilot at 60 Hz
        self.turn_scale = 1.0            # weather penalty, applied before the mixer so both bodies get it
        self.cmd = (0.0, 0.0, 0, 0)      # (speed, turn, left, right): the numbers both bodies use
        self.test_cmd = None             # (left, right) wheel test from Hardware Check / calibration, else None
        self.threads = {}                # name -> last heartbeat time, for the debug overlay

    def device(self, name):
        return self.devices[name]

    def snapshot(self):
        with self.lock:
            return {n: (d.connected, d.color(), d.where, d.fw, d.rtt_ms, d.loss, d.note, d.sim)
                    for n, d in self.devices.items()}

    def beat(self, name, t):
        self.threads[name] = t
