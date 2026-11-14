"""The heads-up display. Every panel floats over the game (the game fills the whole screen)."""
import collections
import math
import pygame
import config as C
from core import weather as wx
from core.clock import mmss
from gfx import fonts, palette as K
from gfx.widgets import Hearts, Toasts, Tween, banner, dot, panel, sparkline

LABELS = (("pad", "PAD"), ("robot", "ROBOT"), ("tower", "TOWER"), ("station", "STATION"), ("camera", "CAMERA"))


class Hud:
    def __init__(self):
        self.hearts = Hearts(C.LIVES, 28)
        self.toasts = Toasts()
        self.t = 0.0
        self.temp = Tween(23.0, 6.0)
        self.speed = Tween(0.0, 10.0)
        self.hit_flash = 0.0
        self.cam_surface = None
        self.cam_stamp = -1.0
        self.radar_bump = {"L": -9.0, "R": -9.0}
        self.shown_wx = wx.NORMAL
        self.wx_t = 0.0

    def update(self, dt, game):
        self.t += dt
        self.hearts.set(game.lives.lives)
        self.hearts.update(dt)
        self.toasts.update(dt)
        self.hit_flash = max(0.0, self.hit_flash - dt)
        if game.weather.temp is not None:
            self.temp.set(game.weather.temp)
        self.temp.update(dt)
        self.speed.set(abs(game.speed_cms))
        self.speed.update(dt)
        if game.weather.state != self.shown_wx:
            self.shown_wx, self.wx_t = game.weather.state, self.t

    def reset(self, game):
        self.hearts.shown = game.lives.lives
        self.hearts.anim.clear()
        self.toasts.items.clear()

    # ---- pieces
    def status_strip(self, surf, state, cx=None, y=16, flicker=None):
        snap = state.snapshot()
        cx = C.RENDER_W // 2 if cx is None else cx
        w = 690
        r = panel(surf, pygame.Rect(cx - w // 2, y, w, 46), 175, scan=False, radius=23)
        x = r.left + 28
        for key, label in LABELS:
            conn, col, where, fw, rtt, loss, note, sim = snap[key]
            dot(surf, (x, r.centery), K.DOT[col], 7)
            fonts.text(surf, label + ("*" if sim else ""), (x + 14, r.centery), 17, K.WHITE if conn else K.GREY, anchor="midleft")
            x += fonts.width(label, 17) + 44
        robot = snap["robot"]
        if robot[4] is not None:
            rtt = robot[4]
            col = K.GREEN if rtt < 40 else K.YELLOW if rtt < 80 else K.RED
            fonts.text(surf, "%d ms" % rtt, (r.right - 18, r.centery), 19, col, mono=True, anchor="midright")

    def lives_panel(self, surf, game):
        r = panel(surf, pygame.Rect(24, 16, 15 * 32 + 40, 128))
        self.hearts.draw(surf, (r.left + 20, r.top + 14), game.lives.lives, self.t)
        fonts.text(surf, "T+ %s" % mmss(game.t), (r.left + 22, r.top + 56), 24, K.CYAN, mono=True)
        fonts.text(surf, "ON ORBIT %s" % mmss(game.streak), (r.left + 150, r.top + 56), 24, K.WHITE, mono=True)
        fonts.text(surf, "DODGED %d" % game.dodged, (r.right - 20, r.top + 56), 24, K.GREEN, mono=True, anchor="topright")
        if game.practice:
            fonts.text(surf, "PRACTICE: no lives lost, X fires an asteroid", (r.left + 22, r.bottom - 32), 18, K.YELLOW)
        else:
            fonts.text(surf, "LIVES %d / %d" % (game.lives.lives, C.LIVES), (r.left + 22, r.bottom - 32), 18, K.GREY)
        fonts.text(surf, "BEST %s" % mmss(max(C.BEST_TIME, game.best_streak)), (r.right - 20, r.bottom - 32), 18, K.GREY, mono=True, anchor="topright")
        return r

    def weather_panel(self, surf, game):
        w = game.weather
        r = panel(surf, pygame.Rect(C.RENDER_W - 24 - 392, 16, 392, 200))
        col = (K.GREEN, K.ICE, K.HEAT)[w.state]
        fonts.text(surf, "WEATHER", (r.left + 20, r.top + 12), 17, K.GREY)
        badge = pygame.Rect(r.right - 150, r.top + 10, 130, 30)
        pygame.draw.rect(surf, K.mix(K.PANEL, col, 0.35), badge, border_radius=15)
        pygame.draw.rect(surf, col, badge, 2, border_radius=15)
        fonts.text(surf, w.name(), badge.center, 19, col, bold=True, anchor="center")
        if w.temp is None:
            fonts.text(surf, "-- C", (r.left + 20, r.top + 44), 62, K.DIM, mono=True)
            fonts.text(surf, "no station", (r.left + 190, r.top + 78), 20, K.GREY)
        else:
            fonts.text(surf, "%.1f" % self.temp.v, (r.left + 20, r.top + 44), 62, K.WHITE, mono=True)
            fonts.text(surf, "C", (r.left + 175, r.top + 62), 30, K.GREY)
            arrow = {"rising": "^ rising", "falling": "v falling", "steady": "- steady", "spike": "! SPIKE"}[w.trend]
            fonts.text(surf, arrow, (r.right - 20, r.top + 56), 20, K.YELLOW if w.trend == "spike" else K.CYAN, anchor="topright")
            fonts.text(surf, "humidity %d%%" % (w.hum or 0), (r.right - 20, r.top + 84), 18, K.GREY, anchor="topright")
        vals = [v for (_, v) in w.history]
        sparkline(surf, (r.left + 20, r.top + 118, r.w - 40, 46), vals, col, 10, 40)
        fonts.text(surf, "last 60 s", (r.left + 22, r.top + 166), 15, K.DIM)
        if w.robot_temp is not None:
            fonts.text(surf, "Robot air %.1f C" % w.robot_temp, (r.right - 20, r.top + 166), 17, K.GREY, anchor="topright")
        else:
            fonts.text(surf, "zone: %s" % wx.NAMES[w.zone].lower(), (r.right - 20, r.top + 166), 17, K.DIM, anchor="topright")
        return r

    def banner(self, surf, game, y):
        w = game.weather
        if w.state == wx.HOT:
            banner(surf, C.RENDER_W // 2, y, "WARNING: MOVE AWAY FROM THE HOT ZONE AREA",
                   "T-Minus_6 is in a hot zone. Hull temperature rising.", K.HEAT, self.t)
            return y + 108
        if w.state == wx.COLD:
            banner(surf, C.RENDER_W // 2, y, "WARNING: MOVE AWAY FROM THE COLD ZONE AREA",
                   "T-Minus_6 is in a cold zone. Hull temperature falling.", K.ICE, self.t)
            return y + 108
        if w.spike_active(game.wall):
            banner(surf, C.RENDER_W // 2, y, "TEMPERATURE SPIKE DETECTED", "The air changed by %.0f C or more in %d s."
                   % (C.SPIKE_C, C.SPIKE_WINDOW_S), K.YELLOW, self.t)
            return y + 108
        return y

    def radar(self, surf, game):
        R = 190
        r = pygame.Rect(24, C.RENDER_H - 24 - 248, 2 * R * 0.72 + 40, 248)
        panel(surf, r)
        cx, cy = r.centerx, r.bottom - 26
        fonts.text(surf, "ROBOT RADAR", (r.left + 18, r.top + 10), 16, K.GREY)
        fonts.text(surf, "%s" % ("FRONT STOP" if game.robot.front_stop else ""), (r.right - 18, r.top + 10), 16, K.RED, bold=True, anchor="topright")
        fan = [(cx, cy)] + [(cx + R * math.sin(math.radians(a)), cy - R * math.cos(math.radians(a))) for a in range(-45, 46, 5)]
        s = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.polygon(s, (30, 70, 110, 60), [(x - r.left, y - r.top) for x, y in fan])
        surf.blit(s, r.topleft)
        for cm, lab in ((25, "25"), (50, "50"), (100, "100")):
            rr = int(R * cm / 100.0)
            pygame.draw.arc(surf, (50, 90, 130), (cx - rr, cy - rr, 2 * rr, 2 * rr), math.radians(45), math.radians(135), 1)
            fonts.text(surf, lab, (cx + 4, cy - rr - 14), 13, K.DIM)
        for a in (-45, 45):
            pygame.draw.line(surf, (50, 90, 130), (cx, cy), (cx + R * math.sin(math.radians(a)), cy - R * math.cos(math.radians(a))), 1)
        now = game.wall
        for ang, (cm, tt) in list(game.radar.items()):
            age = now - tt
            if age > 2.0:
                continue
            f = 1.0 - age / 2.0
            d = min(cm, 100.0) / 100.0 * R
            x, y = cx + d * math.sin(math.radians(ang)), cy - d * math.cos(math.radians(ang))
            col = K.RED if cm < 8 else K.ORANGE if cm < 25 else K.GREEN if cm < 100 else K.DIM
            pygame.draw.line(surf, K.mix(K.PANEL, col, 0.35 * f), (cx, cy), (x, y), 1)
            if cm < 100:
                pygame.draw.circle(surf, K.mix(K.PANEL, col, f), (int(x), int(y)), 5)
        pygame.draw.circle(surf, K.CYAN, (cx, cy), 7)
        for side, ang in (("L", -35), ("R", 35)):                                   # bumpers
            if now - game.bump_t.get(side, -9) < 1.0:
                pygame.draw.circle(surf, K.RED, (cx + int(36 * math.sin(math.radians(ang))), cy - int(36 * math.cos(math.radians(ang)))), 10)

    def autopilot_panel(self, surf, game, ap_on, delay_ms):
        r = panel(surf, pygame.Rect(C.RENDER_W // 2 - 280, C.RENDER_H - 24 - 124, 560, 124))
        col = K.GREEN if ap_on else K.GREY
        dot(surf, (r.left + 28, r.top + 26), col, 8)
        fonts.text(surf, "AUTO-PILOT  " + ("ON" if ap_on else "OFF"), (r.left + 48, r.top + 12), 24, col, bold=True)
        status = game.autopilot.status() if ap_on else "MANUAL"
        zone = game.autopilot.zone if ap_on else "clear"
        zc = {"clear": K.GREEN, "warning": K.YELLOW, "danger": K.RED}[zone]
        fonts.text(surf, status, (r.right - 20, r.top + 14), 22, zc, anchor="topright")
        d, kind = game.field.nearest(game.craft.x, game.craft.y)
        near = "%d cm %s" % (max(0, d), kind) if d < 99 else "clear"
        for i, (lab, val, c) in enumerate((("SPEED", "%4.1f cm/s" % self.speed.v, K.WHITE),
                                           ("NEAREST", near, K.RED if d < C.AP_DANGER_CM else K.YELLOW if d < C.AP_WARN_CM else K.GREEN),
                                           ("LINK DELAY", "%d ms" % delay_ms if delay_ms is not None else "no robot", K.CYAN))):
            x = r.left + 22 + i * 180
            fonts.text(surf, lab, (x, r.top + 56), 15, K.GREY)
            fonts.text(surf, val, (x, r.top + 76), 22, c, mono=True)
        if game.tower_note:
            fonts.text(surf, game.tower_note, (r.centerx, r.top - 14), 22, K.RED, bold=True, anchor="midbottom")

    def camera(self, surf, cam, full, rect=None):
        if full:
            rect = pygame.Rect(0, 0, C.RENDER_W, C.RENDER_H)
        else:
            rect = pygame.Rect(C.RENDER_W - 24 - 400, C.RENDER_H - 24 - 322, 400, 322)
            panel(surf, rect, 200, scan=False)
            rect = pygame.Rect(rect.left + 8, rect.top + 8, rect.w - 16, rect.h - 54)
        frame = cam.frame if cam else None
        live = bool(cam and cam.live())
        if live and frame is not None:
            if cam.stamp != self.cam_stamp:
                self.cam_stamp = cam.stamp
                self.cam_surface = pygame.image.frombuffer(frame.tobytes(), (frame.shape[1], frame.shape[0]), "RGB")
            surf.blit(pygame.transform.scale(self.cam_surface, rect.size) if full else pygame.transform.smoothscale(self.cam_surface, rect.size), rect)
        else:
            pygame.draw.rect(surf, (8, 10, 18), rect)
            fonts.text(surf, "NO SIGNAL", rect.center, 40 if full else 26, K.GREY, bold=True, anchor="center")
            if cam is not None and cam.error:
                fonts.text(surf, cam.error[:60], (rect.centerx, rect.centery + (36 if full else 24)), 18 if full else 14, K.DIM, anchor="center")
            if int(self.t * 3) % 2 == 0:
                for i in range(0, rect.h, 14):
                    pygame.draw.line(surf, (18, 22, 34), (rect.left, rect.top + i), (rect.right, rect.top + i))
        badge = pygame.Rect(rect.left + 14, rect.top + 12, 150, 30) if full else pygame.Rect(rect.left + 6, rect.bottom + 8, 190, 30)
        col = K.GREEN if live else K.RED
        pygame.draw.rect(surf, K.mix(K.PANEL, col, 0.3), badge, border_radius=15)
        pygame.draw.rect(surf, col, badge, 2, border_radius=15)
        age = cam.age_ms() if cam else None
        fonts.text(surf, ("LIVE %d ms" % age) if live and age is not None else "NO SIGNAL", badge.center, 17, col, bold=True, anchor="center")
        if not full:
            fonts.text(surf, "ROBOT CAM  [B]", (rect.right - 6, rect.bottom + 14), 15, K.GREY, anchor="topright")

    def debug(self, surf, info):
        lines = ["FPS %5.1f   frame %5.1f ms   worst %5.1f ms   postfx %d" % (info["fps"], info["ms"], info["worst"], info["postfx"])]
        lines += ["%-8s %s" % (k, v) for k, v in info["threads"].items()]
        lines += info["packets"]
        r = pygame.Rect(C.RENDER_W // 2 - 330, 140, 660, 24 + 21 * len(lines))
        panel(surf, r, 215, scan=False)
        for i, l in enumerate(lines):
            fonts.text(surf, l, (r.left + 16, r.top + 12 + i * 21), 16, K.GREEN, mono=True)

    def draw(self, surf, game, ui):
        """ui: dict(state, ap_on, camera, cam_full, delay_ms, debug, status_cx)"""
        self.status_strip(surf, ui["state"])
        y = self.banner(surf, game, 152)
        self.toasts.draw(surf, C.RENDER_W // 2, y + 6 if y != 152 else 74)
        if ui.get("cam_full"):
            self.camera(surf, ui["camera"], True)
        self.lives_panel(surf, game)
        self.weather_panel(surf, game)
        self.radar(surf, game)
        self.autopilot_panel(surf, game, ui["ap_on"], ui.get("delay_ms"))
        if not ui.get("cam_full"):
            self.camera(surf, ui["camera"], False)
        if ui.get("debug"):
            self.debug(surf, ui["debug"])
