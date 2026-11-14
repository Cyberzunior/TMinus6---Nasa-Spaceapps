"""Every full screen: boot, menu, settings, calibrate, hardware check, pause, game-over animation, results.
Screens receive semantic actions from the app (up, down, left, right, confirm, back, start, char:<c>, yes, no ...)."""
import math
import random
import pygame
import config as C
from core import calibration as cal
from core import weather as wx
from core.clock import mmss, now
from gfx import fonts, palette as K
from gfx.widgets import dot, panel
from gfx.ship import glow_sprite


def dim(surf, alpha=170):
    s = pygame.Surface((C.RENDER_W, C.RENDER_H), pygame.SRCALPHA)
    s.fill((3, 5, 14, alpha))
    surf.blit(s, (0, 0))


def title(surf, text, y=70, size=64, color=K.CYAN):
    fonts.text(surf, text, (C.RENDER_W // 2, y), size, color, bold=True, anchor="center", shadow=True)


def hints(surf, text):
    fonts.text(surf, text, (C.RENDER_W // 2, C.RENDER_H - 48), 20, K.GREY, anchor="center")


class MenuList:
    def __init__(self, items):
        self.items, self.i = items, 0

    def move(self, d):
        self.i = (self.i + d) % len(self.items)

    def draw(self, surf, x, y, step=66, size=38, width=520):
        for k, (label, hint) in enumerate(self.items):
            sel = k == self.i
            r = pygame.Rect(x, y + k * step, width, step - 10)
            if sel:
                s = pygame.Surface(r.size, pygame.SRCALPHA)
                pygame.draw.rect(s, (60, 130, 220, 70), s.get_rect(), border_radius=12)
                pygame.draw.rect(s, (*K.CYAN, 230), s.get_rect(), 2, border_radius=12)
                surf.blit(s, r.topleft)
                pygame.draw.polygon(surf, K.CYAN, [(r.left + 16, r.centery - 10), (r.left + 16, r.centery + 10), (r.left + 30, r.centery)])
            fonts.text(surf, label, (r.left + 48, r.centery), size, K.WHITE if sel else K.GREY, bold=sel, anchor="midleft")
            if sel and hint:
                fonts.text(surf, hint, (r.right + 28, r.centery), 20, K.GREY, anchor="midleft")


class BootScreen:
    def __init__(self, steps):
        self.steps, self.done, self.total = steps, 0, len(steps)
        self.t = 0.0
        self.finished = False

    def update(self, app, dt):
        self.t += dt
        if self.done < self.total:
            name, fn = self.steps[self.done]
            self.label = name
            try:
                fn()
            except Exception as e:                                  # a failed step must not stop the game starting
                app.log("boot step %r failed: %r" % (name, e))
            self.done += 1
        elif self.t > 1.2:
            self.finished = True

    def draw(self, surf, app):
        cx, cy = C.RENDER_W // 2, C.RENDER_H // 2
        for i in range(3):                                           # the orbit ring draws itself around the logo
            r = 170 + i * 42
            a0 = self.t * (0.8 + i * 0.3)
            pygame.draw.arc(surf, K.mix(K.BG, K.CYAN, 0.8 - i * 0.22), (cx - r, cy - r - 40, 2 * r, 2 * r), a0, a0 + 3.2 + i, 3)
        n = len("T-Minus_6")
        shown = min(n, int(self.t * 9))
        fonts.text(surf, "T-Minus_6"[:shown], (cx, cy - 40), 120, K.WHITE, bold=True, anchor="center", shadow=True)
        fonts.text(surf, "D NOVAS   |   NASA SPACE APPS 2026   |   TORONTO", (cx, cy + 70), 24, K.GREY, anchor="center")
        bar = pygame.Rect(cx - 300, cy + 140, 600, 10)
        pygame.draw.rect(surf, (25, 38, 70), bar, border_radius=5)
        pygame.draw.rect(surf, K.CYAN, (bar.left, bar.top, int(bar.w * self.done / max(1, self.total)), bar.h), border_radius=5)
        fonts.text(surf, getattr(self, "label", "starting") + "...", (cx, cy + 170), 20, K.GREY, anchor="center")


class MenuScreen:
    def __init__(self):
        self.list = MenuList([("PLAY", "15 lives, asteroids, the real game"), ("PRACTICE", "no lives lost, X fires an asteroid"),
                              ("CALIBRATE", "speed, turn, latency, tower aim"), ("SETTINGS", "volume, post-fx, thresholds, demo mode"),
                              ("HARDWARE CHECK", "test every device before the demo"), ("QUIT", "")])

    def handle(self, app, a):
        if a == "up":
            self.list.move(-1)
        elif a == "down":
            self.list.move(1)
        elif a in ("confirm", "start"):
            app.audio.play("confirm")
            app.menu_choice(self.list.items[self.list.i][0])

    def update(self, app, dt):
        pass

    def draw(self, surf, app):
        title(surf, "T-Minus_6", 150, 96, K.WHITE)
        fonts.text(surf, "ORBIT. DODGE. SURVIVE.", (C.RENDER_W // 2, 232), 24, K.CYAN, anchor="center")
        panel(surf, pygame.Rect(C.RENDER_W // 2 - 490, 310, 980, 420), 190, scan=False)
        self.list.draw(surf, C.RENDER_W // 2 - 440, 330)
        ready = app.hwcheck.ready(app)
        fonts.text(surf, "READY FOR DEMO" if ready else "hardware not checked yet",
                   (C.RENDER_W // 2, C.RENDER_H - 110), 28 if ready else 20, K.GREEN if ready else K.GREY, bold=ready, anchor="center")
        fonts.text(surf, "BEST  %s" % mmss(C.BEST_TIME), (C.RENDER_W - 40, C.RENDER_H - 110), 22, K.GREY, anchor="topright")
        hints(surf, "up / down: choose    A or Enter: select    F2 / Back: hardware check    F11: fullscreen    M: mute")


class SettingsScreen:
    ITEMS = ("Master volume", "Post-processing", "Demo mode", "After game over", "Hot above (C)", "Cold below (C)", "Spike (C in 10 s)",
             "Weather slows turns", "Privacy: never save frames", "Back")

    def __init__(self):
        self.list = MenuList([(i, "") for i in self.ITEMS])

    def value(self, k):
        return [("%d%%" % round(C.MASTER_VOLUME * 100)), ("OFF", "VIGNETTE", "FULL")[C.POSTFX], "ON" if C.DEMO_MODE else "OFF",
                "straight back to PLAY" if C.RESTART_TO_PLAY else "go to MENU", "%.0f" % C.HOT_C, "%.0f" % C.COLD_C, "%.0f" % C.SPIKE_C,
                "%d%%" % round(C.WEATHER_TURN_PENALTY * 100), "ON" if C.PRIVACY_NO_SAVE_FRAMES else "OFF", ""][k]

    def change(self, app, d):
        i = self.list.i
        if i == 0:
            C.save_local(MASTER_VOLUME=round(max(0.0, min(1.0, C.MASTER_VOLUME + 0.1 * d)), 2))
        elif i == 1:
            C.save_local(POSTFX=(C.POSTFX + d) % 3)
            app.postfx.level = C.POSTFX
        elif i == 2:
            C.save_local(DEMO_MODE=not C.DEMO_MODE)
        elif i == 3:
            C.save_local(RESTART_TO_PLAY=not C.RESTART_TO_PLAY)
        elif i == 4:
            C.save_local(HOT_C=float(max(C.COLD_C + 4, min(60, C.HOT_C + d))))
        elif i == 5:
            C.save_local(COLD_C=float(max(-10, min(C.HOT_C - 4, C.COLD_C + d))))
        elif i == 6:
            C.save_local(SPIKE_C=float(max(1, min(10, C.SPIKE_C + d))))
        elif i == 7:
            C.save_local(WEATHER_TURN_PENALTY=round(max(0.0, min(0.6, C.WEATHER_TURN_PENALTY + 0.1 * d)), 2))
        elif i == 8:
            C.save_local(PRIVACY_NO_SAVE_FRAMES=not C.PRIVACY_NO_SAVE_FRAMES)
        app.audio.play("click")

    def handle(self, app, a):
        if a == "up":
            self.list.move(-1)
        elif a == "down":
            self.list.move(1)
        elif a == "left":
            self.change(app, -1)
        elif a == "right":
            self.change(app, 1)
        elif a in ("confirm", "start") and self.list.i == len(self.ITEMS) - 1:
            app.goto("MENU")
        elif a in ("confirm", "start"):
            self.change(app, 1)
        elif a == "back":
            app.goto("MENU")

    def update(self, app, dt):
        pass

    def draw(self, surf, app):
        title(surf, "SETTINGS", 110)
        x, y = C.RENDER_W // 2 - 460, 220
        for k, item in enumerate(self.ITEMS):
            sel = k == self.list.i
            r = pygame.Rect(x, y + k * 62, 920, 54)
            if sel:
                s = pygame.Surface(r.size, pygame.SRCALPHA)
                pygame.draw.rect(s, (60, 130, 220, 70), s.get_rect(), border_radius=10)
                pygame.draw.rect(s, (*K.CYAN, 230), s.get_rect(), 2, border_radius=10)
                surf.blit(s, r.topleft)
            fonts.text(surf, item, (r.left + 24, r.centery), 28, K.WHITE if sel else K.GREY, anchor="midleft")
            v = self.value(k)
            if v:
                fonts.text(surf, ("<  %s  >" if sel else "%s") % v, (r.right - 24, r.centery), 28, K.CYAN if sel else K.GREY, anchor="midright")
        hints(surf, "up / down: choose    left / right: change    Esc or B: back    changes are saved to config.local.json")


class PauseOverlay:
    def __init__(self):
        self.list = MenuList([("RESUME", ""), ("HARDWARE CHECK", ""), ("QUIT TO MENU", "")])

    def handle(self, app, a):
        if a == "up":
            self.list.move(-1)
        elif a == "down":
            self.list.move(1)
        elif a == "start" or (a == "confirm" and self.list.i == 0) or a == "back":
            app.resume()
        elif a == "confirm":
            app.pause_choice(self.list.items[self.list.i][0])

    def draw(self, surf, app):
        dim(surf, 190)
        title(surf, "PAUSED", 330, 90, K.WHITE)
        fonts.text(surf, "robot stopped", (C.RENDER_W // 2, 395), 22, K.GREY, anchor="center")
        self.list.draw(surf, C.RENDER_W // 2 - 260, 450, 64, 34, 520)
        hints(surf, "Start: resume    hold Start 2 s: re-sync robot to its start mark and reset the game")


class CalibrateScreen:
    STEPS = ("fwd", "turn", "latency", "aim", "done")

    def __init__(self):
        self.reset()

    def reset(self):
        self.i, self.text, self.job, self.msg = 0, "", None, ""
        self.new = {}
        self.rtt = []

    def run_test(self, app, left, right, seconds):
        self.job = (now() + seconds, left, right)
        app.state.test_cmd = (left, right)

    def handle(self, app, a):
        step = self.STEPS[self.i]
        if a == "back":
            self.stop(app)
            app.goto("MENU")
            return
        if self.job:
            return
        if isinstance(a, str) and a.startswith("char:"):
            ch = a[5:]
            if ch == "\b":
                self.text = self.text[:-1]
            elif (ch.isdigit() or ch == ".") and len(self.text) < 7:
                self.text += ch
            return
        if step == "fwd":
            if a in ("confirm", "start") and not self.text:
                if not app.links["robot"].connected:
                    self.msg = "No robot connected. Connect it (or run with --sim) and try again."
                    return
                v = C.V_MAX * 0.5
                secs = 50.0 / max(1.0, v)
                self.msg = "Driving %.1f s at half speed. Measure how far it went." % secs
                self.run_test(app, int(0.5 * C.MAX_PWM), int(0.5 * C.MAX_PWM), secs)
            elif a == "confirm" and self.text:
                try:
                    self.new["V_MAX"] = cal.scale_after_test(C.V_MAX, 50.0, float(self.text))
                except ValueError as e:
                    self.msg = str(e)
                    return
                self.text, self.msg, self.i = "", "", self.i + 1
        elif step == "turn":
            if a in ("confirm", "start") and not self.text:
                if not app.links["robot"].connected:
                    self.msg = "No robot connected."
                    return
                secs = 360.0 / max(1.0, C.W_MAX)
                self.msg = "Turning on the spot for %.1f s. Count the degrees it turned (360 = one full turn)." % secs
                k = int(C.TURN_GAIN * C.MAX_PWM)
                self.run_test(app, k, -k, secs)
            elif a == "confirm" and self.text:
                try:
                    self.new["W_MAX"] = cal.scale_after_test(C.W_MAX, 360.0, float(self.text))
                except ValueError as e:
                    self.msg = str(e)
                    return
                self.text, self.msg, self.i = "", "", self.i + 1
        elif step == "latency":
            if a in ("confirm", "start"):
                if self.job is None and not self.rtt:
                    self.job, self.rtt = (now() + 5.0, None, None), []
                    self.msg = "Measuring for 5 seconds..."
                elif self.rtt:
                    self.new["SYNC_DELAY_MS"] = cal.sync_delay_from(sum(self.rtt) / len(self.rtt) / 2.0)
                    self.msg, self.i = "", self.i + 1
        elif step == "aim":
            if a == "left":
                self.new["AIM_CENTER_DEG"] = max(0.0, self.new.get("AIM_CENTER_DEG", C.AIM_CENTER_DEG) - 1)
                app.links["tower"].aim(int(self.new["AIM_CENTER_DEG"]))
            elif a == "right":
                self.new["AIM_CENTER_DEG"] = min(180.0, self.new.get("AIM_CENTER_DEG", C.AIM_CENTER_DEG) + 1)
                app.links["tower"].aim(int(self.new["AIM_CENTER_DEG"]))
            elif a == "fire":
                app.links["tower"].fire(test=True)
            elif a in ("confirm", "start"):
                self.i += 1
        elif step == "done":
            if a in ("confirm", "start"):
                if cal.save(**self.new):
                    app.toast("Calibration saved", "ok")
                app.goto("MENU")

    def stop(self, app):
        self.job = None
        app.state.test_cmd = None

    def update(self, app, dt):
        if self.job:
            end = self.job[0]
            if self.STEPS[self.i] == "latency":
                r = app.links["robot"].best()
                if r and r.rtt_ms is not None:
                    self.rtt.append(r.rtt_ms)
            if now() >= end:
                self.stop(app)
                self.msg = "Done. Type the number you measured and press Enter." if self.STEPS[self.i] != "latency" else \
                    ("Average round trip %.0f ms. Press Enter to use half of it." % (sum(self.rtt) / len(self.rtt)) if self.rtt else "No replies from the robot.")

    def draw(self, surf, app):
        title(surf, "CALIBRATE", 100)
        step = self.STEPS[self.i]
        y = 190
        steps = {"fwd": ("1 / 4   Forward speed", "Put the robot on the table. Press A / Enter: it drives half speed for the time the game expects "
                         "to cover 50 cm.", "Type the distance it really covered (cm), then Enter."),
                 "turn": ("2 / 4   Turn rate", "Press A / Enter: the robot spins on the spot for the time the game expects to cover 360 degrees.",
                          "Type the degrees it really turned, then Enter."),
                 "latency": ("3 / 4   Link delay", "Press A / Enter to measure the round trip to the robot. Half of it becomes the screen delay "
                             "(SYNC_DELAY_MS) so the craft and the robot move together.", ""),
                 "aim": ("4 / 4   Tower aim", "Left / right moves the pan servo, X or F fires a test ball. Set the angle where the ball "
                         "flies straight at Earth, then press Enter.", ""),
                 "done": ("Done", "These values will be saved to config.local.json:", "")}[step]
        fonts.text(surf, steps[0], (C.RENDER_W // 2, y), 40, K.WHITE, bold=True, anchor="midtop")
        self.wrap(surf, steps[1], C.RENDER_W // 2, y + 70, 1100, 26, K.GREY)
        if steps[2]:
            fonts.text(surf, steps[2], (C.RENDER_W // 2, y + 190), 24, K.CYAN, anchor="midtop")
            box = pygame.Rect(C.RENDER_W // 2 - 160, y + 240, 320, 64)
            pygame.draw.rect(surf, (20, 32, 60), box, border_radius=10)
            pygame.draw.rect(surf, K.CYAN, box, 2, border_radius=10)
            fonts.text(surf, self.text + ("_" if int(now() * 2) % 2 else ""), box.center, 36, K.WHITE, mono=True, anchor="center")
        if step == "aim":
            v = self.new.get("AIM_CENTER_DEG", C.AIM_CENTER_DEG)
            fonts.text(surf, "pan servo  %d deg" % v, (C.RENDER_W // 2, y + 220), 44, K.CYAN, mono=True, anchor="midtop")
        if step == "done":
            for k, (key, val) in enumerate(self.new.items()):
                fonts.text(surf, "%-16s %s" % (key, val), (C.RENDER_W // 2, y + 140 + k * 40), 30, K.GREEN, mono=True, anchor="midtop")
            if not self.new:
                fonts.text(surf, "(nothing changed)", (C.RENDER_W // 2, y + 140), 26, K.GREY, anchor="midtop")
        if self.job:
            left = max(0.0, self.job[0] - now())
            fonts.text(surf, "running... %.1f s   (Esc stops)" % left, (C.RENDER_W // 2, y + 330), 26, K.YELLOW, anchor="midtop")
        if self.msg:
            self.wrap(surf, self.msg, C.RENDER_W // 2, y + 380, 1000, 24, K.YELLOW)
        hints(surf, "Enter / A: next    Esc / B: leave")

    @staticmethod
    def wrap(surf, text, cx, y, width, size, color):
        words, line, yy = text.split(), "", y
        for w in words:
            if fonts.width(line + " " + w, size) > width:
                fonts.text(surf, line, (cx, yy), size, color, anchor="midtop")
                line, yy = w, yy + size + 8
            else:
                line = (line + " " + w).strip()
        fonts.text(surf, line, (cx, yy), size, color, anchor="midtop")


class HwCheckScreen:
    """One page that tests everything before the demo. READY FOR DEMO only when every check passed this session."""
    CHECKS = [
        ("pad", "Gamepad found, stick moved", "auto"),
        ("robot_link", "Robot connected, round trip under 80 ms", "auto"),
        ("robot_scan", "Robot turret sweeps both sides (scan readings)", "auto"),
        ("wheels_l", "Left wheels spin forward (robot lifted)", "manual"),
        ("wheels_r", "Right wheels spin forward", "manual"),
        ("tower_link", "Tower connected", "auto"),
        ("tower_fire", "Tower released one ball and answered K", "auto"),
        ("station_link", "Weather station connected, W readings arriving", "auto"),
        ("leds", "LEDs flash: red hot, blue cold, yellow hit", "manual"),
        ("buzzers", "Buzzers sound: active (hot), passive (cold)", "manual"),
        ("lcd", "Weather LCD shows the hot and cold warnings", "manual"),
        ("camera", "Camera picture is live", "auto"),
    ]
    TESTS = {"1": "Spin LEFT wheels", "2": "Spin RIGHT wheels", "3": "Sweep turret", "4": "Fire tower once",
             "5": "Flash LEDs + buzzers", "6": "Hot warning on LCD", "7": "Cold warning on LCD"}

    def __init__(self):
        self.status = {k: None for k, _, _ in self.CHECKS}          # None pending, True pass, False fail
        self.job = None
        self.ask = None                                            # manual check waiting for Y / N
        self.t_total = 0.0
        self.scan_angles = set()
        self.pad_ok = False
        self.fire_t = -1.0
        self.was_ready = False

    def ready(self, app):
        return all(self.status.values()) or (app.sim_all and self.status_auto_sim())

    def status_auto_sim(self):
        return True

    def handle(self, app, a):
        if a == "back":
            app.goto(app.hw_return)
            return
        if isinstance(a, str) and a.startswith("char:") and a[5:] in self.TESTS:
            self.start_test(app, a[5:])
        elif a in ("yes", "confirm") and self.ask:
            self.status[self.ask] = True
            self.ask = None
        elif a == "no" and self.ask:
            self.status[self.ask] = False
            self.ask = None

    def start_test(self, app, key):
        r, t, s = app.links["robot"], app.links["tower"], app.links["station"]
        if self.job:
            return
        if key in ("1", "2"):
            if not r.connected:
                app.toast("Robot not connected", "bad")
                return
            v = 170
            app.state.test_cmd = (v, 0) if key == "1" else (0, v)
            self.job = ("wheels_l" if key == "1" else "wheels_r", now() + 1.0)
        elif key == "3":
            self.scan_angles.clear()
            self.job = ("sweep", now() + 6.5)
        elif key == "4":
            if not t.connected:
                app.toast("Tower not connected", "bad")
                return
            t.allow(True)
            if t.fire(test=True):
                self.fire_t = now()
                app.toast("Fired: watch for one ball", "warn")
            else:
                app.toast("Tower disarmed or fired within 2 s", "warn")
        elif key == "5":
            if not s.connected:
                app.toast("Station not connected", "bad")
                return
            self.job = ("leds", now() + 5.0)
        elif key in ("6", "7"):
            if not s.connected:
                app.toast("Station not connected", "bad")
                return
            app.game.force_zone(wx.HOT if key == "6" else wx.COLD)
            self.job = ("lcd", now() + 3.0)

    def update(self, app, dt):
        self.t_total += dt
        snap = app.state.snapshot()
        st = self.status
        ax = max([abs(v) for v in app.state.raw_axes] or [0.0])
        if app.state.pad is not None and (ax > 0.5 or abs(app.state.stick[0]) > 0.5 or abs(app.state.stick[1]) > 0.5 or app.pad_button_seen):
            st["pad"] = True
        elif app.sim_all:
            st["pad"] = True
        rb = snap["robot"]
        if rb[0] and (rb[4] is None or rb[4] < C.RTT_WARN_MS):
            if rb[4] is not None:
                st["robot_link"] = True
        for ang in app.game.radar:
            self.scan_angles.add(ang)
        if min(self.scan_angles or [0]) <= -30 and max(self.scan_angles or [0]) >= 30:
            st["robot_scan"] = True
        if snap["tower"][0]:
            st["tower_link"] = True
        if self.fire_t > 0 and app.links["tower"].last_k > self.fire_t:
            st["tower_fire"] = True
        if snap["station"][0] and app.game.weather.temp is not None:
            st["station_link"] = True
        if app.camera is not None and app.camera.live():
            st["camera"] = True
        if app.sim_all:                                              # --sim: everything is a software device, auto-green
            for k in st:
                st[k] = True
        if self.job:
            name, end = self.job
            t = now()
            if name == "leds":
                phase = int((5.0 - (end - t)) / 1.5)
                app.game.force_zone((wx.HOT, wx.COLD, None, None)[min(3, max(0, phase))])
                if phase == 2 and int(t * 4) % 4 == 0:
                    app.links["station"].set_lives(app.game.lives.lives - 1)
                if phase >= 2:
                    app.links["station"].set_lives(app.game.lives.lives)
            if t >= end:
                app.state.test_cmd = None
                if name in ("wheels_l", "wheels_r"):
                    self.ask = name
                elif name == "leds":
                    app.game.force_zone(None)
                    self.ask = "leds"
                elif name == "lcd":
                    app.game.force_zone(None)
                    self.ask = "lcd"
                self.job = None
        elif self.ask is None and self.status["leds"] and not self.status["buzzers"] and False:
            pass

    def ask_text(self):
        return {"wheels_l": "Did the LEFT wheels spin forward?", "wheels_r": "Did the RIGHT wheels spin forward?",
                "leds": "Did the LEDs flash (red, blue, yellow)? Press Y for yes, N for no, then run test 5 again for the buzzers.",
                "lcd": "Did the LCD show the warning text?"}.get(self.ask, "")

    def draw(self, surf, app):
        title(surf, "HARDWARE CHECK", 90)
        snap = app.state.snapshot()
        y = 150
        for key, label in (("pad", "Gamepad"), ("robot", "Robot (UNO Q #1)"), ("tower", "Tower (UNO Q #2)"),
                           ("station", "Weather station (UNO R3)"), ("camera", "Camera")):
            conn, col, where, fw, rtt, loss, note, sim = snap[key]
            r = panel(surf, pygame.Rect(120, y, 1120, 66), 170, scan=False)
            dot(surf, (r.left + 30, r.centery), K.DOT[col], 9)
            fonts.text(surf, label + ("  (simulated)" if sim else ""), (r.left + 60, r.centery), 25, K.WHITE, anchor="midleft")
            info = (where or "-")
            if fw is not None:
                info += "   fw v%s" % fw + ("  MISMATCH" if fw != C.FW_VERSION else "")
            if rtt is not None:
                info += "   %d ms" % rtt
            if not conn:
                info = note or "missing"
            fonts.text(surf, info[:58], (r.right - 20, r.centery), 20, K.GREY if conn else K.RED, mono=True, anchor="midright")
            y += 76
        r = panel(surf, pygame.Rect(1280, 150, 520, 366), 170, scan=False)
        fonts.text(surf, "TESTS (press the number)", (r.left + 20, r.top + 14), 18, K.GREY)
        for i, (k, label) in enumerate(self.TESTS.items()):
            fonts.text(surf, k, (r.left + 24, r.top + 52 + i * 42), 24, K.CYAN, mono=True, bold=True)
            fonts.text(surf, label, (r.left + 62, r.top + 52 + i * 42), 24, K.WHITE)
        y = 548
        fonts.text(surf, "CHECKLIST", (120, y - 6), 18, K.GREY)
        for i, (key, label, kind) in enumerate(self.CHECKS):
            col_i, row_i = i // 6, i % 6
            x, yy = 120 + col_i * 840, y + 24 + row_i * 44
            v = self.status[key]
            c = K.GREEN if v else K.RED if v is False else K.DIM
            pygame.draw.circle(surf, c, (x + 14, yy + 14), 11, 0 if v is not None else 2)
            fonts.text(surf, ("OK" if v else "X") if v is not None else "", (x + 14, yy + 14), 14, K.BG, bold=True, anchor="center")
            fonts.text(surf, label, (x + 38, yy + 14), 22, K.WHITE if v is not None else K.GREY, anchor="midleft")
            fonts.text(surf, "auto" if kind == "auto" else "you confirm", (x + 780, yy + 14), 15, K.DIM, anchor="midright")
        if self.ask:
            r = panel(surf, pygame.Rect(C.RENDER_W // 2 - 520, 380, 1040, 150), 245, edge=K.YELLOW, scan=False)
            fonts.text(surf, self.ask_text(), (r.centerx, r.top + 50), 26, K.YELLOW, anchor="center")
            fonts.text(surf, "Y = yes     N = no", (r.centerx, r.top + 104), 30, K.WHITE, bold=True, anchor="center")
        elif self.job:
            fonts.text(surf, "running: %s ..." % self.job[0], (C.RENDER_W // 2, 520), 24, K.YELLOW, anchor="center")
        ready = self.ready(app)
        badge = pygame.Rect(C.RENDER_W // 2 - 260, C.RENDER_H - 190, 520, 76)
        col = K.GREEN if ready else K.DIM
        pygame.draw.rect(surf, K.mix(K.PANEL, col, 0.28 if ready else 0.1), badge, border_radius=38)
        pygame.draw.rect(surf, col, badge, 3, border_radius=38)
        fonts.text(surf, "READY FOR DEMO" if ready else "%d of %d checks passed" % (sum(1 for v in self.status.values() if v), len(self.status)),
                   badge.center, 34 if ready else 26, col, bold=True, anchor="center")
        hints(surf, "1-7: run a test    Y / N: confirm what you saw    Esc / B: back")


class ResultsScreen:
    def handle(self, app, a):
        if a in ("start", "confirm"):
            app.after_results()

    def update(self, app, dt):
        pass

    def draw(self, surf, app):
        res = app.last_results
        pygame.draw.rect(surf, (0, 0, 0), (0, 0, C.RENDER_W, C.RENDER_H))
        title(surf, "ORBIT FAILED", 120, 96, K.RED)
        fonts.text(surf, "Signal lost at T+ %s" % mmss(res["time"]), (C.RENDER_W // 2, 200), 28, K.GREY, anchor="center")
        cols = (C.RENDER_W // 2 - 520, C.RENDER_W // 2 - 270, C.RENDER_W // 2 - 70, C.RENDER_W // 2 + 150, C.RENDER_W // 2 + 380)
        for c, head in zip(cols, ("RUN", "TIME", "DEBRIS HITS", "ASTEROID HITS", "DODGED")):
            fonts.text(surf, head, (c, 280), 20, K.GREY)
        y = 320
        for mode in ("MANUAL", "AUTO-PILOT"):
            r = app.history.get(mode)
            sel = mode == app.last_mode
            vals = (mode, mmss(r["time"]), str(r["debris"]), str(r["asteroid"]), str(r["dodged"])) if r else (mode, "-", "-", "-", "-")
            for c, v in zip(cols, vals):
                fonts.text(surf, v, (c, y), 30, (K.YELLOW if sel else K.WHITE) if r else K.DIM, mono=True)
            y += 52
        fonts.text(surf, "best streak without a hit %s     best time %s" % (mmss(res["best_streak"]), mmss(C.BEST_TIME)),
                   (C.RENDER_W // 2, y + 30), 24, K.CYAN, anchor="center")
        fonts.text(surf, "Fly one run by hand and one with auto-pilot to compare.", (C.RENDER_W // 2, y + 80), 20, K.GREY, anchor="center")
        if int(now() * 2) % 2:
            fonts.text(surf, "PRESS START", (C.RENDER_W // 2, y + 170), 48, K.YELLOW, bold=True, anchor="center")
        fonts.text(surf, "Put the robot back on its start mark first.", (C.RENDER_W // 2, y + 225), 22, K.GREY, anchor="center")


class GameOverFX:
    """Failed orbit, about 8 seconds: engine dies, tumble, the ring breaks, the craft falls to Earth and burns up."""
    LENGTH = 10.5

    def __init__(self, world_view, game, audio):
        self.wv, self.t = world_view, 0.0
        c = game.craft
        self.x, self.y, self.h = c.x, c.y, c.theta
        self.spin, self.fragmented, self.engine_fail_played = 40.0, False, False
        self.audio = audio
        self.spark_t = 0.0

    def update(self, dt, game):
        self.t += dt
        t, wv = self.t, self.wv
        self.spin += 220 * dt
        self.h += self.spin * dt
        r = math.hypot(self.x, self.y) or 1.0
        wv.ring_break = max(0.0, min(1.0, (t - 1.2) / 3.5))
        if not self.engine_fail_played and t > 0.05:
            self.engine_fail_played = True
            self.audio.play("engine_fail")
        if t < 3.2:                                                  # drift off the ring
            self.x += self.x / r * 3.0 * dt
            self.y += self.y / r * 3.0 * dt
        elif not self.fragmented:                                    # gravity takes over
            pull = 5 + 18 * (t - 3.2) ** 1.4
            self.x -= self.x / r * pull * dt
            self.y -= self.y / r * pull * dt
            sx, sy = wv.px(self.x, self.y)
            self.spark_t += dt
            if self.spark_t > 0.02:
                self.spark_t = 0
                wv.parts.emit(sx, sy, 3, [K.ORANGE, K.YELLOW, K.WHITE], 90, (0.3, 0.8), (2, 4), drag=1.2)
            if r < C.EARTH_R + 2.5:
                self.fragmented = True
                wv.parts.emit(sx, sy, 140, [K.ORANGE, K.YELLOW, K.WHITE, K.RED], 360, (0.6, 1.6), (2, 6), drag=1.8)
                wv.parts.emit(sx, sy, 18, [(200, 200, 215)], 200, (0.8, 1.8), (4, 9), drag=1.0, kind="frag")
                wv.parts.ring(sx, sy, 160, K.ORANGE, 0.9)
                self.audio.play("burn")
        return t > self.LENGTH

    def scorch(self):
        return max(0.0, min(1.0, (self.t - 3.2) / 2.0))

    def draw(self, surf, game):
        wv, t = self.wv, self.t
        if not self.fragmented:
            x, y = wv.px(self.x, self.y)
            fl = random.random() * max(0.0, 1.0 - t / 1.2) if t < 1.2 and random.random() < 0.5 else 0.0
            wv.ship.draw(surf, x, y, self.h, 0.0, C.CRAFT_R * wv.S, scorch=self.scorch(), flame_override=fl)
        if t < 3.2 and int(t * 5) % 2 == 0:
            fonts.text(surf, "MAIN ENGINE FAILURE", (C.RENDER_W // 2, 200), 64, K.RED, bold=True, anchor="center", shadow=True)
            pygame.draw.rect(surf, K.RED, (6, 6, C.RENDER_W - 12, C.RENDER_H - 12), 5)
        if t > 6.5:
            s = pygame.Surface((C.RENDER_W, C.RENDER_H), pygame.SRCALPHA)
            s.fill((0, 0, 0, int(min(1.0, (t - 6.5) / 1.5) * 240)))
            surf.blit(s, (0, 0))
        if t > 7.5:
            fonts.text(surf, "ORBIT FAILED", (C.RENDER_W // 2, C.RENDER_H // 2 - 40), 100, K.RED, bold=True, anchor="center")
            fonts.text(surf, "Signal lost at T+ %s" % mmss(game.over_t), (C.RENDER_W // 2, C.RENDER_H // 2 + 40), 30, K.GREY, anchor="center")
