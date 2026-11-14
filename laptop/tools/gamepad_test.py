"""Pair the gamepad in Bluetooth settings, run this, press every button and move every stick.
It prints the axis and button numbers for config.py (or config.local.json).   python tools/gamepad_test.py"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
import pygame  # noqa: E402

import config as C  # noqa: E402


def main():
    pygame.init()
    pygame.joystick.init()
    pygame.display.set_mode((560, 120))
    pygame.display.set_caption("gamepad test (close this window to stop)")
    if pygame.joystick.get_count() == 0:
        print("No gamepad found. Pair it in the Bluetooth settings first (Xbox pad: hold the pair button until the light blinks fast).")
        return 1
    pad = pygame.joystick.Joystick(0)
    pad.init()
    print("Gamepad: %s | %d axes, %d buttons, %d hats" % (pad.get_name(), pad.get_numaxes(), pad.get_numbuttons(), pad.get_numhats()))
    print("Settings now: AXIS_TURN=%d AXIS_SPEED=%d BTN_AUTOPILOT(Y)=%d BTN_CAMERA(B)=%d BTN_RESTART(Start)=%d BTN_BACK=%d BTN_FIRE(X)=%d BTN_CONFIRM(A)=%d"
          % (C.AXIS_TURN, C.AXIS_SPEED, C.BTN_AUTOPILOT, C.BTN_CAMERA, C.BTN_RESTART, C.BTN_BACK, C.BTN_FIRE, C.BTN_CONFIRM))
    print("Move the left stick, press Y, B, X, A, Start, Back, and both triggers. Ctrl+C or close the window to stop.\n")
    last = {}
    names = {C.BTN_AUTOPILOT: "Y", C.BTN_CAMERA: "B", C.BTN_FIRE: "X", C.BTN_CONFIRM: "A", C.BTN_RESTART: "Start", C.BTN_BACK: "Back"}
    try:
        while True:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return 0
                if e.type == pygame.JOYBUTTONDOWN:
                    print("button %2d pressed   (config calls it %s)" % (e.button, names.get(e.button, "unassigned")))
                elif e.type == pygame.JOYHATMOTION:
                    print("hat %d -> %s" % (e.hat, e.value))
            for i in range(pad.get_numaxes()):                                   # print an axis only when it moved a lot
                v = round(pad.get_axis(i), 2)
                if abs(v - last.get(i, 0.0)) > 0.35:
                    print("axis %d = %+.2f" % (i, v))
                    last[i] = v
            time.sleep(0.01)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
