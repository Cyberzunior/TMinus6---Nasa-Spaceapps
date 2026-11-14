"""Makes `laptop/` importable and keeps pygame headless. Used by pytest and by tests/run_tests.py."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LAPTOP = os.path.join(ROOT, "laptop")
for p in (LAPTOP, os.path.join(LAPTOP, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)
