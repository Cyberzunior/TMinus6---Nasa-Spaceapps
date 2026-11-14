"""One clock for everything: monotonic seconds and microseconds."""
import time


def now():
    return time.perf_counter()


def now_us():
    return time.perf_counter_ns() // 1000


def mmss(seconds):
    seconds = max(0, int(seconds))
    return "%02d:%02d" % (seconds // 60, seconds % 60)
