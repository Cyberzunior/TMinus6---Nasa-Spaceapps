"""HUD building blocks: panels, hearts that crack, sparkline, banner, toasts, status dots, number tweening."""
import collections
import math
import pygame
from gfx import fonts, palette as K
from gfx.ship import glow_sprite

_panels = {}


def panel(surf, rect, alpha=170, edge=K.PANEL_EDGE, radius=14, scan=True):
    """A translucent navy panel with a thin glowing edge and a very faint scanline texture."""
    rect = pygame.Rect(rect)
    key = (rect.w, rect.h, alpha, edge, scan)
    if key not in _panels:
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(s, (*K.PANEL, alpha), s.get_rect(), border_radius=radius)
        if scan:
            for y in range(2, rect.h - 2, 4):
                pygame.draw.line(s, (255, 255, 255, 7), (6, y), (rect.w - 6, y))
        pygame.draw.rect(s, (*edge, 200), s.get_rect(), 2, border_radius=radius)
        _panels[key] = s
    surf.blit(_panels[key], rect.topleft)
    return rect


class Tween:
    """Smoothly follows a target value (ease-out)."""

    def __init__(self, v=0.0, rate=8.0):
        self.v, self.target, self.rate = float(v), float(v), rate

    def set(self, t):
        self.target = float(t)

    def update(self, dt):
        self.v += (self.target - self.v) * min(1.0, dt * self.rate)
        return self.v


def _heart_poly(size, color, outline=None, width=0):
    ss = size * 4
    s = pygame.Surface((ss, ss), pygame.SRCALPHA)
    r = ss * 0.26
    cx = ss / 2
    pygame.draw.circle(s, color, (cx - r * 0.95, ss * 0.36), r, width)
    pygame.draw.circle(s, color, (cx + r * 0.95, ss * 0.36), r, width)
    pts = [(cx - r * 1.93, ss * 0.42), (cx, ss * 0.92), (cx + r * 1.93, ss * 0.42)]
    pygame.draw.polygon(s, color, pts, width)
    return pygame.transform.smoothscale(s, (size, size))


