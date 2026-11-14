"""Gamepad access for the triage GUI (pygame, joystick only, thread safe).

SDL's joystick state is only refreshed by event.pump(), which needs the video
subsystem. The 'dummy' video driver gives it one without opening any window.
"""
import os
import threading

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")

_lock = threading.RLock()
_pygame = None
_pad = None


def _pg():
    global _pygame
    if _pygame is None:
        import pygame
        pygame.display.init()
        pygame.joystick.init()
        _pygame = pygame
    return _pygame


def available():
    try:
        _pg()
        return True
    except Exception:       # noqa: BLE001 - pygame missing or no video driver
        return False


def rescan():
    """Re-detect controllers (call after pairing one over Bluetooth). -> [(index, name)]"""
    global _pad
    with _lock:
        pg = _pg()
        _pad = None
        pg.joystick.quit()
        pg.joystick.init()
        return [(i, pg.joystick.Joystick(i).get_name()) for i in range(pg.joystick.get_count())]


def select(index):
    """Open controller `index`. Returns its name, or None when it is not there."""
    global _pad
    with _lock:
        pg = _pg()
        if index < 0 or index >= pg.joystick.get_count():
            _pad = None
            return None
        _pad = pg.joystick.Joystick(index)
        return _pad.get_name()


def read():
    """Current state {'name','axes','buttons','hats'} or None when no pad is open."""
    with _lock:
        if _pad is None:
            return None
        pg = _pg()
        try:
            pg.event.pump()
            return {
                "name": _pad.get_name(),
                "axes": [_pad.get_axis(i) for i in range(_pad.get_numaxes())],
                "buttons": [_pad.get_button(i) for i in range(_pad.get_numbuttons())],
                "hats": [_pad.get_hat(i) for i in range(_pad.get_numhats())],
            }
        except Exception:       # noqa: BLE001 - pad unplugged mid read
            return None
