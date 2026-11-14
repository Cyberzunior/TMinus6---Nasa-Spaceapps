"""Debris (scenario pieces and objects the robot's ultrasonic sensor finds) and asteroids (the tower's paper balls)."""
import json
import math
import os
import random
import config as C
from core.model import in_arc, predict_pose

WARN, FIRED, FLY = "warn", "fired", "fly"


class Debris:
    def __init__(self, x, y, r, real, seed=0):
        self.x, self.y, self.r, self.real, self.seed = x, y, r, real, seed
        rnd = random.Random(seed)
        self.rot = rnd.uniform(0, 360)
        self.spin = rnd.choice((-1, 1)) * rnd.uniform(8, 25)      # degrees per second, drawing only
        self.angle = math.degrees(math.atan2(y, x)) % 360.0
        self.confirmed_t = -99.0       # last time the robot's sensor saw it
        self.hit_t = -99.0
        self.rel = None                # craft angle relative to the piece, for counting dodges


class Detected:
    """Something the ultrasonic sensor found that the scenario does not know about."""

    def __init__(self, x, y, t):
        self.x, self.y, self.r, self.expire = x, y, 3.0, t + C.DETECT_TTL_S


class Asteroid:
    def __init__(self, tower, target, max_dist, burns):
        self.x0, self.y0 = tower
        d = math.hypot(target[0] - tower[0], target[1] - tower[1]) or 1.0
        self.dx, self.dy = (target[0] - tower[0]) / d, (target[1] - tower[1]) / d
        self.target, self.target_dist = target, d
        self.speed = C.ASTEROID_SPEED
        self.max_dist, self.burns = max_dist, burns
        self.state, self.timer, self.dist = WARN, C.ASTEROID_WARN_S, 0.0
        self.offline = False           # no K came back: the screen asteroid flies alone
        self.rot, self.spin = random.uniform(0, 360), random.choice((-1, 1)) * random.uniform(120, 260)
        self.seed = random.randrange(1 << 30)
        self.age = 0.0

    def bearing(self):
        """Degrees between the launch line and the tower-to-Earth line (what the pan servo must turn)."""
        straight = math.degrees(math.atan2(-self.y0, -self.x0))
        return (math.degrees(math.atan2(self.dy, self.dx)) - straight + 180.0) % 360.0 - 180.0

    def pos(self, ahead=0.0):
        """Position `ahead` seconds from now; None after it burned up or left the board."""
        delay = self.timer if self.state == WARN else 0.0
        d = self.dist + self.speed * max(0.0, ahead - delay)
        if d > self.max_dist:
            return None
        return self.x0 + self.dx * d, self.y0 + self.dy * d


