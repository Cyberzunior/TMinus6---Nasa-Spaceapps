"""Fonts. Tries Segoe UI and Consolas, falls back to whatever exists, never crashes when they are missing."""
import pygame

_cache = {}


def reset():
    """Forget every font and rendered string (a new pygame session invalidates them)."""
    _cache.clear()
    _text_cache.clear()

SANS = "segoeui,seguisemibold,helveticaneue,arial,dejavusans,liberationsans"
MONO = "consolas,menlo,dejavusansmono,liberationmono,couriernew"


def get(size, mono=False, bold=False):
    key = (size, mono, bold)
    if key not in _cache:
        try:
            _cache[key] = pygame.font.SysFont(MONO if mono else SANS, size, bold=bold)
        except Exception:
            _cache[key] = pygame.font.Font(None, int(size * 1.2))
    return _cache[key]


_text_cache = {}


def reset():
    """Forget every font and rendered string (a new pygame session invalidates them)."""
    _cache.clear()
    _text_cache.clear()



def _render(s, size, color, mono, bold, shadow):
    """Rendered text is cached: building a surface per string per frame was a big part of the HUD cost."""
    key = (s, size, color, mono, bold, shadow)
    img = _text_cache.get(key)
    if img is None:
        if len(_text_cache) > 900:
            _text_cache.clear()
        f = get(size, mono, bold)
        img = f.render(s, True, color)
        if shadow:
            sh = f.render(s, True, (0, 0, 0))
            sh.set_alpha(150)
            both = pygame.Surface((img.get_width() + 2, img.get_height() + 2), pygame.SRCALPHA)
            both.blit(sh, (2, 2))
            both.blit(img, (0, 0))
            img = both
        _text_cache[key] = img
    return img


def text(surface, s, pos, size=24, color=(236, 242, 250), mono=False, bold=False, anchor="topleft", alpha=255, shadow=False):
    """Draw text and return its rect. anchor is any pygame rect attribute (topleft, center, midtop, topright...)."""
    img = _render(str(s), size, tuple(color), mono, bold, shadow)
    r = img.get_rect()
    setattr(r, anchor, pos)
    if alpha < 255:
        img = img.copy()
        img.set_alpha(alpha)
    surface.blit(img, r)
    return r


def width(s, size, mono=False, bold=False):
    return get(size, mono, bold).size(str(s))[0]
