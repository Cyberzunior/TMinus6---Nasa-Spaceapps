"""Screen shake: decaying random offset."""
import math
import random


class Shake:
    def __init__(self):
        self.power = 0.0

    def add(self, amount):
        self.power = min(40.0, self.power + amount)

    def update(self, dt):
        self.power = max(0.0, self.power - 60.0 * dt)

    def offset(self):
        if self.power < 0.3:
            return 0, 0
        a = random.uniform(0, 6.283)
        return int(math.cos(a) * self.power * 0.5), int(math.sin(a) * self.power * 0.5)
