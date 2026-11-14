"""The whole game, headless, with software devices: boot, menu, play, asteroid, hit, hot / cold warnings, game over,
restart. Also the safety rules at app level (pause, emergency stop, stick ignored after game over)."""
import time
import pygame
import config as C
from core import statemachine as S
from core import weather as wx


def make_app(**kw):
    pygame.init()
    from app import App, Args
    app = App(Args(sim=True, seed=5, no_audio=True, **kw), headless=True)
    app.boot_all()
    return app


def frames(app, n):
    last = time.perf_counter()
    for _ in range(n):
        now = time.perf_counter()
        app.frame(now - last)
        last = now
        time.sleep(0.003)


def wait_connected(app, timeout=8.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        frames(app, 5)
        if all(d.connected for d in app.state.devices.values()):
            return True
    return False


def test_full_round_in_sim():
    app = make_app()
    try:
        assert app.sm.state == S.MENU and wait_connected(app)
        assert app.hwcheck.ready(app)                              # --sim: auto-green
        app.menu_choice("PLAY")
        assert app.sm.state == S.PLAY and app.state.drive_enabled
        app._action("ap")
        frames(app, 30)
        assert app.state.ap_on
        app.game.fire_test_asteroid() or app.game._spawn(force=True)
        frames(app, 90)
        assert app.links["tower"].last_k > 0                      # the sim tower answered K
        app.sim_station.set_air(36.0)                             # hot air at the DHT11
        t0 = time.time()
        while time.time() - t0 < 4.0 and app.game.weather.state != wx.HOT:
            frames(app, 3)
        assert app.game.weather.state == wx.HOT and app.sim_station.lcd()[0] == "!! HOT ZONE !!"
        app.sim_station.set_air(11.0)
        t0 = time.time()
        while time.time() - t0 < 6.0 and app.game.weather.state != wx.COLD:
            frames(app, 3)
        assert app.game.weather.state == wx.COLD and app.sim_station.lcd()[0] == "!! COLD ZONE !!"
        app.sim_station.set_air(23.0)
        g = app.game
        g.lives.lives, g.lives.shield = 1, 0.0
        g._hit("debris", g.craft.x, g.craft.y)
        frames(app, 3)
        assert app.sm.state == S.GAMEOVER and not app.state.drive_enabled
        t0 = time.time()
        while time.time() - t0 < 4.0 and not app.links["robot"].latch_confirmed:
            frames(app, 3)
        assert app.links["robot"].latch_confirmed and app.sim_robot.latched      # the robot confirmed the latch
        assert not app.links["tower"].armed
        app.state.keys = (1.0, 0.0)
        frames(app, 20)
        assert app.state.cmd[2] == 0 and app.state.cmd[3] == 0                   # the stick does nothing after game over
        t0 = time.time()
        while time.time() - t0 < 25 and app.sm.state != S.RESULTS:
            frames(app, 30)
        assert app.sm.state == S.RESULTS
        app._action("start")
        frames(app, 20)
        assert app.sm.state == S.MENU and app.game.lives.lives == 15
        assert not app.links["robot"].latched and app.links["tower"].armed
    finally:
        app.shutdown()


def test_pause_stops_the_robot_and_emergency_stop_latches():
    app = make_app()
    try:
        wait_connected(app)
        app.menu_choice("PLAY")
        frames(app, 10)
        app.pause_game()
        frames(app, 20)
        assert app.sm.state == S.PAUSE and app.state.cmd[2] == 0 and app.state.cmd[3] == 0
        app.resume()
        assert app.sm.state == S.PLAY
        app.emergency_stop()
        frames(app, 20)
        assert app.sm.state == S.PAUSE and app.links["robot"].latched and not app.links["tower"].armed
        t0 = time.time()
        while time.time() - t0 < 2 and not app.sim_robot.latched:
            frames(app, 3)
        assert app.sim_robot.latched
        app.resume()                                               # resuming releases both
        frames(app, 20)
        assert not app.links["robot"].latched and app.links["tower"].armed
    finally:
        app.shutdown()


def test_hold_start_resyncs_and_menu_works():
    app = make_app()
    try:
        app.menu_choice("PRACTICE")
        frames(app, 5)
        assert app.game.practice
        app.game.t = 12.0
        app.resync()
        assert app.game.t == 0.0 and app.game.lives.lives == 15 and app.sm.state == S.PRACTICE
        app.goto(S.PAUSE)
        assert app.goto(S.HWCHECK) and app.goto(S.PAUSE) and app.resume() is None
        frames(app, 5)
        assert app.sm.state == S.PRACTICE
    finally:
        app.shutdown()


def test_screens_render_without_hardware_and_never_crash():
    from app import App, Args
    pygame.init()
    app = App(Args(no_serial=True), headless=True)                  # nothing simulated, nothing plugged in
    try:
        app.boot_all()
        for name in (S.SETTINGS, S.CALIBRATE, S.HWCHECK):
            app.sm.state = S.MENU
            assert app.goto(name)
            frames(app, 6)
        app.goto(S.MENU)
        app.menu_choice("PLAY")
        frames(app, 60)
        assert app.sm.state == S.PLAY
        assert not any(d.connected for k, d in app.state.devices.items() if k != "pad")   # honest: nothing connected
        assert len(app.errors) == 0
    finally:
        app.shutdown()
