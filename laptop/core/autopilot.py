"""The one auto-pilot. Its (speed, turn) goes into the same mixer as the stick, so the craft and the robot
dodge identically.

Ten times a second it rolls the craft forward along candidate lanes (the orbit ring, and rings inside / outside
it) against the predicted position of every hazard: debris, objects the robot's sensor found, asteroids on their
launch line, the border, Earth. If the ring is blocked it takes the lane with the biggest gap, slows down, and
eases back after a clear second."""
import math
import config as C
from core.model import angdiff, mix, Pose, step_pose

OFFSETS = (0, 6, -6, 10, -10, 14, -13)     # cm from the orbit ring
GAP_CAP = 8.0                              # gaps bigger than this all count as clear


def lane_control(pose, radius, spd):
    """Steer along a ring of this radius around Earth. Returns (speed, turn)."""
    r = pose.radius() or 1.0
    want = pose.angle() + C.ORBIT_DIR * (90.0 + math.degrees(math.atan((r - radius) / 12.0)))
    err = angdiff(want, pose.theta)
    ff = C.ORBIT_DIR * math.degrees(spd * C.V_MAX / r) / C.W_MAX          # the turn the circle itself needs
    turn = max(-1.0, min(1.0, err / 40.0 + ff))
    return (spd if abs(err) < 60 else spd * 0.3), turn


class Autopilot:
    def __init__(self):
        self.reset()

    def reset(self):
        self.dodge = None          # (offset, speed fraction) while dodging
        self.clear_t = 0.0
        self.zone = "clear"        # clear / warning / danger
        self.threat = None         # (kind, x, y)
        self.path = []             # planned path for drawing
        self._tick = 0.0

    def _rollout(self, pose, field, off, frac, keep=False):
        p = Pose(pose.x, pose.y, pose.theta)
        dt, worst, pts = 0.1, (1e9, None, 0.0, 0.0), []
        for i in range(int(C.AP_HORIZON_S / max(0.3, frac) / dt)):       # slower lanes look just as far ahead
            s, t = lane_control(p, C.ORBIT_R + off, C.AP_CRUISE * frac)
            s, t = mix(s, t)[:2]
            step_pose(p, s, t, dt)
            c = field.clearance(p.x, p.y, (i + 1) * dt)
            if c[0] < worst[0]:
                worst = c
            if keep and i % 2 == 0:
                pts.append((p.x, p.y))
        return worst, pts

    def _plan(self, pose, field, dt):
        nominal, pts = self._rollout(pose, field, 0, 1.0, keep=True)
        blocked = nominal[0] < C.AP_SAFE_CM
        dist = math.hypot(nominal[2] - pose.x, nominal[3] - pose.y) if blocked else 1e9
        if blocked and nominal[1] == "asteroid":
            dist = 0.0                              # a ball on a collision course is always the danger zone
        self.zone = "danger" if dist < C.AP_DANGER_CM else "warning" if dist < C.AP_WARN_CM else "clear"
        self.threat = nominal[1:] if blocked else None
        if not blocked:
            self.clear_t += dt
            if self.clear_t >= C.AP_CLEAR_S:
                self.dodge = None
            if self.dodge is None:
                self.path = pts
            return
        self.clear_t = 0.0
        if self.dodge is None and self.zone == "clear":
            self.path = pts
            return                                  # seen, but still outside the warning zone
        if nominal[1] == "asteroid":                # a crossing ball: also try to beat it or let it pass ahead
            speeds = (1.0 / C.AP_CRUISE, C.AP_WARN_SPEED, C.AP_DANGER_SPEED, 0.1)
        elif self.zone == "danger":
            speeds = (C.AP_DANGER_SPEED,)
        else:
            speeds = (C.AP_WARN_SPEED, C.AP_DANGER_SPEED)
        scores, paths = {}, {}
        for off in OFFSETS:
            for frac in speeds:
                worst, p = self._rollout(pose, field, off, frac, keep=True)
                scores[(off, frac)] = min(worst[0], GAP_CAP) - 0.12 * abs(off) - 1.0 * abs(1 - frac)
                paths[(off, frac)] = p
        best = max(scores, key=scores.get)
        if self.dodge not in scores or scores[best] > scores[self.dodge] + 1.5:
            self.dodge = best
        self.path = paths[self.dodge]

    def decide(self, pose, field, stick_speed, stick_turn, dt):
        """Returns (speed, turn) in -1..1 for the mixer."""
        self._tick -= dt
        if self._tick <= 0:                         # plan 10 times a second
            self._plan(pose, field, 0.1)
            self._tick = 0.1
        off, frac = self.dodge or (0, 1.0)
        speed, turn = lane_control(pose, C.ORBIT_R + off, C.AP_CRUISE * frac)
        if not (self.dodge and self.zone == "danger"):      # outside the danger zone the stick is a nudge
            speed += C.AP_NUDGE * stick_speed
            turn += C.AP_NUDGE * 2 * stick_turn
        return max(-1.0, min(1.0, speed)), max(-1.0, min(1.0, turn))

    def status(self):
        if self.dodge and self.zone != "clear":
            return "DODGING"
        if self.dodge:
            return "RETURNING"
        return "HOLDING ORBIT"
