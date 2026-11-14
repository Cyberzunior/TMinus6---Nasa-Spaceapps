"""One palette: deep navy space, cyan / blue accents, orange for danger, red for heat, ice blue for cold."""
BG = (5, 8, 20)
NAVY = (10, 16, 38)
PANEL = (10, 18, 40)
PANEL_EDGE = (40, 80, 130)
CYAN = (90, 220, 255)
BLUE = (70, 130, 255)
ICE = (150, 210, 255)
WHITE = (236, 242, 250)
GREY = (136, 150, 175)
DIM = (66, 78, 104)
ORANGE = (255, 150, 50)
YELLOW = (255, 214, 80)
RED = (255, 70, 70)
HEAT = (255, 90, 40)
GREEN = (80, 230, 140)
HULL = (225, 232, 245)
HULL_DARK = (110, 130, 165)
DOT = {"green": GREEN, "yellow": YELLOW, "red": RED}


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
