"""Robot camera. One thread keeps ONLY the newest frame (MJPEG from an ESP32-CAM or a phone app, or the simulated
first-person view). It reconnects by itself, reports the frame age, and never touches the control link."""
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import config as C
from core.clock import now


def probe_port81(subnet_prefix, timeout=0.2):
    """Looks for an ESP32-CAM (CameraWebServer streams on :81) in the /24 of the robot's address."""
    def check(i):
        ip = "%s.%d" % (subnet_prefix, i)
        try:
            with socket.create_connection((ip, 81), timeout=timeout):
                return ip
        except OSError:
            return None
    with ThreadPoolExecutor(64) as ex:
        for ip in ex.map(check, range(1, 255)):
            if ip:
                return "http://%s:81/stream" % ip
    return None


class Camera(threading.Thread):
    def __init__(self, state, log, url=None, sim_source=None, robot_ip=lambda: None):
        super().__init__(daemon=True, name="camera")
        self.state, self.log = state, log
        self.url, self.sim_source, self.robot_ip = url or C.CAMERA_URL, sim_source, robot_ip
        self.stop_flag = threading.Event()
        self.frame = None                  # numpy RGB (h, w, 3)
        self.stamp = 0.0
        self.fps = 0.0
        self.error = ""
        self.size = (0, 0)

    def age_ms(self):
        return (now() - self.stamp) * 1000.0 if self.frame is not None else None

    def live(self):
        a = self.age_ms()
        return a is not None and a < 2000.0

    def _publish(self, rgb):
        self.frame, self.stamp = rgb, now()
        self.size = (rgb.shape[1], rgb.shape[0])

    def _mark(self):
        with self.state.lock:
            d = self.state.devices["camera"]
            d.connected = self.live()
            d.where = ("sim view" if self.sim_source else self.url) or "searching"
            d.note = "" if d.connected else (self.error or "NO SIGNAL")
            a = self.age_ms()
            d.rtt_ms = None
            d.sim = self.sim_source is not None
            d.rx_rate = self.fps

    def run(self):
        if self.sim_source is not None:
            return self._run_sim()
        try:
            import cv2
        except ImportError:
            self.error = "opencv-python is not installed"
            self.log("camera: " + self.error)
            while not self.stop_flag.wait(1.0):
                self._mark()
            return
        t_probe = -99.0
        while not self.stop_flag.is_set():
            if not self.url:
                self._mark()
                ip = self.robot_ip()
                if ip and now() - t_probe > 10.0:
                    t_probe = now()
                    self.error = "looking for the camera"
                    found = probe_port81(ip.rsplit(".", 1)[0])
                    if found:
                        self.url = found
                        self.log("camera found at " + found)
                self.stop_flag.wait(0.5)
                continue
            cap = None
            try:
                cap = cv2.VideoCapture(self.url)
                try:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    pass
                n, t0 = 0, now()
                while not self.stop_flag.is_set() and cap.isOpened():
                    ok, img = cap.read()
                    if not ok:
                        break
                    self._publish(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))   # privacy: frames are never saved
                    self.error = ""
                    n += 1
                    if now() - t0 >= 1.0:
                        self.fps, n, t0 = n / (now() - t0), 0, now()
                    self._mark()
            except Exception as e:
                self.error = "camera error: %s" % e
            finally:
                if cap is not None:
                    cap.release()
            self.error = self.error or "no stream at %s" % self.url
            self._mark()
            self.stop_flag.wait(1.0)             # stream dropped: try again

    def _run_sim(self):
        while not self.stop_flag.is_set():
            try:
                self._publish(self.sim_source())
                self.fps = 15.0
                self._mark()
            except Exception as e:
                self.error = "sim camera: %s" % e
            self.stop_flag.wait(1 / 15.0)

    def stop(self):
        self.stop_flag.set()
