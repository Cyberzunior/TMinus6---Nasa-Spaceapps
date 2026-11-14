import random
import config as C
from core import hazards as hz
from core import weather as wx
from core.autopilot import lane_control
from core.events import Event
from core.game import Game
from core.lives import Lives
from core.model import mix
from core.state import SharedState
from core.statemachine import StateMachine, BOOT, MENU, PLAY, PAUSE, GAMEOVER, RESULTS, HWCHECK, CALIBRATE


class Rec:
    """A device link that records every call."""
    connected = True
    front_stop = False

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *a, **k: (self.calls.append((name,) + a) or True)

    def one_way_s(self):
        return 0.0

    def names(self):
        return [c[0] for c in self.calls]


def make(practice=False):
    st = SharedState()
    r, t, s = Rec(), Rec(), Rec()
    g = Game(st, r, t, s)
    g.reset(practice=practice)
    for x in (r, t, s):
        x.calls.clear()
    st.drive_enabled = True
    return g, st, r, t, s


def run(g, st, seconds, cmd=(0.0, 0.0), dt=1 / 60):
    st.cmd = mix(*cmd)
    n = int(seconds / dt)
    for _ in range(n):
        g.step(dt)
    return n


def test_each_hit_takes_exactly_one_life_then_1_5_s_protection():
    L = Lives()
    assert L.hit("debris") and L.lives == 14
    assert not L.hit("asteroid") and L.lives == 14        # inside the protection
    L.tick(1.4)
    assert not L.hit("bumper")
    L.tick(0.2)
    assert L.hit("bumper") and L.lives == 13
    assert L.hits == {"debris": 1, "asteroid": 0, "bumper": 1}


def test_practice_mode_loses_no_lives():
    L = Lives(practice=True)
    assert L.hit("debris") and L.lives == 15


def test_bumper_debris_and_asteroid_each_cost_one_heart():
    g, st, r, t, s = make()
    g.handle(Event("bumper", ("L",)))
    assert g.lives.lives == 14 and ("set_lives", 14) in s.calls
    g.lives.tick(2.0)
    d = g.field.debris[0]
    g.craft.x, g.craft.y = d.x + 1.0, d.y
    run(g, st, 0.02)
    assert g.lives.lives == 13
    g.lives.tick(2.0)
    run(g, st, 0.02)                                       # still overlapping, but the piece pushes the craft out
    g.lives.tick(2.0)
    a = hz.Asteroid(g.field.tower, (g.craft.x, g.craft.y), 500, False)
    a.state, a.dist = hz.FLY, a.target_dist - 0.5
    g.field.asteroids.append(a)
    g.craft.x, g.craft.y = (a.x0 + a.dx * a.dist, a.y0 + a.dy * a.dist)
    run(g, st, 0.05)
    assert g.lives.hits["asteroid"] == 1 or g.lives.lives <= 12


def test_no_second_hit_during_protection():
    g, st, *_ = make()
    g.handle(Event("bumper", ("L",)))
    for _ in range(5):
        g.handle(Event("bumper", ("R",)))
    assert g.lives.lives == 14


def test_game_over_sequence():
    g, st, r, t, s = make()
    g.lives.lives = 1
    g.handle(Event("bumper", ("L",)))
    assert g.over and g.lives.lives == 0
    assert ("latch", True) in r.calls                      # the robot is latched
    assert ("set_armed", False) in t.calls                 # the tower is disarmed
    assert "game_over" in s.names()                        # G to the weather station
    t0 = g.t
    run(g, st, 1.0, (1.0, 0.0))
    assert g.t == t0                                       # the game is frozen
    g.reset()                                              # Start: 15 lives, everything released
    assert g.lives.lives == 15 and not g.over
    assert ("latch", False) in r.calls and ("set_armed", True) in t.calls and "reset" in s.names()


def test_asteroid_sequence_warn_aim_fire_k():
    g, st, r, t, s = make()
    assert g._spawn(force=True)
    a = g.field.asteroids[0]
    assert a.state == hz.WARN
    run(g, st, C.ASTEROID_WARN_S - 0.2)
    assert "fire" not in t.names()                         # still in the one second warning
    run(g, st, 0.25)
    names = t.names()
    assert "fire" in names and names.count("fire") == 1
    if C.TOWER_HAS_PAN:
        assert names.index("aim") < names.index("fire")    # aim first, then fire
    assert a.state == hz.FIRED
    pos_before = a.dist
    run(g, st, 0.1)
    assert a.dist == pos_before and a.state == hz.FIRED    # the screen asteroid waits for K (the timeout is 0.25 s)
    g.handle(Event("tower_k", ()))
    assert a.state == hz.FLY
    run(g, st, 0.1)
    assert a.dist > pos_before


