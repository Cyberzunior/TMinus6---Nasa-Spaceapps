"""Screen flow: BOOT -> HARDWARE CHECK -> MENU -> (PLAY | PRACTICE | CALIBRATE | SETTINGS) -> PAUSE -> GAME OVER
-> RESULTS -> MENU. Hardware Check can be opened from the menu and from pause and returns where it came from."""
BOOT, HWCHECK, MENU, PLAY, PRACTICE, CALIBRATE, SETTINGS, PAUSE, GAMEOVER, RESULTS = (
    "BOOT", "HWCHECK", "MENU", "PLAY", "PRACTICE", "CALIBRATE", "SETTINGS", "PAUSE", "GAMEOVER", "RESULTS")

ALLOWED = {
    BOOT: {HWCHECK, MENU},
    HWCHECK: {MENU, PAUSE},
    MENU: {PLAY, PRACTICE, CALIBRATE, SETTINGS, HWCHECK},
    PLAY: {PAUSE, GAMEOVER, MENU},
    PRACTICE: {PAUSE, MENU},
    CALIBRATE: {MENU},
    SETTINGS: {MENU},
    PAUSE: {PLAY, PRACTICE, MENU, HWCHECK},
    GAMEOVER: {RESULTS},
    RESULTS: {MENU, PLAY},
}
FLYING = (PLAY, PRACTICE)


class StateMachine:
    def __init__(self, on_change=None):
        self.state = BOOT
        self.previous = BOOT
        self.resume = PLAY               # what PAUSE returns to
        self.entered = 0.0
        self.on_change = on_change

    def can(self, new):
        return new in ALLOWED[self.state]

    def go(self, new, now=0.0):
        """Switch state. Returns False (and stays) if the flow does not allow it."""
        if not self.can(new):
            return False
        if new == PAUSE and self.state in FLYING:
            self.resume = self.state
        if new in FLYING and self.state == PAUSE and new != self.resume:
            return False
        old, self.previous, self.state, self.entered = self.state, self.state, new, now
        if self.on_change:
            self.on_change(old, new)
        return True

    def flying(self):
        return self.state in FLYING

    def time_in(self, now):
        return now - self.entered
