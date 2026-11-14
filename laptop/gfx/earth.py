"""Procedural Earth: oceans and continents from layered noise, rotating clouds, a day/night terminator (the Sun is on
the left, matching the hot zone) and a glowing atmosphere. Frames are rendered once at boot with numpy, then the
game only blits two pre-made surfaces per frame."""
import math
import numpy as np
import pygame

FRAMES = 40


def _fields(seed, octaves):
    """Sum-of-sines noise on the sphere. Three random directions per octave, so no single plane wave shows as a band."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(octaves):
        for _ in range(3):
            d = rng.normal(size=3)
            d /= np.linalg.norm(d)
            out.append((d * (1.7 * 1.85 ** i), rng.uniform(0, 6.28), 1.0 / 1.7 ** i))
    return out


def _noise(px, py, pz, fields):
    n = 0.0
    tot = 0.0
    for d, ph, a in fields:
        n = n + a * np.sin(px * d[0] + py * d[1] + pz * d[2] + ph)
        tot += a
    return n / tot


def build(radius, seed=4):
    """Returns (earth_frames, cloud_frames, atmosphere_surface), each earth/cloud frame (2r x 2r)."""
    R = int(radius)
    size = 2 * R
    ys, xs = np.mgrid[0:size, 0:size]
    nx = (xs + 0.5 - R) / R
    ny = (ys + 0.5 - R) / R
    r2 = nx ** 2 + ny ** 2
    inside = r2 < 1.0
    nz = np.sqrt(np.clip(1.0 - r2, 0, 1))
    L = np.array([-0.82, -0.12, 0.56])
    L /= np.linalg.norm(L)
    diff = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    soft = np.clip((nx * L[0] + ny * L[1] + nz * L[2]) * 3.0 + 0.45, 0, 1)         # soft terminator
    land_f, cloud_f, snow_f = _fields(seed, 7), _fields(seed + 9, 5), _fields(seed + 5, 3)
    earth, clouds = [], []
    edge = np.clip((1.0 - np.sqrt(np.clip(r2, 0, 1))) * R, 0, 1)                    # anti-aliased rim
    for k in range(FRAMES):
        phi = 2 * math.pi * k / FRAMES
        px = nx * math.cos(phi) + nz * math.sin(phi)
        pz = -nx * math.sin(phi) + nz * math.cos(phi)
        tc, ts = math.cos(0.41), math.sin(0.41)                                     # 23.5 degrees of axial tilt
        qy, qz = ny * tc - pz * ts, ny * ts + pz * tc
        h = _noise(px, qy, qz, land_f)
        lat = np.abs(qy)
        land = h > 0.08
        ocean = np.zeros((size, size, 3))
        deep = np.clip((0.08 - h) * 2.2, 0, 1)
        ocean[..., 0] = 14 + 10 * (1 - deep)
        ocean[..., 1] = 60 + 45 * (1 - deep)
        ocean[..., 2] = 130 + 70 * (1 - deep)
        veg = np.clip((h - 0.08) * 3.0, 0, 1)
        ground = np.zeros_like(ocean)
        ground[..., 0] = 60 + 110 * veg * (lat * 0.8 + 0.2)
        ground[..., 1] = 130 - 20 * veg
        ground[..., 2] = 55 + 25 * veg
        col = np.where(land[..., None], ground, ocean)
        snow = (lat > 0.84 + 0.1 * _noise(px, qy, qz, snow_f))
        col = np.where(snow[..., None], np.array([235, 242, 250]), col)
        spec = np.clip((np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)) ** 40, 0, 1) * (~land) * 0.6
        lit = col * (0.06 + 0.94 * soft[..., None]) * (0.55 + 0.45 * diff[..., None] ** 0.6) + spec[..., None] * 255
        rgba = np.zeros((size, size, 4), np.uint8)
        rgba[..., :3] = np.clip(lit, 0, 255)
        rgba[..., 3] = np.where(inside, 255 * edge, 0)
        earth.append(pygame.image.frombuffer(rgba.tobytes(), (size, size), "RGBA").convert_alpha())

        phc = phi * 1.7 + 0.8
        cx_ = nx * math.cos(phc) + nz * math.sin(phc)
        cz_ = -nx * math.sin(phc) + nz * math.cos(phc)
        c = np.clip((_noise(cx_ * 1.2, ny * 1.2, cz_ * 1.2, cloud_f) - 0.14) * 2.6, 0, 1)
        cl = np.zeros((size, size, 4), np.uint8)
        shade = 0.12 + 0.88 * soft
        cl[..., 0] = cl[..., 1] = cl[..., 2] = np.clip(245 * shade, 0, 255)
        cl[..., 3] = np.where(inside, 190 * c * edge * (0.25 + 0.75 * soft), 0)
        clouds.append(pygame.image.frombuffer(cl.tobytes(), (size, size), "RGBA").convert_alpha())

    glow = int(R * 0.28)
    gs = size + 2 * glow
    gy, gx = np.mgrid[0:gs, 0:gs]
    d = np.sqrt((gx + 0.5 - gs / 2) ** 2 + (gy + 0.5 - gs / 2) ** 2) / R
    a = np.clip(1.0 - (d - 1.0) / 0.28, 0, 1) ** 2.2 * (d >= 0.97)
    sun = np.clip(((gx - gs / 2) / (R * -1.0)) * 0.6 + 0.55, 0.15, 1.0)             # brighter on the Sun side
    atm = np.zeros((gs, gs, 4), np.uint8)
    atm[..., 0], atm[..., 1], atm[..., 2] = 70, 150, 255
    atm[..., 3] = np.clip(a * 190 * sun, 0, 255)
    atmosphere = pygame.image.frombuffer(atm.tobytes(), (gs, gs), "RGBA").convert_alpha()
    return earth, clouds, atmosphere, glow


class Earth:
    def __init__(self, radius_px):
        self.r = int(radius_px)
        self.earth, self.clouds, self.atm, self.glow = build(self.r)
        self.t = 0.0

    def update(self, dt):
        self.t += dt

    def draw(self, surf, center, tint=None):
        cx, cy = center
        surf.blit(self.atm, (cx - self.r - self.glow, cy - self.r - self.glow))
        k = int(self.t * 1.6) % FRAMES
        surf.blit(self.earth[k], (cx - self.r, cy - self.r))
        surf.blit(self.clouds[int(self.t * 2.4) % FRAMES], (cx - self.r, cy - self.r))
