"""Lives and the hit rule: every hit costs exactly one life, then 1.5 s of protection."""
import config as C


class Lives:
    def __init__(self, practice=False):
        self.practice = practice
        self.reset()

    def reset(self):
        self.lives = C.LIVES
        self.shield = 0.0
        self.hits = {"debris": 0, "asteroid": 0, "bumper": 0}
        self.last_hit_t = -99.0

    @property
    def dead(self):
        return self.lives <= 0

    def protected(self):
        return self.shield > 0.0

    def hit(self, kind, t=0.0):
        """Returns True if the hit counted."""
        if self.dead or self.protected():
            return False
        self.hits[kind] = self.hits.get(kind, 0) + 1
        self.shield = C.SHIELD_S
        self.last_hit_t = t
        if not self.practice:
            self.lives -= 1
        return True

    def tick(self, dt):
        self.shield = max(0.0, self.shield - dt)