class Hearts:
    """15 glowing hearts. A lost heart cracks in two, the halves fall apart and fade to an outline."""

    def __init__(self, n=15, size=28):
        self.n, self.size = n, size
        self.full = _heart_poly(size, (255, 80, 100))
        shine = _heart_poly(size, (255, 170, 180))
        self.full.blit(pygame.transform.smoothscale(shine, (size // 2, size // 2)), (size // 4, size // 6), special_flags=pygame.BLEND_RGB_ADD)
        self.empty = _heart_poly(size, (90, 100, 130), width=6)
        self.glow = glow_sprite(int(size * 0.75), (120, 20, 40), 2.0)
        self.shown = n
        self.anim = {}                  # index -> age

    def set(self, lives):
        while self.shown > lives:
            self.shown -= 1
            self.anim[self.shown] = 0.0
        self.shown = lives if lives > self.shown else self.shown

    def update(self, dt):
        for k in list(self.anim):
            self.anim[k] += dt
            if self.anim[k] > 0.9:
                del self.anim[k]

    def draw(self, surf, pos, lives, t):
        x0, y0 = pos
        step = self.size + 4
        for i in range(self.n):
            x = x0 + i * step
            if i in self.anim:
                a = self.anim[i]
                f = a / 0.9
                if a < 0.3:                                                 # the crack line flashes across the heart
                    surf.blit(self.full, (x, y0))
                    pygame.draw.lines(surf, (20, 10, 20), False, [(x + self.size * 0.5, y0), (x + self.size * 0.42, y0 + self.size * 0.35),
                                                                   (x + self.size * 0.58, y0 + self.size * 0.6), (x + self.size * 0.5, y0 + self.size)], 3)
                else:
                    g = (a - 0.3) / 0.6
                    half = self.size // 2
                    left = self.full.subsurface((0, 0, half, self.size)).copy()
                    right = self.full.subsurface((half, 0, self.size - half, self.size)).copy()
                    left.set_alpha(int(255 * (1 - g)))
                    right.set_alpha(int(255 * (1 - g)))
                    surf.blit(left, (x - 10 * g, y0 + 24 * g * g))
                    surf.blit(right, (x + half + 10 * g, y0 + 30 * g * g))
                    surf.blit(self.empty, (x, y0))
                fl = pygame.Surface((self.size + 8, self.size + 8), pygame.SRCALPHA)
                if f < 0.35:
                    pygame.draw.rect(fl, (255, 60, 60, int(160 * (1 - f / 0.35))), fl.get_rect(), border_radius=8)
                    surf.blit(fl, (x - 4, y0 - 4))
            elif i < lives:
                pulse = 0.65 + 0.35 * math.sin(t * 2.5 + i * 0.5)
                g = self.glow.copy()
                g.fill((int(255 * pulse),) * 3, special_flags=pygame.BLEND_RGB_MULT)
                surf.blit(g, (x + self.size // 2 - g.get_width() // 2, y0 + self.size // 2 - g.get_height() // 2),
                          special_flags=pygame.BLEND_RGB_ADD)
                surf.blit(self.full, (x, y0))
            else:
                surf.blit(self.empty, (x, y0))
        return x0 + self.n * step


def sparkline(surf, rect, values, color=K.CYAN, lo=None, hi=None):
    rect = pygame.Rect(rect)
    pygame.draw.rect(surf, (20, 32, 60), rect, border_radius=6)
    if len(values) < 2:
        return
    v0 = min(values) if lo is None else lo
    v1 = max(values) if hi is None else hi
    if v1 - v0 < 4:
        mid = (v0 + v1) / 2
        v0, v1 = mid - 2, mid + 2
    n = len(values)
    pts = [(rect.left + 4 + (rect.w - 8) * i / (n - 1), rect.bottom - 4 - (rect.h - 8) * (v - v0) / (v1 - v0)) for i, v in enumerate(values)]
    pygame.draw.lines(surf, color, False, pts, 2)
    pygame.draw.circle(surf, K.WHITE, (int(pts[-1][0]), int(pts[-1][1])), 3)


def dot(surf, pos, color, r=8, pulse=0.0):
    glow = glow_sprite(r * 2, color, 1.6)
    surf.blit(glow, (pos[0] - r * 2, pos[1] - r * 2), special_flags=pygame.BLEND_RGB_ADD)
    pygame.draw.circle(surf, color, pos, r)
    pygame.draw.circle(surf, K.mix(color, (255, 255, 255), 0.5), (pos[0] - 2, pos[1] - 2), max(2, r // 3))


class Toasts:
    def __init__(self):
        self.items = []                 # [text, kind, ttl]

    def add(self, text, kind="info", ttl=3.2):
        if self.items and self.items[-1][0] == text:
            self.items[-1][2] = ttl
            return
        self.items.append([text, kind, ttl])
        self.items = self.items[-4:]

    def update(self, dt):
        for it in self.items:
            it[2] -= dt
        self.items = [it for it in self.items if it[2] > 0]

    def draw(self, surf, cx, y):
        colors = {"info": K.CYAN, "ok": K.GREEN, "warn": K.YELLOW, "bad": K.RED}
        for text, kind, ttl in self.items:
            a = max(0.0, min(1.0, ttl / 0.5, (3.2 - ttl) / 0.15 + 0.2))
            w = fonts.width(text, 24) + 50
            r = pygame.Rect(0, 0, w, 42)
            r.midtop = (cx, y)
            s = pygame.Surface(r.size, pygame.SRCALPHA)
            pygame.draw.rect(s, (*K.PANEL, int(215 * a)), s.get_rect(), border_radius=21)
            pygame.draw.rect(s, (*colors.get(kind, K.CYAN), int(230 * a)), s.get_rect(), 2, border_radius=21)
            surf.blit(s, r.topleft)
            fonts.text(surf, text, r.center, 24, colors.get(kind, K.CYAN), anchor="center", alpha=int(255 * a))
            y += 50


def banner(surf, cx, y, title, sub, color, t, icon="warn"):
    """The big pulsing warning banner."""
    w = max(fonts.width(title, 32, bold=True), fonts.width(sub, 21)) + 170
    r = pygame.Rect(0, 0, w, 96)
    r.midtop = (cx, y)
    p = 0.5 + 0.5 * math.sin(t * 7)
    s = pygame.Surface(r.size, pygame.SRCALPHA)
    pygame.draw.rect(s, (*K.mix(K.PANEL, color, 0.18 + 0.1 * p), 225), s.get_rect(), border_radius=16)
    pygame.draw.rect(s, (*K.mix(color, K.WHITE, 0.25 * p), 255), s.get_rect(), 4, border_radius=16)
    surf.blit(s, r.topleft)
    ix, iy = r.left + 56, r.centery
    pygame.draw.polygon(surf, K.mix(color, K.WHITE, 0.2 * p), [(ix, iy - 32), (ix + 36, iy + 26), (ix - 36, iy + 26)])
    pygame.draw.polygon(surf, K.PANEL, [(ix, iy - 19), (ix + 25, iy + 20), (ix - 25, iy + 20)])
    fonts.text(surf, "!", (ix, iy + 3), 32, color, bold=True, anchor="center")
    fonts.text(surf, title, (r.centerx + 34, r.top + 34), 32, K.WHITE, bold=True, anchor="center", shadow=True)
    fonts.text(surf, sub, (r.centerx + 34, r.top + 72), 21, K.mix(color, K.WHITE, 0.55), anchor="center")
    return r
