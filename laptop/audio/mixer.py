"""Plays the synthesized sounds. Missing sound card, headless run, any pygame.mixer failure: silent, never a crash.
Engine hum: four seamless loops run together and their volumes cross-fade with speed, which raises the pitch."""
import pygame
import config as C
from audio import synth


class Mixer:
    def __init__(self):
        self.ok = False
        self.muted = False
        self.sounds, self.loops, self.chan = {}, {}, {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(synth.SR, -16, 1, 512)
            pygame.mixer.set_num_channels(24)
            import numpy as np
            for k, a in synth.build().items():
                self.sounds[k] = pygame.mixer.Sound(buffer=np.ascontiguousarray(a).tobytes())
            for k, a in synth.loops().items():
                snd = pygame.mixer.Sound(buffer=np.ascontiguousarray(a).tobytes())
                ch = snd.play(loops=-1)
                if ch is not None:
                    ch.set_volume(0.0)
                    self.loops[k], self.chan[k] = snd, ch
            self.ok = True
        except Exception:
            self.ok = False

    def vol(self):
        return 0.0 if self.muted else max(0.0, min(1.0, C.MASTER_VOLUME))

    def play(self, name, vol=1.0):
        if not self.ok or self.muted or name not in self.sounds:
            return
        try:
            s = self.sounds[name]
            s.set_volume(self.vol() * vol)
            s.play()
        except Exception:
            pass

    def update(self, speed01, engine_on, ambient_on):
        """Call once a frame. speed01 is 0..1."""
        if not self.ok:
            return
        v = self.vol()
        try:
            if "pad" in self.chan:
                self.chan["pad"].set_volume(v * (0.5 if ambient_on else 0.0))
            x = max(0.0, min(1.0, speed01)) * 3.0
            for i in range(4):
                w = max(0.0, 1.0 - abs(x - i)) if engine_on else 0.0
                self.chan["e%d" % i].set_volume(v * w * (0.18 + 0.22 * speed01))
        except Exception:
            pass

    def hush(self):
        """Engine and ambient off at once (game over)."""
        self.update(0.0, False, False)

    def toggle_mute(self):
        self.muted = not self.muted
        return self.muted
