"""The rules of a run, with no drawing and no hardware code: it talks to the devices through three small link
objects and reads the mixed command from the shared state. Runs headless in the tests."""
import collections
import math
import random
import config as C
from core import hazards as hz
from core import weather as wx
from core.autopilot import Autopilot
from core.calibration import aim_servo
from core.lives import Lives
from core.model import angdiff, in_arc, start_pose, step_pose


class NullLink:
    """Stands in for a device link in tests and when a link is not built."""
    connected = False
    front_stop = False

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *a, **k: False

    def one_way_s(self):
        return 0.0


class Game:
    def __init__(self, state, robot=None, tower=None, station=None, log=None):
        self.state = state
        self.robot, self.tower, self.station = robot or NullLink(), tower or NullLink(), station or NullLink()
        self.log = log or (lambda msg: None)
        self.field = hz.HazardField()
        self.weather = wx.WeatherModel()
        self.autopilot = Autopilot()
        self.lives = Lives()
        self.fx, self.toasts = [], []            # drained by the renderer / HUD
        self.practice = False
        self.demo = False
        self.reset()

    # ---- lifecycle
    def reset(self, practice=False, demo=None):
        """Back to the start mark with 15 lives. Unlatches the robot, re-arms the tower, resets the station."""
        self.practice = practice
        self.demo = C.DEMO_MODE if demo is None else demo
        self.craft, self.ghost = start_pose(), start_pose()
        self.lives = Lives(practice)
        self.field.reset()
        self.autopilot.reset()
        zone_forced = None
        self.weather.forced = zone_forced
        self.weather.spike_until = -1.0
        self.t = 0.0
        self.over, self.over_t = False, 0.0
        self.streak = self.best_streak = 0.0
        self.dodged = 0
        self.ap_time = 0.0
        self.speed_cms = 0.0
        self.next_asteroid_t = C.ASTEROID_GAP_S
        self.demo_i = 0
        self.tower_note = ""
        self.radar, self.bump_t = {}, {}
        self._history = collections.deque()      # (t, speed, turn) for the sync delay and the ghost
        self._zone_sent = None
        with self.state.lock:
            self.state.ap_on = False
            self.state.ap_cmd = (0.0, 0.0)
            self.state.turn_scale = 1.0
        self.robot.latch(False)
        self.tower.set_armed(True)
        self.station.reset()
        self.station.set_lives(self.lives.lives)
        self.log("run reset (%s)" % ("practice" if practice else "play"))

    # ---- inputs
    def toggle_autopilot(self):
        with self.state.lock:
            self.state.ap_on = not self.state.ap_on
            on = self.state.ap_on
        self.autopilot.reset()
        self.log("auto-pilot %s" % ("on" if on else "off"))
        return on

    def fire_test_asteroid(self):
        """X in practice mode."""
        if self.practice and not self.field.asteroids and not self.over:
            return self._spawn(force=True)
        return False

    def force_zone(self, zone):
        """Rehearsal keys: H hot, K cold, N back to the real state."""
        self.weather.forced = zone
        self.log("zone forced: %s" % ("off" if zone is None else wx.NAMES[zone]))

    def handle(self, ev):
        """One event from a device thread."""
        kind, d = ev.kind, ev.data
        if kind == "scan":
            self.robot_scan = d
            self.radar[d[0]] = (d[1], self.wall)
            self.field.add_scan(self.ghost, d[0], d[1], self.t)
        elif kind == "bumper" and not self.over:
            self.bump_t[d[0]] = self.wall
            if C.DRIFT_CORRECTION > 0 and self.field.debris:      # the robot is touching something real
                near = min(self.field.debris, key=lambda q: math.hypot(q.x - self.ghost.x, q.y - self.ghost.y))
                dist = math.hypot(near.x - self.ghost.x, near.y - self.ghost.y)
                if near.real and 0 < dist < 20:
                    k = C.DRIFT_CORRECTION * (1 - (near.r + C.CRAFT_R) / dist)
                    self.ghost.x += (near.x - self.ghost.x) * k
                    self.ghost.y += (near.y - self.ghost.y) * k
            self._hit("bumper", self.craft.x, self.craft.y)
        elif kind == "tower_k":
            for a in self.field.asteroids:
                if a.state == hz.FIRED:
                    a.state = hz.FLY
        elif kind == "weather":
            self.weather.on_station(d[0], d[1], d[2], self.wall)
        elif kind == "robot_air":
            self.weather.on_robot_air(d[0], d[1], self.wall)
        elif kind == "device_down" and d[0] == "station":
            self.weather.station_lost()

    # ---- helpers
    def _hit(self, kind, x, y):
        if not self.lives.hit(kind, self.t):
            return False
        self.streak = 0.0
        self.fx.append(("hit", x, y, kind))
        self.station.set_lives(self.lives.lives)
        self.log("HIT by %s, %d lives left" % (kind, self.lives.lives))
        if self.lives.dead:
            self.over, self.over_t = True, self.t
            self.robot.latch(True)
            self.tower.set_armed(False)
            self.station.game_over()
            self.fx.append(("gameover", x, y, kind))
            self.log("GAME OVER at T+%.0f s" % self.t)
        return True

    def _spawn(self, force=False):
        speed, turn = self.state.cmd[0], self.state.cmd[1]
        a = self.field.plan_asteroid(self.craft, speed, turn, force)
        if a is None:
            return False
        if C.TOWER_HAS_PAN:
            self.tower.aim(aim_servo(a.bearing()))
        self.fx.append(("asteroid_warn", a.x0, a.y0, ""))
        self.log("asteroid incoming")
        return True

    def _collide(self, pose):
        """Keep a body on the board and out of Earth and debris. Returns the debris piece it touched, if any."""
        cr = C.CRAFT_R
        pose.x = max(-C.BOARD_W / 2 + cr, min(C.BOARD_W / 2 - cr, pose.x))
        pose.y = max(-C.BOARD_H / 2 + cr, min(C.BOARD_H / 2 - cr, pose.y))
        touched = None
        for ox, oy, r, piece in [(0.0, 0.0, C.EARTH_R, None)] + [(d.x, d.y, d.r, d) for d in self.field.debris]:
            dist = math.hypot(pose.x - ox, pose.y - oy)
            if dist < r + cr:
                k = (r + cr) / (dist or 1.0)
                pose.x, pose.y = ox + (pose.x - ox) * k, oy + (pose.y - oy) * k
                touched = piece or touched
        return touched

    def _delayed(self, delay):
        """The command from `delay` seconds ago."""
        want = self.t - delay
        best = self._history[0] if self._history else (0.0, 0.0, 0.0)
        for item in self._history:
            if item[0] <= want:
                best = item
            else:
                break
        return best[1], best[2]

    def zone_of(self, pose):
        a = pose.angle()
        return wx.HOT if in_arc(a, C.HOT_ZONE) else wx.COLD if in_arc(a, C.COLD_ZONE) else wx.NORMAL

    # ---- one frame
    wall = 0.0
    robot_scan = None

    def step(self, dt, wall=None):
        """Advance the run by dt seconds. `wall` is the real clock, used for weather history."""
        self.wall = self.t if wall is None else wall
        st = self.state
        if self.over:
            self._weather()
            return
        speed, turn = st.cmd[0], st.cmd[1]
        self._history.append((self.t, speed, turn))
        while len(self._history) > 2 and self._history[1][0] < self.t - 1.0:
            self._history.popleft()

        # craft: the mixed command, optionally delayed so the screen matches the robot
        cs, ct = self._delayed(C.SYNC_DELAY_MS / 1000.0) if C.SYNC_DELAY_MS > 0 else (speed, turn)
        step_pose(self.craft, cs, ct, dt)
        self.speed_cms = cs * C.V_MAX
        piece = self._collide(self.craft)
        if piece is not None:
            piece.hit_t = self.t
            self._hit("debris", self.craft.x, self.craft.y)

        # robot ghost: the same commands, as late as the link makes them; stopped when the robot is
        if self.robot.connected:
            gs, gt = self._delayed(self.robot.one_way_s())
            if self.robot.front_stop and gs > 0:
                gs = 0.0
            step_pose(self.ghost, gs, gt, dt)
            self._collide(self.ghost)

        self.field.tick(dt, self.t)
        self._asteroids(dt)
        self._dodges()
        self._weather()

        if st.ap_on:
            st.ap_cmd = self.autopilot.decide(self.craft, self.field, st.stick[0], st.stick[1], dt)
        self.lives.tick(dt)
        self.t += dt
        if st.ap_on:
            self.ap_time += dt
        if not self.lives.protected():
            self.streak += dt
            self.best_streak = max(self.best_streak, self.streak)

    def idle(self, dt, wall):
        """Menus, pause, hardware check: the weather (real sensor, zones, demo keys) keeps working, nothing else moves."""
        self.wall = wall
        self._weather()
        self.field.tick(dt, self.t)

    def _weather(self):
        w = self.weather
        w.set_zone(self.zone_of(self.craft) if not self.over else wx.NORMAL)
        for ev in w.update(self.wall):
            if ev[0] == "state":
                if ev[2] == wx.NORMAL:
                    self.toasts.append(("Temperature back to normal", "ok"))
                self.fx.append(("weather", 0, 0, wx.NAMES[ev[2]]))
                self.log("weather %s -> %s" % (wx.NAMES[ev[1]], wx.NAMES[ev[2]]))
            elif ev[0] == "spike":
                self.fx.append(("spike", 0, 0, ""))
                self.log("temperature spike %.1f C in %d s" % (ev[1], C.SPIKE_WINDOW_S))
        self.station.set_zone(w.game_zone() if not self.over else wx.NORMAL)
        penalty = C.WEATHER_TURN_PENALTY if w.state != wx.NORMAL else 0.0
        self.state.turn_scale = 1.0 - penalty

    def _asteroids(self, dt):
        self.tower.allow(not self.over)
        for a in self.field.asteroids[:]:
            a.age += dt
            a.rot = (a.rot + a.spin * dt) % 360.0
            if a.state == hz.WARN:
                a.timer -= dt
                if a.timer <= 0:
                    sent = self.tower.fire()
                    if self.tower.connected and sent:
                        a.state, a.timer = hz.FIRED, C.ASTEROID_K_TIMEOUT_S
                        self.tower_note = ""
                    else:                         # no tower: the screen asteroid flies alone
                        a.state, a.offline = hz.FLY, True
                        self.tower_note = "TOWER OFFLINE"
                    self.fx.append(("asteroid_fire", a.x0, a.y0, ""))
            elif a.state == hz.FIRED:
                a.timer -= dt
                if a.timer <= 0:
                    a.state, a.offline = hz.FLY, True
                    self.tower_note = "TOWER OFFLINE"
            else:
                a.dist += a.speed * dt
                p = a.pos()
                if p is None:
                    self.field.asteroids.remove(a)
                    self.dodged += 1
                    end = (a.x0 + a.dx * a.max_dist, a.y0 + a.dy * a.max_dist)
                    self.fx.append(("burn" if a.burns else "miss", end[0], end[1], ""))
                    continue
                in_lane = abs(math.hypot(*p) - C.ORBIT_R) <= C.LANE_WIDTH / 2
                if in_lane and math.hypot(p[0] - self.craft.x, p[1] - self.craft.y) < C.ASTEROID_R + C.CRAFT_R:
                    self.field.asteroids.remove(a)
                    if not self._hit("asteroid", p[0], p[1]):
                        self.fx.append(("miss", p[0], p[1], ""))
        if self.over:
            return
        if self.demo:
            while self.demo_i < len(C.DEMO_SCRIPT) and self.t >= C.DEMO_SCRIPT[self.demo_i][0]:
                action = C.DEMO_SCRIPT[self.demo_i][1]
                self.demo_i += 1
                if action == "asteroid":
                    if not self.field.asteroids:
                        self._spawn(force=True)
                elif action in ("hot", "cold", "normal"):
                    self.force_zone({"hot": wx.HOT, "cold": wx.COLD, "normal": None}[action])
        elif not self.practice and self.t >= self.next_asteroid_t and not self.field.asteroids:
            if self._spawn():
                self.next_asteroid_t = self.t + C.ASTEROID_GAP_S + random.uniform(0, C.ASTEROID_GAP_JITTER_S)

    def _dodges(self):
        """Passing a debris piece without touching it counts as one dodge."""
        ang = self.craft.angle()
        for d in self.field.debris:
            rel = angdiff(ang, d.angle)
            if d.rel is not None and d.rel * C.ORBIT_DIR < 0 <= rel * C.ORBIT_DIR and abs(rel) < 30 \
                    and self.t - d.hit_t > 3:
                self.dodged += 1
                self.fx.append(("dodged", d.x, d.y, ""))
            d.rel = rel

    def results(self):
        h = self.lives.hits
        return {"time": self.t, "debris": h["debris"] + h["bumper"], "asteroid": h["asteroid"],
                "dodged": self.dodged, "best_streak": self.best_streak}
