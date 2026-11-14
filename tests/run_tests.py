"""Runs the test_*.py files without pytest:   python tests/run_tests.py [name-filter]
(With pytest installed, `pytest tests` does the same.) Exit code 1 when anything fails."""
import glob
import importlib
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import conftest  # noqa: F401,E402


def main():
    flt = sys.argv[1] if len(sys.argv) > 1 else ""
    passed = failed = 0
    for path in sorted(glob.glob(os.path.join(HERE, "test_*.py"))):
        mod = importlib.import_module(os.path.basename(path)[:-3])
        for name in sorted(n for n in dir(mod) if n.startswith("test_")):
            if flt and flt not in name and flt not in mod.__name__:
                continue
            t0 = time.time()
            print("RUN  %s.%s" % (mod.__name__, name), flush=True)
            try:
                getattr(mod, name)()
                passed += 1
                print("PASS %-58s %.2fs" % (mod.__name__ + "." + name, time.time() - t0))
            except Exception:
                failed += 1
                print("FAIL %s.%s\n%s" % (mod.__name__, name, traceback.format_exc()))
    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
