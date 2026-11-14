"""Gamepad polling and the ONE mixer, in their own thread at INPUT_HZ (default 120).

The thread reads the stick (or the keyboard fallback), applies the dead zone and expo curve, picks the stick or the
auto-pilot, runs mix() once, and stores the result in the shared state. The game craft reads that same stored
command, and this thread sends the same numbers to the robot as one small UDP line every 20 ms (and at once when
they change). Nothing here waits for an acknowledgement.

SDL only refreshes joystick values when events are pumped. The hint below makes SDL refresh them in its own
thread, so reading axes here works while the main thread draws. Verify on your pad with tools/gamepad_test.py."""
import os
import threading
import time

os.environ.setdefault("SDL_JOYSTICK_THREAD", "1")
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")

import config as C
from core.clock import now
from core.model import mix, shape_axis


def trigger_scale(brake, boost):
    """Speed scale 0.5..1. Triggers read -1 (released) .. 1 (pressed); some drivers use 0..1."""
    b = max(0.0, min(1.0, (brake + 1.0) / 2.0)) if brake < -0.01 or brake > 0.01 else 0.0
    u = max(0.0, min(1.0, (boost + 1.0) / 2.0)) if boost < -0.01 or boost > 0.01 else 0.0
    base = C.TRIGGER_BASE
    return max(0.5, min(1.0, base + (1.0 - base) * u - (base - 0.5) * b))


def read_pad(pad):
    """Returns (speed, turn, scale, raw_axes). Speed is positive when the stick is pushed up."""
    n = pad.get_numaxes()
    raw = [pad.get_axis(i) for i in range(n)]
    turn = raw[C.AXIS_TURN] if C.AXIS_TURN < n else 0.0
    speed = -raw[C.AXIS_SPEED] if C.AXIS_SPEED < n else 0.0
    brake = raw[C.AXIS_BRAKE] if 0 <= C.AXIS_BRAKE < n else -1.0
    boost = raw[C.AXIS_BOOST] if 0 <= C.AXIS_BOOST < n else -1.0
    return shape_axis(speed), shape_axis(turn), trigger_scale(brake, boost), raw


class InputThread(threading.Thread):
    def __init__(self, state, robot, log):
        super().__init__(daemon=True, name="input")
        self.state, self.robot, self.log = state, robot, log
        self.stop_flag = threading.Event()
        self.rate = 0.0
        self.sent = 0
        self._last = None
        self._t_send = 0.0
        self.errors = 0

    def compute(self):
        """One mixer pass. Returns the command tuple (speed, turn, left, right)."""
        st = self.state
        speed = turn = 0.0
        scale = 1.0
        raw = []
        pad = st.pad
        if pad is not None:
            try:
                speed, turn, scale, raw = read_pad(pad)
            except Exception:
                self.errors += 1
        if speed == 0.0 and turn == 0.0:                    # the keyboard fallback only when the pad is idle
            speed, turn = st.keys
            scale = 1.0
        st.raw_axes = raw
        st.stick = (speed, turn)
        tc = st.test_cmd
        if tc is not None:                                    # a wheel test: exactly these wheel speeds
            return (0.0, 0.0, int(tc[0]), int(tc[1]))
        if not st.drive_enabled:
            s = t = 0.0
        elif st.ap_on:
            s, t = st.ap_cmd                                  # the auto-pilot already includes the stick nudge
        else:
            s, t = speed * scale, turn
        return mix(s, t * st.turn_scale)                   # weather penalty here, so both bodies get it

    def run(self):
        period = 1.0 / C.INPUT_HZ
        t_rate, n = now(), 0
        nxt = now()
        while not self.stop_flag.is_set():
            try:
                cmd = self.compute()
                with self.state.lock:
                    self.state.cmd = cmd
                t = now()
                changed = self._last is None or abs(cmd[0] - self._last[0]) > C.CMD_EPS or abs(cmd[1] - self._last[1]) > C.CMD_EPS
                if changed or t - self._t_send >= 1.0 / C.SEND_HZ:
                    self._t_send, self._last = t, cmd
                    if self.robot.send_drive(cmd[2], cmd[3], int(self.state.ap_on)):
                        self.sent += 1
                n += 1
                if t - t_rate >= 1.0:
                    self.rate, t_rate, n = n / (t - t_rate), t, 0
                self.state.beat("input", t)
            except Exception as e:
                self.errors += 1
                self.log("input thread error: %r" % e)
            nxt += period
            delay = nxt - now()
            if delay > 0:
                time.sleep(delay)
            else:
                nxt = now()

    def stop(self):
        self.stop_flag.set()


def rumble(pad, strength=0.6, ms=250):
    """Never fails: not every pad or driver supports it."""
    if not C.RUMBLE or pad is None:
        return
    try:
        pad.rumble(strength, strength, ms)
    except Exception:
        pass
