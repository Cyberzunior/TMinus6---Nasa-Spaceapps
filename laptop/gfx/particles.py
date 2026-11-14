"""Particles: exhaust, sparks, fragments, shockwave rings, heat shimmer, ice crystals, burn-up debris.
Rows are plain lists for speed: [x, y, vx, vy, life, max_life, size, color, kind]."""
import math
import random
import pygame


class Particles:
    def __init__(self, cap=900):
        self.p = []
        self.rings = []          # [x, y, radius, max_radius, life, color]
        self.cap = cap

    def emit(self, x, y, n, color, speed=90.0, life=(0.3, 0.8), size=(1.5, 3.5), spread=6.283, angle=0.0,
             kind="spark", drag=0.0):
        for _ in range(n):
            if len(self.p) >= self.cap:
                break
            a = angle + random.uniform(-spread / 2, spread / 2)
            v = random.uniform(0.25, 1.0) * speed
            L = random.uniform(*life)
            c = color if not isinstance(color, list) else random.choice(color)
            self.p.append([x, y, math.cos(a) * v, math.sin(a) * v, L, L, random.uniform(*size), c, kind, drag])

    def ring(self, x, y, max_r, color, life=0.6):
        self.rings.append([x, y, 4.0, max_r, life, life, color])

    def update(self, dt):
        out = []
        for q in self.p:
            q[4] -= dt
            if q[4] <= 0:
                continue
            k = 1.0 - q[9] * dt
            q[2] *= k
            q[3] *= k
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            out.append(q)
        self.p = out
        for r in self.rings:
            r[4] -= dt
            r[2] = r[3] * (1.0 - r[4] / r[5])
        self.rings = [r for r in self.rings if r[4] > 0]

    def draw(self, surf):
        for q in self.p:
            f = q[4] / q[5]
            c = q[7]
            col = (int(c[0] * f), int(c[1] * f), int(c[2] * f))
            s = max(1, int(q[6] * (0.4 + 0.6 * f)))
            if q[8] == "ice":
                x, y = int(q[0]), int(q[1])
                pygame.draw.line(surf, col, (x - s, y), (x + s, y), 1)
                pygame.draw.line(surf, col, (x, y - s), (x, y + s), 1)
            else:
                surf.fill(col, (int(q[0]), int(q[1]), s, s), special_flags=pygame.BLEND_RGB_ADD)
        for r in self.rings:
            f = r[4] / r[5]
            col = (int(r[6][0] * f), int(r[6][1] * f), int(r[6][2] * f))
            rr = int(r[2])
            if rr > 2:
                pygame.draw.circle(surf, col, (int(r[0]), int(r[1])), rr, max(1, int(5 * f)))
