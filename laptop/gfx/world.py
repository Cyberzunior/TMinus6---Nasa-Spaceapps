"""Draws the board: ring with hot and cold arcs, Earth, debris, asteroids, robot ghost, planned path, craft."""
import math
import random
import pygame
import config as C
from core import weather as wx
from core.model import in_arc
from gfx import fonts, palette as K
from gfx.earth import Earth
from gfx.particles import Particles
from gfx.ship import Ship, glow_sprite
from gfx.starfield import Starfield


def _rock_sprite(radius_px, seed, base=(120, 110, 100)):
    """A rocky body with craters, lit from the left. Cached per size."""
    rnd = random.Random(seed)
    n = 9
    d = radius_px * 2 + 8
    s = pygame.Surface((d, d), pygame.SRCALPHA)
    cx = cy = d // 2
    pts = []
    for i in range(n):
        a = 6.283 * i / n
        r = radius_px * rnd.uniform(0.78, 1.0)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pygame.draw.polygon(s, base, pts)
    lit = [(x + (cx - x) * 0.35 - radius_px * 0.12, y + (cy - y) * 0.35 - radius_px * 0.1) for x, y in pts]
    pygame.draw.polygon(s, K.mix(base, (255, 245, 230), 0.35), lit)
    for _ in range(4):
        a, r = rnd.uniform(0, 6.283), rnd.uniform(0, radius_px * 0.55)
        c = (int(cx + r * math.cos(a)), int(cy + r * math.sin(a)))
        cr = max(2, int(radius_px * rnd.uniform(0.12, 0.25)))
        pygame.draw.circle(s, K.mix(base, (20, 18, 16), 0.55), c, cr)
        pygame.draw.circle(s, K.mix(base, (255, 255, 255), 0.25), (c[0] - 1, c[1] - 1), cr, 1)
    pygame.draw.polygon(s, K.mix(base, (0, 0, 0), 0.4), pts, 2)
    return s