def test_asteroid_starts_anyway_if_no_k_arrives():
    g, st, r, t, s = make()
    g._spawn(force=True)
    run(g, st, C.ASTEROID_WARN_S + C.ASTEROID_K_TIMEOUT_S + 0.2)
    a = g.field.asteroids[0]
    assert a.state == hz.FLY and a.offline and g.tower_note == "TOWER OFFLINE"


def test_virtual_asteroid_when_tower_missing():
    g, st, r, t, s = make()
    t.connected = False
    g._spawn(force=True)
    run(g, st, C.ASTEROID_WARN_S + 0.1)
    assert g.field.asteroids[0].state == hz.FLY and g.tower_note == "TOWER OFFLINE"


def test_practice_x_fires_asteroid_only_in_practice():
    g, *_ = make(practice=False)
    assert not g.fire_test_asteroid()
    g, *_ = make(practice=True)
    assert g.fire_test_asteroid() and not g.fire_test_asteroid()      # one at a time


def test_asteroid_flight_time_is_about_2_to_3_seconds_inside_the_sector():
    """Spawns only happen while the craft is in the asteroid sector; there the ball takes about 2-3 s to reach the lane."""
    import math
    g, st, *_ = make()
    a0, a1 = g.field.sector
    span = (a1 - a0) % 360
    for i in range(5):
        ang = math.radians(a0 + span * i / 4)
        g.craft.x, g.craft.y = C.ORBIT_R * math.cos(ang), C.ORBIT_R * math.sin(ang)
        g.field.asteroids.clear()
        a = g.field.plan_asteroid(g.craft, 0.0, 0.0, force=False)
        assert a is not None, "a craft standing in the sector must get an asteroid"
        flight = math.hypot(a.x0 - a.target[0], a.y0 - a.target[1]) / a.speed
        assert 1.5 <= flight <= 3.2, (round(a0 + span * i / 4), flight)
    g.field.asteroids.clear()
    g.craft.x, g.craft.y = 0.0, -C.ORBIT_R                  # 270 degrees: outside the sector and not heading in
    assert g.field.plan_asteroid(g.craft, 0.0, 0.0, force=False) is None


def test_weather_hysteresis_and_severity():
    w = wx.WeatherModel()
    w.on_station(24.0, 40, 0, 1.0)
    assert w.update(1.0) == [] and w.state == wx.NORMAL
    w.on_station(31.0, 40, 2, 2.0)
    assert ("state", wx.NORMAL, wx.HOT) in w.update(2.0)
    w.on_station(29.5, 40, 2, 3.0)
    w.update(3.0)
    assert w.state == wx.HOT                               # inside the 1 C hysteresis: stays hot
    w.on_station(28.9, 40, 0, 4.0)
    w.update(4.0)
    assert w.state == wx.NORMAL
    w.set_zone(wx.COLD)
    w.update(5.0)
    assert w.state == wx.COLD
    w.on_station(35.0, 40, 2, 6.0)
    w.update(6.0)
    assert w.state == wx.HOT                               # sensor HOT beats the game's COLD zone
    w.forced = wx.COLD
    assert w.game_zone() == wx.COLD


def test_weather_spike_and_trend():
    w = wx.WeatherModel()
    for i, tmp in enumerate((22.0, 22.5, 23.0)):
        w.on_station(tmp, 40, 0, float(i))
        w.update(float(i))
    assert w.trend == "rising" or w.trend == "steady"
    w.on_station(26.5, 40, 0, 4.0)
    ev = w.update(4.0)
    assert any(e[0] == "spike" for e in ev) and w.trend == "spike" and w.spike_active(4.5)
    assert not any(e[0] == "spike" for e in w.update(4.2))     # reported once, not every frame


def test_robot_air_sensor_forwards_state_to_the_station():
    w = wx.WeatherModel()
    w.on_robot_air(36.0, 30, 1.0)
    assert w.game_zone() == wx.HOT
    w.on_robot_air(10.0, 30, 2.0)
    assert w.game_zone() == wx.NORMAL                      # HOT ends first (1 C hysteresis) ...
    w.on_robot_air(10.0, 30, 4.0)
    assert w.game_zone() == wx.COLD                        # ... then the next reading says COLD


