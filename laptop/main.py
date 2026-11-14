"""T-Minus_6: the game.   python main.py [--sim] [--windowed] [--debug]

  --sim              every device is a software one (no hardware needed). Mixed mode: --sim-robot --sim-tower
                     --sim-station --sim-camera in any combination.
  --windowed         start windowed even if FULLSCREEN is set in config.local.json
  --debug            FPS / thread / packet overlay (F4 toggles it) and log lines on the console
  --demo             scripted rehearsal: timed asteroids and hot / cold zones
  --no-audio         silent
  --seed N           repeatable asteroid timing"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.chdir(HERE)


def parse(argv=None):
    p = argparse.ArgumentParser(description="T-Minus_6 game")
    p.add_argument("--sim", action="store_true", help="simulate all devices")
    for n in ("robot", "tower", "station", "camera"):
        p.add_argument("--sim-" + n, action="store_true", help="simulate the " + n)
    p.add_argument("--windowed", action="store_true")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--demo", action="store_true")
    p.add_argument("--no-audio", action="store_true")
    p.add_argument("--no-serial", action="store_true", help="never open serial ports")
    p.add_argument("--seed", type=int, default=None)
    return p.parse_args(argv)


def main(argv=None):
    ns = parse(argv)
    try:
        import numpy  # noqa: F401
        import pygame  # noqa: F401
        import serial  # noqa: F401
    except ImportError as e:
        print("A required package is missing (%s).\nInstall everything with:  pip install -r requirements.txt" % e)
        return 1
    import pygame
    from app import App, Args
    pygame.init()
    args = Args(**{k: v for k, v in vars(ns).items() if k != "sim"}, sim=ns.sim)
    app = App(args)
    try:
        app.run()
    except KeyboardInterrupt:
        app.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
