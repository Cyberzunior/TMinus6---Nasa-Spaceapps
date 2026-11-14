"""Soak test: plays full demos (play, asteroid, hot, cold, game over, restart) back to back with software devices and
reports frame time, thread count and Python memory so a leak shows up.   python tools/soak.py --demos 3
(The 30 minute stability target needs a long run:  python tools/soak.py --minutes 30)"""
import argparse
import os
import sys
import threading
import time
import tracemalloc

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demos", type=int, default=3)
    ap.add_argument("--minutes", type=float, default=0.0, help="keep going for this long instead of a fixed number of demos")
    ap.add_argument("--real-time", action="store_true", help="pace frames at 60 fps (default: as fast as the machine allows)")
    a = ap.parse_args()
    import pygame
    pygame.init()
    from app import App, Args
    from core import statemachine as S
    app = App(Args(sim=True, demo=True, no_audio=True, seed=7), headless=True)
    app.boot_all()
    tracemalloc.start()
    t_end = time.time() + a.minutes * 60 if a.minutes else None
    demo, base_threads, samples = 0, threading.active_count(), []
    last = time.perf_counter()
    app.menu_choice("PLAY")
    t_demo = time.time()
    worst = 0.0
    while True:
        now = time.perf_counter()
        dt = now - last if a.real_time else 1 / 60
        last = now
        t0 = time.perf_counter()
        if not app.frame(dt):
            print("app stopped")
            return 1
        worst = max(worst, time.perf_counter() - t0)
        if a.real_time:
            time.sleep(max(0.0, 1 / 60 - (time.perf_counter() - t0)))
        st = app.sm.state
        if st in S.FLYING and app.game.t > 62 and not app.game.over:           # the scripted demo ran its course: lose the lives
            app.game.lives.lives, app.game.lives.shield = 1, 0.0
            app.game._hit("debris", app.game.craft.x, app.game.craft.y)
        elif st == S.RESULTS:
            demo += 1
            cur, peak = tracemalloc.get_traced_memory()
            samples.append(cur)
            print("demo %d done: python memory %.1f MB, threads %d (start %d), worst frame %.1f ms, state errors %d"
                  % (demo, cur / 1e6, threading.active_count(), base_threads, worst * 1000, len(app.errors)))
            worst = 0.0
            done = (time.time() >= t_end) if t_end else demo >= a.demos
            if done:
                break
            app._action("start")
            app.menu_choice("PLAY")
    growth = (samples[-1] - samples[0]) / 1e6 if len(samples) > 1 else 0.0
    threads_ok = threading.active_count() <= base_threads + 2
    print("memory growth over the run: %+.1f MB | thread leak: %s" % (growth, "no" if threads_ok else "YES"))
    app.shutdown()
    return 0 if threads_ok else 1


if __name__ == "__main__":
    sys.exit(main())
