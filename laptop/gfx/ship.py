"""The T-Minus_6 craft: gradient hull, glowing cockpit, wings, an engine flame that follows speed, blinking navigation
lights and a fading trail. Also draws the dashed outline used for the robot ghost."""
import collections
import math
import random
import pygame
from gfx import palette as K


def glow_sprite(radius, color, power=2.0):
    s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for r in range(radius, 0, -2):
        a = (1.0 - r / radius) ** power
        pygame.draw.circle(s, (color[0], color[1], color[2], int(255 * a)), (radius, radius), r)
    return s


class Ship:
    def __init__(self, scale):
        self.S = scale
        self.trail = collections.deque(maxlen=46)
        self.t = 0.0
        self.cockpit_glow = glow_sprite(26, K.CYAN, 1.6)
        self.flame_glow = glow_sprite(28, (150, 70, 20), 2.4)
        self.nav_red = glow_sprite(10, K.RED, 1.2)
        self.nav_green = glow_sprite(10, K.GREEN, 1.2)

    def pts(self, cx, cy, h, size, shape):
        a = math.radians(h)
        c, s = math.cos(a), math.sin(a)
        return [(cx + size * (x * c - y * s), cy + size * (x * s + y * c)) for x, y in shape]

    HULL = [(1.15, 0), (0.45, -0.28), (-0.2, -0.46), (-0.72, -0.4), (-0.55, 0), (-0.72, 0.4), (-0.2, 0.46), (0.45, 0.28)]
    TOP = [(1.0, 0), (0.4, -0.2), (-0.35, -0.3), (-0.5, 0), (-0.35, 0.3), (0.4, 0.2)]
    WING_L = [(0.1, -0.4), (-0.35, -1.12), (-0.78, -1.12), (-0.52, -0.38)]
    WING_R = [(0.1, 0.4), (-0.35, 1.12), (-0.78, 1.12), (-0.52, 0.38)]

    def update(self, dt, x, y, speed01):
        self.t += dt
        if speed01 > 0.03 or len(self.trail):
            self.trail.append([x, y, 1.0])
        for p in self.trail:
            p[2] -= dt * 1.1
        while self.trail and self.trail[0][2] <= 0:
            self.trail.popleft()

    def draw_trail(self, surf, moving=True):
        for p in self.trail:
            a = max(0.0, p[2])
            r = max(1, int(7 * a))
            surf.fill((int(60 * a), int(150 * a), int(230 * a)), (int(p[0]) - r // 2, int(p[1]) - r // 2, r, r),
                      special_flags=pygame.BLEND_RGB_ADD)

    def draw(self, surf, x, y, heading, speed01, size, flash=False, scorch=0.0, flame_override=None, ap=False):
        if flash and int(self.t * 14) % 2:
            return
        cx, cy = x, y
        hull = K.mix(K.HULL, (255, 150, 60), scorch)
        dark = K.mix(K.HULL_DARK, (150, 50, 20), scorch)
        flame = speed01 if flame_override is None else flame_override
        if flame > 0.04:                                                  # flame: three flickering layers
            fl = size * (0.35 + 1.1 * flame) * random.uniform(0.85, 1.15)
            for scale, col in ((1.0, (255, 90, 30)), (0.7, (255, 170, 50)), (0.4, (255, 245, 190))):
                tip = self.pts(cx, cy, heading, size, [(-0.7 - fl / size * scale, 0)])[0]
                base = self.pts(cx, cy, heading, size, [(-0.62, -0.2 * scale - 0.05), (-0.62, 0.2 * scale + 0.05)])
                pygame.draw.polygon(surf, col, [base[0], tip, base[1]])
            g = self.flame_glow
            e = self.pts(cx, cy, heading, size, [(-0.85, 0)])[0]
            surf.blit(g, (e[0] - 28, e[1] - 28), special_flags=pygame.BLEND_RGB_ADD)
        pygame.draw.polygon(surf, (30, 70, 140), self.pts(cx, cy, heading, size, self.WING_L))
        pygame.draw.polygon(surf, (30, 70, 140), self.pts(cx, cy, heading, size, self.WING_R))
        pygame.draw.polygon(surf, K.BLUE, self.pts(cx, cy, heading, size, self.WING_L), 2)
        pygame.draw.polygon(surf, K.BLUE, self.pts(cx, cy, heading, size, self.WING_R), 2)
        pygame.draw.polygon(surf, dark, self.pts(cx, cy, heading, size, self.HULL))             # gradient: dark base, bright top
        pygame.draw.polygon(surf, hull, self.pts(cx, cy, heading, size, self.TOP))
        pygame.draw.polygon(surf, K.mix(hull, (255, 255, 255), 0.5), self.pts(cx, cy, heading, size, [(1.0, 0), (0.4, -0.2), (0.2, 0)]))
        pygame.draw.polygon(surf, K.WHITE if not scorch else K.ORANGE, self.pts(cx, cy, heading, size, self.HULL), 2)
        cp = self.pts(cx, cy, heading, size, [(0.35, 0)])[0]
        surf.blit(self.cockpit_glow, (cp[0] - 26, cp[1] - 26), special_flags=pygame.BLEND_RGB_ADD)
        pygame.draw.circle(surf, K.CYAN, (int(cp[0]), int(cp[1])), max(3, int(size * 0.13)))
        if int(self.t * 2) % 2 == 0:                                       # navigation lights blink
            l, r = self.pts(cx, cy, heading, size, [(-0.78, -1.12), (-0.78, 1.12)])
            surf.blit(self.nav_red, (l[0] - 10, l[1] - 10), special_flags=pygame.BLEND_RGB_ADD)
            surf.blit(self.nav_green, (r[0] - 10, r[1] - 10), special_flags=pygame.BLEND_RGB_ADD)
        if ap:
            pygame.draw.circle(surf, K.GREEN, (int(cx), int(cy)), int(size * 1.35), 2)

    def draw_ghost(self, surf, x, y, heading, size, t):
        col = K.CYAN
        pts = self.pts(x, y, heading, size, self.HULL)
        for i in range(len(pts)):
            if (i + int(t * 6)) % 2 == 0:
                pygame.draw.line(surf, col, pts[i], pts[(i + 1) % len(pts)], 2)
