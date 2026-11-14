"""Every sound is generated here with numpy. No audio files, nothing downloaded. Returns int16 mono arrays."""
import numpy as np

SR = 22050


def _t(sec):
    return np.arange(int(SR * sec)) / SR


def _env(n, attack=0.005, release=0.05):
    e = np.ones(n)
    a, r = max(1, int(SR * attack)), max(1, int(SR * release))
    e[:a] = np.linspace(0, 1, a)
    e[-r:] *= np.linspace(1, 0, r)
    return e


def _i16(x, vol=0.5):
    x = np.clip(x, -1, 1) * vol
    return (x * 32767).astype(np.int16)


def tone(freq, sec, vol=0.4, slide=0.0, shape="sine"):
    t = _t(sec)
    f = freq + slide * t / sec
    ph = 2 * np.pi * np.cumsum(f) / SR
    w = np.sin(ph) if shape == "sine" else np.sign(np.sin(ph)) * 0.6 if shape == "square" else 2 * (ph / (2 * np.pi) % 1) - 1
    return _i16(w * _env(len(t)), vol)


def noise_burst(sec, vol=0.4, lp=0.2, decay=6.0):
    n = int(SR * sec)
    x = np.random.default_rng(3).uniform(-1, 1, n)
    y = np.empty(n)
    acc = 0.0
    for i in range(n):                          # one-pole low pass: a boom, not a hiss
        acc += lp * (x[i] - acc)
        y[i] = acc
    y *= np.exp(-decay * np.arange(n) / n)
    return _i16(y / max(1e-6, np.abs(y).max()), vol)


def engine_loop(freq, sec=1.0):
    """Seamless low hum: whole number of cycles in the loop."""
    cycles = max(1, round(freq * sec))
    f = cycles / sec
    t = _t(sec)
    w = np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * 2 * f * t) + 0.25 * np.sin(2 * np.pi * 3 * f * t + 1)
    w += 0.12 * np.sin(2 * np.pi * 7 * f * t)
    return _i16(w / 1.9, 0.35)


def pad_loop(sec=8.0):
    t = _t(sec)
    w = sum(np.sin(2 * np.pi * f * t + p) * a for f, p, a in ((55, 0, 1), (82.5, 1, 0.6), (110.25, 2, 0.45), (165, 3, 0.25)))
    w *= 0.6 + 0.4 * np.sin(2 * np.pi * t / sec)
    return _i16(w / 2.4, 0.22)


def build():
    """name -> int16 array"""
    S = {}
    S["click"] = tone(1400, 0.04, 0.35, -400)
    S["confirm"] = np.concatenate([tone(660, 0.06, 0.35), tone(990, 0.09, 0.35)])
    S["connect"] = np.concatenate([tone(520, 0.08, 0.35), tone(780, 0.12, 0.35)])
    S["disconnect"] = np.concatenate([tone(780, 0.08, 0.35), tone(430, 0.16, 0.35)])
    S["incoming"] = np.concatenate([tone(500 + 120 * i, 0.12, 0.4, 100, "square") for i in range(5)])
    S["boom"] = noise_burst(0.9, 0.7, 0.08, 5.0)
    S["hit"] = np.concatenate([noise_burst(0.25, 0.6, 0.25, 8.0)[:5000] // 1, tone(140, 0.3, 0.5, -80)[:6000]])
    S["heart"] = np.concatenate([tone(440, 0.1, 0.3, -200), tone(300, 0.2, 0.3, -150)])
    S["dodge"] = tone(1300, 0.06, 0.2, 500)
    S["fire"] = tone(300, 0.12, 0.3, 500)
    one = np.concatenate([tone(1800, 0.05, 0.35, 0, "square"), np.zeros(int(SR * 0.05), np.int16)])
    S["hot"] = np.tile(one, 4)
    low = np.concatenate([tone(300, 0.1, 0.4), np.zeros(int(SR * 0.04), np.int16), tone(240, 0.16, 0.4),
                          np.zeros(int(SR * 0.3), np.int16)])
    S["cold"] = low
    S["spike"] = np.concatenate([tone(900, 0.08, 0.3), tone(1100, 0.08, 0.3), tone(900, 0.08, 0.3)])
    S["engine_fail"] = tone(180, 1.6, 0.5, -170, "saw")
    S["alarm"] = np.concatenate([tone(180, 0.35, 0.45, 0, "square"), tone(130, 0.35, 0.45, 0, "square")] * 3)
    S["burn"] = noise_burst(1.6, 0.4, 0.05, 3.0)
    S["pause"] = tone(500, 0.1, 0.3, -150)
    S["ready"] = np.concatenate([tone(523, 0.1, 0.35), tone(659, 0.1, 0.35), tone(784, 0.18, 0.35)])
    return S


def loops():
    return {"pad": pad_loop(), "e0": engine_loop(55), "e1": engine_loop(80), "e2": engine_loop(115), "e3": engine_loop(160)}