def test_game_zones_follow_the_craft_and_go_to_the_station():
    g, st, r, t, s = make()
    g.craft.x, g.craft.y = -C.ORBIT_R, 0.0                 # 180 degrees: the sunlit hot arc
    run(g, st, 0.05)
    assert g.weather.state == wx.HOT and ("set_zone", wx.HOT) in s.calls
    g.craft.x, g.craft.y = C.ORBIT_R, 0.0                  # 0 degrees: Earth's shadow
    run(g, st, 0.05)
    assert g.weather.state == wx.COLD


def test_weather_penalty_applies_to_the_command_not_just_the_screen():
    from devio.gamepad import InputThread
    st = SharedState()
    st.drive_enabled = True
    st.keys = (0.0, 1.0)
    st.turn_scale = 1.0
    th = InputThread(st, Rec(), lambda m: None)
    full = th.compute()
    st.turn_scale = 0.8
    pen = th.compute()
    assert abs(pen[1] - 0.8 * full[1]) < 1e-9 and abs(pen[2]) < abs(full[2])   # wheels get less turn too


def test_state_machine_flow():
    sm = StateMachine()
    assert sm.state == BOOT and not sm.go(PLAY)
    assert sm.go(MENU) and sm.go(PLAY) and sm.flying()
    assert sm.go(PAUSE) and sm.resume == PLAY and sm.go(PLAY)
    assert sm.go(GAMEOVER) and not sm.go(PLAY) and sm.go(RESULTS) and sm.go(MENU)
    assert sm.go(CALIBRATE) and sm.go(MENU) and sm.go(HWCHECK) and sm.go(MENU)
    assert sm.go(PLAY) and sm.go(PAUSE) and sm.go(HWCHECK) and sm.go(PAUSE)


def test_pause_resumes_into_practice_not_play():
    sm = StateMachine()
    sm.go(MENU)
    from core.statemachine import PRACTICE
    sm.go(PRACTICE)
    sm.go(PAUSE)
    assert not sm.go(PLAY) and sm.go(PRACTICE)


def test_demo_mode_script_runs():
    old = C.DEMO_MODE
    C.DEMO_MODE = True
    try:
        g, st, r, t, s = make()
        run(g, st, 21.0)
        assert g.weather.forced == wx.HOT and "fire" in t.names()
        run(g, st, 8.0)
        assert g.weather.forced is None
    finally:
        C.DEMO_MODE = old


def test_autopilot_dodges_10_of_10():
    """Dodge 10 of 10 in sim: ten random runs of 90 s, not a single hit."""
    for seed in range(1, 11):
        random.seed(seed)
        g, st, r, t, s = make()
        st.ap_on = True
        for _ in range(90 * 60):
            st.cmd = mix(*st.ap_cmd)
            g.step(1 / 60)
            if g.over:
                break
        h = g.lives.hits
        assert h["debris"] + h["asteroid"] == 0, (seed, h)
        assert g.t >= 89.0


def test_without_the_autopilot_a_craft_on_the_ring_does_get_hit():
    random.seed(1)
    g, st, *_ = make()
    for _ in range(60 * 120):
        st.cmd = mix(*lane_control(g.craft, C.ORBIT_R, C.AP_CRUISE))
        g.step(1 / 60)
        if g.over:
            break
    assert g.lives.hits["asteroid"] + g.lives.hits["debris"] >= 2


def test_ultrasonic_scan_confirms_real_debris_and_adds_unknown_objects():
    g, st, *_ = make()
    d = next(p for p in g.field.debris if p.real)
    import math
    g.ghost.x, g.ghost.y, g.ghost.theta = d.x - 25, d.y, 0.0
    assert g.field.add_scan(g.ghost, 0, 25 - d.r - C.SENSOR_FWD + 0, 1.0) in ("confirm", None)
    g.ghost.x, g.ghost.y, g.ghost.theta = 0.0, 20.0, 0.0
    assert g.field.add_scan(g.ghost, 0, 30, 1.0) == "new" and len(g.field.detected) == 1
    assert g.field.add_scan(g.ghost, 0, 30, 1.2) == "confirm" and len(g.field.detected) == 1
    g.field.tick(0.1, 10.0)
    assert not g.field.detected                            # forgotten after DETECT_TTL_S
    assert g.field.add_scan(g.ghost, 0, 500, 1.0) is None  # out of range is ignored
