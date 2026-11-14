"""Logging: logs/YYYYMMDD_HHMMSS.log (rotated, newest LOG_KEEP kept) and a weather CSV every 5 s."""
import csv
import glob
import logging
import os
import time
import config as C

ROOT = os.path.abspath(os.path.join(C.HERE, ".."))
LOG_DIR = os.path.join(ROOT, "logs")


def setup(debug=False):
    """Returns (log_function, path). Never raises: if the folder is read-only the game logs to the console only."""
    logger = logging.getLogger("tminus6")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.handlers.clear()
    path = None
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        old = sorted(glob.glob(os.path.join(LOG_DIR, "*.log")))
        for f in old[:max(0, len(old) - C.LOG_KEEP + 1)]:
            try:
                os.remove(f)
            except OSError:
                pass
        path = os.path.join(LOG_DIR, time.strftime("%Y%m%d_%H%M%S") + ".log")
        h = logging.FileHandler(path, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(message)s", "%H:%M:%S"))
        logger.addHandler(h)
    except OSError:
        pass
    if debug or path is None:
        logger.addHandler(logging.StreamHandler())
    return logger.info, path


class WeatherCsv:
    """time, temperature, humidity, state, every WEATHER_LOG_S while a run is on."""

    def __init__(self):
        self.f = self.w = None
        self.t_last = -99.0
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            self.f = open(os.path.join(LOG_DIR, time.strftime("weather_%Y%m%d_%H%M%S.csv")), "w", newline="")
            self.w = csv.writer(self.f)
            self.w.writerow(["time", "temp_c", "humidity", "state", "robot_temp_c"])
        except OSError:
            self.f = self.w = None

    def maybe(self, wall, weather):
        if self.w is None or wall - self.t_last < C.WEATHER_LOG_S or weather.temp is None:
            return
        self.t_last = wall
        try:
            self.w.writerow([time.strftime("%H:%M:%S"), "%.1f" % weather.temp, int(weather.hum or 0), weather.name(),
                             "" if weather.robot_temp is None else "%.1f" % weather.robot_temp])
            self.f.flush()
        except (OSError, ValueError):
            pass

    def close(self):
        try:
            self.f.close()
        except Exception:
            pass