class WorldView:
    def __init__(self):
        self.W, self.H = C.RENDER_W, C.RENDER_H
        self.S0 = min(self.W / C.BOARD_W, self.H / C.BOARD_H)
        self.S = self.S0
        self.cx, self.cy = self.W / 2, self.H / 2
        self.t = 0.0
        self.stars = Starfield()
        self.earth = Earth(C.EARTH_R * self.S0)
        self.ship = Ship(self.S0)
        self.parts = Particles()
        self.sprites = {}
        self.asteroid_trails = {}
        self.tower_glow = glow_sprite(30, K.ORANGE, 1.5)
        self.ring_cache = None
        self.ring_break = 0.0
        self.last_pos = None

    # ---- coordinates
    def px(self, x, y):
        return self.cx + x * self.S, self.cy + y * self.S

    def update(self, dt, game, speed01):
        self.t += dt
        self.S = self.S0 * (1.0 + 0.006 * math.sin(self.t * 0.25))       # slow breathing zoom for depth
        self.stars.update(dt)
        self.earth.update(dt)
        c = game.craft
        x, y = self.px(c.x, c.y)
        if not game.over:
            self.ship.update(dt, x, y, speed01)
        self.parts.update(dt)
        if not game.over:
            if speed01 > 0.05:                                            # exhaust
                a = math.radians(c.theta + 180)
                ex, ey = x + math.cos(a) * C.CRAFT_R * self.S * 0.9, y + math.sin(a) * C.CRAFT_R * self.S * 0.9
                self.parts.emit(ex, ey, 2, [K.ORANGE, K.YELLOW, (255, 120, 60)], 60 + 120 * speed01, (0.2, 0.5),
                                (1.5, 3.2), 0.5, a, drag=2.0)
            st = game.weather.state
            if st == wx.HOT and random.random() < 0.7:                    # heat shimmer rising off the hot arc
                ang = math.radians(random.uniform(*self._arc(C.HOT_ZONE)))
                px, py = self.px(C.ORBIT_R * math.cos(ang), C.ORBIT_R * math.sin(ang))
                self.parts.emit(px, py, 1, [(255, 110, 50), (255, 170, 80)], 30, (0.5, 1.1), (2, 4), 0.4, -1.57, drag=0.5)
            elif st == wx.COLD and random.random() < 0.7:
                ang = math.radians(random.uniform(*self._arc(C.COLD_ZONE)))
                px, py = self.px(C.ORBIT_R * math.cos(ang), C.ORBIT_R * math.sin(ang))
                self.parts.emit(px, py, 1, [K.ICE, K.WHITE], 25, (0.8, 1.6), (2, 4), 6.283, 0.0, kind="ice", drag=0.8)

    def _arc(self, arc):
        a0, a1 = arc
        return a0, a0 + (a1 - a0) % 360.0

    def fx(self, game, e, shake, audio):
        """React to one game effect tuple (kind, x, y, extra)."""
        kind, x, y, extra = e
        sx, sy = self.px(x, y)
        if kind == "hit":
            self.parts.emit(sx, sy, 60, [K.ORANGE, K.YELLOW, K.RED, K.WHITE], 280, (0.4, 1.1), (2, 5), drag=1.6)
            self.parts.emit(sx, sy, 14, [(190, 190, 205)], 160, (0.5, 1.2), (3, 7), drag=1.0, kind="frag")
            self.parts.ring(sx, sy, 190, K.ORANGE)
            shake.add(18)
        elif kind == "miss":
            self.parts.emit(sx, sy, 10, [K.ORANGE, K.YELLOW], 90, (0.2, 0.5))
        elif kind == "burn":
            self.parts.emit(sx, sy, 40, [K.ORANGE, K.YELLOW, K.WHITE], 140, (0.4, 1.0), (2, 4), drag=1.5)
            self.parts.ring(sx, sy, 80, K.ORANGE, 0.5)
            shake.add(5)
        elif kind == "asteroid_fire":
            self.parts.emit(sx, sy, 16, [K.ORANGE, K.YELLOW], 110, (0.2, 0.5))

    # ---- drawing
    def draw_ring(self, surf, game, t):
        S, (ex, ey) = self.S, self.px(0, 0)
        R = C.ORBIT_R
        c = game.craft
        ca = c.angle()
        for arc, col in ((C.HOT_ZONE, K.HEAT), (C.COLD_ZONE, K.ICE)):             # glowing zone bands
            a0, span = arc[0], (arc[1] - arc[0]) % 360.0
            n = max(6, int(span / 3))
            inner, outer = [], []
            for i in range(n + 1):
                a = math.radians(a0 + span * i / n)
                inner.append(self.px((R - 3.2) * math.cos(a), (R - 3.2) * math.sin(a)))
                outer.append(self.px((R + 3.2) * math.cos(a), (R + 3.2) * math.sin(a)))
            tint = (96, 30, 14) if col == K.HEAT else (20, 58, 96)
            pygame.draw.polygon(surf, tint, inner + outer[::-1])                    # dark tint, then a bright edge
            pygame.draw.lines(surf, tuple(int(v * 0.8) for v in col), False, outer, 2)
            pygame.draw.lines(surf, tuple(int(v * 0.8) for v in col), False, inner, 2)
            mid = math.radians(a0 + span / 2)
            lx, ly = self.px((R + 8.5) * math.cos(mid), (R + 8.5) * math.sin(mid))
            fonts.text(surf, "HOT ZONE" if col == K.HEAT else "COLD ZONE", (lx, ly), 22, col, bold=True, anchor="center")
        n = 120                                                                    # the dashed ring, glowing near the craft
        brk = self.ring_break
        for i in range(n):
            a0 = 360.0 * i / n
            a1 = a0 + 1.7
            d = abs(((a0 - ca + 180) % 360) - 180)
            glow = max(0.0, 1.0 - d / 45.0)
            col = K.mix((70, 100, 150), K.CYAN, glow)
            p0 = self.px(R * math.cos(math.radians(a0)), R * math.sin(math.radians(a0)))
            p1 = self.px(R * math.cos(math.radians(a1)), R * math.sin(math.radians(a1)))
            if brk > 0:                                                            # failed orbit: the ring breaks apart
                rr = random.Random(i)
                dx, dy = rr.uniform(-1, 1) * brk * 420, rr.uniform(-1, 1) * brk * 420
                p0, p1 = (p0[0] + dx, p0[1] + dy), (p1[0] + dx, p1[1] + dy)
                col = K.mix(col, K.BG, min(1.0, brk))
            pygame.draw.line(surf, col, p0, p1, 3 if glow > 0.5 else 2)
        a0, a1 = game.field.sector                                                 # the asteroid sector
        span = (a1 - a0) % 360.0
        warn = any(a.state == "warn" for a in game.field.asteroids)
        col = K.RED if warn and int(t * 8) % 2 else (150, 90, 45)
        pts = [self.px((R + 14) * math.cos(math.radians(a0 + span * i / 30)), (R + 14) * math.sin(math.radians(a0 + span * i / 30)))
               for i in range(31)]
        pygame.draw.lines(surf, col, False, pts, 2)
        mid = math.radians(a0 + span / 2)
        fonts.text(surf, "ASTEROID SECTOR", self.px((R + 19) * math.cos(mid), (R + 19) * math.sin(mid)), 18, col, anchor="center")

    def draw_board(self, surf):
        w, h = C.BOARD_W * self.S, C.BOARD_H * self.S
        r = pygame.Rect(0, 0, w, h)
        r.center = (self.cx, self.cy)
        pygame.draw.rect(surf, (30, 52, 92), r, 2, border_radius=6)
        L = 40
        for (x, y, dx, dy) in ((r.left, r.top, 1, 1), (r.right, r.top, -1, 1), (r.left, r.bottom, 1, -1), (r.right, r.bottom, -1, -1)):
            pygame.draw.lines(surf, K.CYAN, False, [(x, y + dy * L), (x, y), (x + dx * L, y)], 3)

    def draw_debris(self, surf, game):
        c = game.craft
        for d in game.field.debris:
            x, y = self.px(d.x, d.y)
            r = d.r * self.S
            key = (int(r), d.seed)
            if key not in self.sprites:
                self.sprites[key] = _rock_sprite(int(r), d.seed, (140, 142, 152) if d.real else (118, 112, 130))
            img = pygame.transform.rotate(self.sprites[key], d.rot)
            surf.blit(img, img.get_rect(center=(x, y)))
            dist = math.hypot(c.x - d.x, c.y - d.y) - d.r - C.CRAFT_R
            if dist < 25:                                                         # proximity ring
                a = 1.0 - max(0.0, dist) / 25.0
                pygame.draw.circle(surf, (int(255 * a), int(60 * a), int(60 * a)), (int(x), int(y)), int(r + 12 + 8 * math.sin(self.t * 8)), 2)
            if d.real:
                fonts.text(surf, "REAL", (x, y + r + 10), 15, K.GREY, anchor="midtop")
        for o in game.field.detected:
            x, y = self.px(o.x, o.y)
            pygame.draw.circle(surf, K.GREEN, (int(x), int(y)), int(o.r * self.S), 2)
            fonts.text(surf, "SCAN", (x, y + o.r * self.S + 4), 14, K.GREEN, anchor="midtop")

    def draw_asteroids(self, surf, game):
        tx, ty = self.px(*game.field.tower)
        tx = max(30, min(self.W - 30, tx))
        ty = max(30, min(self.H - 30, ty))
        warn = any(a.state == "warn" for a in game.field.asteroids)
        surf.blit(self.tower_glow, (tx - 30, ty - 30), special_flags=pygame.BLEND_RGB_ADD) if warn else None
        pygame.draw.rect(surf, K.RED if warn else K.GREY, (tx - 14, ty - 14, 28, 28), 3, border_radius=4)
        fonts.text(surf, "TOWER" + ("  OFFLINE" if game.tower_note else ""), (tx, ty - 24), 17,
                   K.RED if game.tower_note else K.GREY, anchor="midbottom")
        for a in game.field.asteroids:
            if a.state == "warn":                                                 # pulsing target line to the aim point
                p = 0.5 + 0.5 * math.sin(self.t * 14)
                x1, y1 = self.px(*a.target)
                n = int(math.hypot(x1 - tx, y1 - ty) / 22)
                for i in range(0, n, 2):
                    f0, f1 = i / n, min(1.0, (i + 1) / n)
                    pygame.draw.line(surf, (int(255 * (0.5 + 0.5 * p)), 60, 60), (tx + (x1 - tx) * f0, ty + (y1 - ty) * f0),
                                     (tx + (x1 - tx) * f1, ty + (y1 - ty) * f1), 3)
                pygame.draw.circle(surf, K.RED, (int(x1), int(y1)), int(30 + 10 * p), 2)
                pygame.draw.circle(surf, K.RED, (int(x1), int(y1)), 5)
                continue
            p = a.pos()
            if not p:
                continue
            x, y = self.px(*p)
            tr = self.asteroid_trails.setdefault(id(a), [])
            tr.append((x, y))
            del tr[:-18]
            for i, (qx, qy) in enumerate(tr):
                f = i / max(1, len(tr))
                pygame.draw.circle(surf, (int(255 * f), int(150 * f), int(40 * f)), (int(qx), int(qy)), max(2, int(14 * f)))
            r = max(10, int(C.ASTEROID_R * self.S * 1.6))
            key = ("ast", r, a.seed % 8)
            if key not in self.sprites:
                self.sprites[key] = _rock_sprite(r, a.seed, (150, 120, 95))
            img = pygame.transform.rotate(self.sprites[key], a.rot)
            surf.blit(img, img.get_rect(center=(x, y)))
            self.parts.emit(x, y, 1, [K.ORANGE, K.YELLOW], 30, (0.2, 0.4), (1.5, 3), drag=1.0)
        alive = {id(a) for a in game.field.asteroids}
        for k in [k for k in self.asteroid_trails if k not in alive]:
            del self.asteroid_trails[k]

    def draw(self, surf, game, ctx):
        """ctx: dict(ap_on, speed01, over_fx) from the app."""
        shake = ctx.get("shake", (0, 0))
        self.stars.draw(surf, shake, (game.craft.x / 60.0, game.craft.y / 40.0))
        self.draw_board(surf)
        self.draw_ring(surf, game, self.t)
        self.earth.draw(surf, self.px(0, 0))
        if ctx.get("backdrop"):                                                    # menus: just the planet and the ring
            return
        self.draw_debris(surf, game)
        if ctx.get("ap_on") and game.autopilot.path:                               # the planned path, faint
            pts = [self.px(x, y) for x, y in game.autopilot.path]
            if len(pts) > 1:
                col = K.RED if game.autopilot.zone == "danger" else K.YELLOW if game.autopilot.zone == "warning" else (50, 130, 110)
                pygame.draw.lines(surf, col, False, pts, 2)
        self.draw_asteroids(surf, game)
        if game.robot.connected:                                                  # where the real robot is
            g = game.ghost
            gx, gy = self.px(g.x, g.y)
            self.ship.draw_ghost(surf, gx, gy, g.theta, C.CRAFT_R * self.S, self.t)
        if not ctx.get("hide_craft"):
            c = game.craft
            x, y = self.px(c.x, c.y)
            self.ship.draw_trail(surf)
            self.ship.draw(surf, x, y, c.theta, ctx.get("speed01", 0.0), C.CRAFT_R * self.S, game.lives.protected(),
                           ap=ctx.get("ap_on", False))
        self.parts.draw(surf)
