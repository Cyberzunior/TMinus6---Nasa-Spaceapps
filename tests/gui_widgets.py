"""Small custom widgets for the triage GUI (painted with QPainter, no OpenGL)."""
import math
import time
from collections import deque

from PyQt5 import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt


class CubeWidget(QtWidgets.QWidget):
    """Wireframe XYZ cube with the controller vector drawn from the centre.

    X is right, Y is up, Z points at the viewer. Each component is -1..1, so the
    arrow tip always stays inside the cube. Drag to rotate, double click to reset.
    """
    DEFAULT_YAW, DEFAULT_PITCH = math.radians(-35), math.radians(22)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 280)
        self.vec = (0.0, 0.0, 0.0)
        self.yaw, self.pitch = self.DEFAULT_YAW, self.DEFAULT_PITCH
        self._last = None
        self.setToolTip("Drag to rotate, double click to reset the view")

    def set_vector(self, x, y, z):
        self.vec = (x, y, z)
        self.update()

    # -- projection
    def _project(self, p):
        x, y, z = p
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        x, z = cy * x + sy * z, -sy * x + cy * z
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        y, z = cp * y - sp * z, sp * y + cp * z
        f = 6.0 / (6.0 - z)                 # mild perspective, +z is toward the viewer
        return QtCore.QPointF(self._cx + self._s * x * f, self._cy - self._s * y * f)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.fillRect(self.rect(), QtGui.QColor("#ffffff"))
        self._cx, self._cy = self.width() / 2, self.height() / 2
        self._s = min(self.width(), self.height()) * 0.30
        proj = self._project

        # floor grid at y = -1
        p.setPen(QtGui.QPen(QtGui.QColor("#e3e6eb"), 1))
        for i in (-1, -0.5, 0, 0.5, 1):
            p.drawLine(proj((i, -1, -1)), proj((i, -1, 1)))
            p.drawLine(proj((-1, -1, i)), proj((1, -1, i)))

        # cube edges
        p.setPen(QtGui.QPen(QtGui.QColor("#8a93a3"), 1.4))
        corners = [(sx, sy, sz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        for a in corners:
            for b in corners:
                if sum(1 for i in range(3) if a[i] != b[i]) == 1 and a < b:
                    p.drawLine(proj(a), proj(b))

        # axes through the centre
        for end, colour, label in (((1.3, 0, 0), "#d32f2f", "X"),
                                   ((0, 1.3, 0), "#2e7d32", "Y"),
                                   ((0, 0, 1.3), "#1565c0", "Z")):
            p.setPen(QtGui.QPen(QtGui.QColor(colour), 1.6))
            neg = tuple(-c for c in end)
            p.drawLine(proj(neg), proj(end))
            tip = proj(end)
            p.drawText(QtCore.QPointF(tip.x() + 5, tip.y() - 4), label)

        # vector, with a drop line to the floor for depth
        x, y, z = self.vec
        tip, origin = proj((x, y, z)), proj((0, 0, 0))
        foot = proj((x, -1, z))
        p.setPen(QtGui.QPen(QtGui.QColor("#888888"), 1, Qt.DashLine))
        p.drawLine(tip, foot)
        p.setBrush(QtGui.QColor("#888888"))
        p.drawEllipse(foot, 3, 3)
        p.setPen(QtGui.QPen(QtGui.QColor("#e67e00"), 3.2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(origin, tip)
        p.setBrush(QtGui.QColor("#e67e00"))
        p.drawEllipse(tip, 6, 6)

        mag = math.sqrt(x * x + y * y + z * z)
        p.setPen(QtGui.QColor("#222222"))
        p.drawText(8, 18, f"x {x:+.2f}   y {y:+.2f}   z {z:+.2f}   |v| {mag:.2f}")

    # -- drag to rotate
    def mousePressEvent(self, e):
        self._last = e.pos()

    def mouseMoveEvent(self, e):
        if self._last is None:
            return
        d = e.pos() - self._last
        self._last = e.pos()
        self.yaw += d.x() * 0.01
        self.pitch = max(-1.4, min(1.4, self.pitch + d.y() * 0.01))
        self.update()

    def mouseReleaseEvent(self, _):
        self._last = None

    def mouseDoubleClickEvent(self, _):
        self.yaw, self.pitch = self.DEFAULT_YAW, self.DEFAULT_PITCH
        self.update()


class RadarWidget(QtWidgets.QWidget):
    """Top-down view of the robot's ultrasonic sweep. 0 deg is straight ahead,
    positive angles are drawn to the right. Readings fade after a few seconds."""
    FADE_S = 3.0

    def __init__(self, max_cm=200, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 200)
        self.max_cm = max_cm
        self.points = deque(maxlen=300)     # (angle, cm, time)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(100)

    def add(self, angle, cm):
        self.points.append((angle, cm, time.monotonic()))

    def clear(self):
        self.points.clear()
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.fillRect(self.rect(), QtGui.QColor("#f4f8f5"))
        cx, cy = self.width() / 2, self.height() - 14
        radius = min(self.width() / 2 - 12, self.height() - 28)
        rect = QtCore.QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius)

        def r_of(cm):
            return min(cm, self.max_cm) / self.max_cm * radius

        # spec zones: <8 cm hardware stop, <25 cm danger, <40 cm warning
        for cm, colour in ((40, "#fff3c4"), (25, "#ffd9b0"), (8, "#ffb3b3")):
            rr = r_of(cm)
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(colour))
            p.drawPie(QtCore.QRectF(cx - rr, cy - rr, 2 * rr, 2 * rr), 0, 180 * 16)
        p.setBrush(Qt.NoBrush)
        p.setPen(QtGui.QPen(QtGui.QColor("#9ccaae"), 1))
        for cm in range(50, self.max_cm + 1, 50):
            rr = r_of(cm)
            p.drawArc(QtCore.QRectF(cx - rr, cy - rr, 2 * rr, 2 * rr), 0, 180 * 16)
            p.drawText(QtCore.QPointF(cx + 3, cy - rr - 2), f"{cm} cm")
        p.drawArc(rect, 0, 180 * 16)
        for ang in (-90, -45, 0, 45, 90):
            a = math.radians(ang)
            p.setPen(QtGui.QPen(QtGui.QColor("#5fa37c" if abs(ang) == 45 else "#9ccaae"), 1,
                                Qt.DashLine if abs(ang) == 45 else Qt.SolidLine))
            p.drawLine(QtCore.QPointF(cx, cy),
                       QtCore.QPointF(cx + radius * math.sin(a), cy - radius * math.cos(a)))

        now = time.monotonic()
        newest = None
        for angle, cm, t in self.points:
            age = now - t
            if age > self.FADE_S:
                continue
            alpha = int(255 * (1 - age / self.FADE_S))
            a = math.radians(angle)
            no_echo = cm >= 400
            rr = radius if no_echo or cm > self.max_cm else r_of(cm)
            pt = QtCore.QPointF(cx + rr * math.sin(a), cy - rr * math.cos(a))
            colour = QtGui.QColor("#999999" if no_echo else "#1b9e55")
            colour.setAlpha(alpha)
            if no_echo or cm > self.max_cm:
                p.setPen(QtGui.QPen(colour, 1.5))
                p.setBrush(Qt.NoBrush)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(colour)
            p.drawEllipse(pt, 4, 4)
            newest = (angle, cm, a)
        if newest:
            _, _, a = newest
            p.setPen(QtGui.QPen(QtGui.QColor(30, 160, 90, 150), 2))
            p.drawLine(QtCore.QPointF(cx, cy),
                       QtCore.QPointF(cx + radius * math.sin(a), cy - radius * math.cos(a)))
        p.setBrush(QtGui.QColor("#222222"))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QtCore.QRectF(cx - 9, cy - 4, 18, 14), 3, 3)    # the robot
        p.setPen(QtGui.QColor("#555555"))
        p.drawText(8, 16, "red < 8 cm stop   orange < 25 cm danger   yellow < 40 cm warning")


class SparkLine(QtWidgets.QWidget):
    """Last N temperature readings with the COLD / HOT thresholds from the spec."""

    def __init__(self, cold=18.0, hot=30.0, n=60, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(110)
        self.cold, self.hot = cold, hot
        self.values = deque(maxlen=n)

    def add(self, v):
        self.values.append(v)
        self.update()

    def clear(self):
        self.values.clear()
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.fillRect(self.rect(), QtGui.QColor("#ffffff"))
        lo = min([self.cold - 4] + list(self.values))
        hi = max([self.hot + 4] + list(self.values))
        w, h = self.width() - 40, self.height() - 12

        def y_of(v):
            return 6 + h - (v - lo) / (hi - lo) * h

        for v, colour, label in ((self.hot, "#d32f2f", f"HOT {self.hot:.0f}"),
                                 (self.cold, "#1565c0", f"COLD {self.cold:.0f}")):
            p.setPen(QtGui.QPen(QtGui.QColor(colour), 1, Qt.DashLine))
            p.drawLine(0, int(y_of(v)), self.width() - 38, int(y_of(v)))
            p.drawText(self.width() - 36, int(y_of(v)) + 4, label)
        if len(self.values) < 2:
            return
        p.setPen(QtGui.QPen(QtGui.QColor("#e67e00"), 2))
        step = w / max(1, self.values.maxlen - 1)
        pts = [QtCore.QPointF(i * step, y_of(v)) for i, v in enumerate(self.values)]
        for a, b in zip(pts, pts[1:]):
            p.drawLine(a, b)


class VideoWidget(QtWidgets.QLabel):
    """Shows the newest QImage, scaled to fit while keeping the aspect ratio."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background:#000; color:#778;")
        self._img = None
        self.setText("no picture")

    def set_image(self, img):
        self._img = img
        self._rescale()

    def clear_image(self, text="no picture"):
        self._img = None
        self.clear()
        self.setText(text)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._rescale()

    def _rescale(self):
        if self._img is not None:
            self.setPixmap(QtGui.QPixmap.fromImage(self._img).scaled(
                self.size(), Qt.KeepAspectRatio, Qt.FastTransformation))