class HazardField:
    def __init__(self, path=None):
        self.debris, self.detected, self.asteroids = [], [], []
        self.tower, self.sector = (C.BOARD_W / 2 + 2, C.BOARD_H / 2 - 6), (20.0, 110.0)
        self.problem = ""
        self.load(path or os.path.join(C.HERE, C.SCENARIO_FILE))

    def load(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                s = json.load(f)
            pieces = []
            for i, d in enumerate(s.get("debris", [])):
                if "x" in d:
                    x, y = float(d["x"]), float(d["y"])
                else:
                    a, r = math.radians(float(d["angle_deg"])), C.ORBIT_R + float(d.get("offset_cm", 0))
                    x, y = r * math.cos(a), r * math.sin(a)
                pieces.append(Debris(x, y, float(d.get("size", 3.0)), bool(d.get("real", False)), seed=i + 1))
            self.debris = pieces
            if "tower" in s:
                self.tower = (float(s["tower"]["x"]), float(s["tower"]["y"]))
            if "asteroid_sector_deg" in s:
                self.sector = tuple(float(a) % 360.0 for a in s["asteroid_sector_deg"])
        except (OSError, ValueError, KeyError, TypeError) as e:
            self.problem = "scenario file problem (%s): playing without debris" % e
            self.debris = []

    def reset(self):
        self.detected, self.asteroids = [], []
        for d in self.debris:
            d.confirmed_t, d.hit_t, d.rel = -99.0, -99.0, None

    # ---- ultrasonic scan -> board
    def add_scan(self, pose, angle, cm, t):
        """One S,angle,cm reading placed on the board with the robot's pose. Returns "confirm", "new" or None."""
        if not C.USE_ROBOT_SCAN or cm <= 2 or cm > C.SCAN_MAX_CM:
            return None
        a = math.radians(pose.theta + C.SCAN_SIGN * angle)
        px = pose.x + (cm + C.SENSOR_FWD) * math.cos(a)
        py = pose.y + (cm + C.SENSOR_FWD) * math.sin(a)
        if min(C.BOARD_W / 2 - abs(px), C.BOARD_H / 2 - abs(py)) < 8 or math.hypot(px, py) < C.EARTH_R + 5:
            return None                          # the border and the Earth stand are already on the map
        for d in self.debris:
            if d.real and math.hypot(px - d.x, py - d.y) < d.r + 8:
                d.confirmed_t = t
                return "confirm"
        for o in self.detected:
            if math.hypot(px - o.x, py - o.y) < 6:
                o.x, o.y, o.expire = (o.x + px) / 2, (o.y + py) / 2, t + C.DETECT_TTL_S
                return "confirm"
        self.detected.append(Detected(px, py, t))
        return "new"

    def tick(self, dt, t):
        for d in self.debris:
            d.rot = (d.rot + d.spin * dt) % 360.0
        self.detected = [o for o in self.detected if o.expire > t]

    # ---- queries
    def clearance(self, x, y, ahead=0.0):
        """Smallest gap (cm) between a craft at (x, y), `ahead` seconds from now, and anything it can hit.
        Returns (gap, kind, hazard_x, hazard_y)."""
        cr = C.CRAFT_R
        best = (min(C.BOARD_W / 2 - abs(x), C.BOARD_H / 2 - abs(y)) - cr, "border", x, y)
        g = math.hypot(x, y) - C.EARTH_R - cr
        if g < best[0]:
            best = (g, "earth", 0.0, 0.0)
        for d in self.debris:
            g = math.hypot(x - d.x, y - d.y) - d.r - cr
            if g < best[0]:
                best = (g, "debris", d.x, d.y)
        for o in self.detected:
            g = math.hypot(x - o.x, y - o.y) - o.r - cr
            if g < best[0]:
                best = (g, "object", o.x, o.y)
        for a in self.asteroids:
            p = a.pos(ahead)
            if p:
                g = math.hypot(x - p[0], y - p[1]) - C.ASTEROID_R - cr
                if g < best[0]:
                    now = a.pos(0.0) or p
                    best = (g, "asteroid", now[0], now[1])
        return best

    def nearest(self, x, y):
        """(distance to the nearest hazard's edge, kind), ignoring the border and Earth."""
        best = (999.0, "")
        for d in self.debris:
            best = min(best, (math.hypot(x - d.x, y - d.y) - d.r, "debris"))
        for o in self.detected:
            best = min(best, (math.hypot(x - o.x, y - o.y) - o.r, "object"))
        for a in self.asteroids:
            p = a.pos()
            if p and a.state == FLY:
                best = min(best, (math.hypot(x - p[0], y - p[1]) - C.ASTEROID_R, "asteroid"))
        return best

    # ---- asteroids
    def _ray(self, target):
        tx, ty = self.tower
        d = math.hypot(target[0] - tx, target[1] - ty) or 1.0
        dx, dy = (target[0] - tx) / d, (target[1] - ty) / d
        s, burns = 0.0, False
        while s < 400:                           # walk the line until Earth or the far border
            s += 0.5
            x, y = tx + dx * s, ty + dy * s
            if math.hypot(x, y) < C.EARTH_R + C.ASTEROID_R:
                burns = True
                break
            if s > d and (abs(x) > C.BOARD_W / 2 or abs(y) > C.BOARD_H / 2):
                break
        return s, burns

    def plan_asteroid(self, pose, speed, turn, force=False):
        """Aim at where the craft will be when the ball arrives. Returns an Asteroid in WARN state, or None when
        the craft is neither inside nor heading into the asteroid sector."""
        tx, ty = self.tower
        lead = C.ASTEROID_WARN_S + C.SIM_TOWER_K_MS / 1000.0
        t = lead + 2.0
        target = pose
        for _ in range(4):                       # flight time depends on the target, so iterate
            target = predict_pose(pose, speed, turn, t)
            t = lead + math.hypot(target.x - tx, target.y - ty) / C.ASTEROID_SPEED
        if not force and not (in_arc(pose.angle(), self.sector) or in_arc(target.angle(), self.sector)):
            return None
        max_dist, burns = self._ray((target.x, target.y))
        a = Asteroid(self.tower, (target.x, target.y), max_dist, burns)
        self.asteroids.append(a)
        return a
