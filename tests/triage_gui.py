#!/usr/bin/env python3
"""T-Minus_6 hardware triage GUI.

    pip install -r tests/requirements.txt
    python tests/triage_gui.py

Two modes, toggled at the top:
  CASE  acceptance tests per sector, from docs/T-Minus_6_Project_Document.pdf
  FUNC  barebones controls: stepper / servo sliders, LCD text, tower fire, robot drive,
        weather readout, robot camera, and the gamepad vector in an XYZ cube

The command line tool tests/triage.py still works as before.
"""
import re
import sys
import time

from PyQt5 import QtCore, QtGui, QtWidgets

from gui_case import CaseMode
from gui_common import (CAMERA_URLS, DEVICE_LABEL, DEVICES, Link, list_serial_ports, load_settings,
                        parse_target, save_settings)
from gui_func import FuncMode

Qt = QtCore.Qt
STATE_COLOUR = {"closed": "#888888", "connecting": "#d29922", "open": "#3fb950", "error": "#f85149"}


class Shared:
    """What the mode pages need from the main window."""

    def __init__(self):
        self.links = {key: Link(key) for key, _, _ in DEVICES}
        self.camera_combo = None
        self.log = lambda text: None

    def camera_url(self):
        return self.camera_combo.currentText().strip() if self.camera_combo is not None else ""


class ConnectionsPanel(QtWidgets.QGroupBox):
    def __init__(self, shared, saved):
        super().__init__("Connections")
        self.shared = shared
        self.saved = saved.get("targets", {})
        self.setMaximumWidth(300)
        grid = QtWidgets.QGridLayout(self)
        self.rows = {}
        r = 0
        for key, label, default in DEVICES:
            link = shared.links[key]
            title = QtWidgets.QLabel(label)
            title.setStyleSheet("font-weight:bold;")
            combo = QtWidgets.QComboBox()
            combo.setEditable(True)
            combo.setToolTip("COM port (serial) or ip:port (UDP)")
            btn = QtWidgets.QPushButton("Connect")
            dot = QtWidgets.QLabel("●")
            detail = QtWidgets.QLabel("")
            detail.setStyleSheet("color:#666; font-size:11px;")
            detail.setWordWrap(True)
            grid.addWidget(title, r, 0, 1, 3)
            grid.addWidget(combo, r + 1, 0)
            grid.addWidget(btn, r + 1, 1)
            grid.addWidget(dot, r + 1, 2)
            grid.addWidget(detail, r + 2, 0, 1, 3)
            r += 3
            self.rows[key] = (combo, btn, dot, detail, default)
            btn.clicked.connect(lambda _, k=key: self._toggle(k))
            link.state_changed.connect(lambda state, text, k=key: self._on_state(k, state, text))
            self._on_state(key, "closed", "")

        cam_title = QtWidgets.QLabel("Camera stream URL")
        cam_title.setStyleSheet("font-weight:bold;")
        self.cam = QtWidgets.QComboBox()
        self.cam.setEditable(True)
        self.cam.addItems(CAMERA_URLS + ["0"])
        self.cam.setToolTip("ESP32-CAM or phone stream URL; a number such as 0 opens a local webcam")
        if saved.get("camera"):
            self.cam.setEditText(saved["camera"])
        shared.camera_combo = self.cam
        grid.addWidget(cam_title, r, 0, 1, 3)
        grid.addWidget(self.cam, r + 1, 0, 1, 3)
        refresh = QtWidgets.QPushButton("Refresh COM ports")
        refresh.clicked.connect(self.fill_ports)
        grid.addWidget(refresh, r + 2, 0, 1, 3)
        grid.setRowStretch(r + 3, 1)
        self.fill_ports(first=True)

    def fill_ports(self, first=False):
        ports = list_serial_ports()
        for key, (combo, _, _, _, default) in self.rows.items():
            keep = self.saved.get(key) if first else combo.currentText()
            combo.clear()
            if default:
                combo.addItem(default)
            for dev, desc in ports:
                combo.addItem(f"{dev}  ({desc})" if desc else dev)
            if keep:
                combo.setEditText(keep)
            elif not default and ports:
                combo.setCurrentIndex(0)

    def targets(self):
        return {k: row[0].currentText().strip() for k, row in self.rows.items()}

    def _toggle(self, key):
        link = self.shared.links[key]
        combo = self.rows[key][0]
        if link.state in ("open", "connecting"):
            link.close_link()
        else:
            link.open_link(combo.currentText())

    def _on_state(self, key, state, text):
        _, btn, dot, detail, _ = self.rows[key]
        dot.setStyleSheet(f"color:{STATE_COLOUR[state]}; font-size:18px;")
        btn.setText("Disconnect" if state == "open" else "Cancel" if state == "connecting" else "Connect")
        detail.setText({"closed": "not connected", "connecting": text or "connecting ...",
                        "open": f"connected ({text})", "error": text}.get(state, text))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("T-Minus_6 hardware triage")
        self.settings = load_settings()
        self.shared = Shared()
        self.shared.log = self.log
        links = self.shared.links

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        outer = QtWidgets.QVBoxLayout(central)

        # ---- top bar: mode toggle in the middle, STOP ALL on the right
        bar = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("T-Minus_6 triage")
        f = title.font()
        f.setPointSize(15)
        f.setBold(True)
        title.setFont(f)
        bar.addWidget(title)
        bar.addStretch(1)
        self.btn_case = QtWidgets.QPushButton("CASE MODE")
        self.btn_func = QtWidgets.QPushButton("FUNC MODE")
        group = QtWidgets.QButtonGroup(self)
        group.setExclusive(True)
        for b, radius in ((self.btn_case, "border-top-left-radius:6px; border-bottom-left-radius:6px;"),
                          (self.btn_func, "border-top-right-radius:6px; border-bottom-right-radius:6px;")):
            b.setCheckable(True)
            b.setMinimumHeight(38)
            b.setMinimumWidth(150)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                "QPushButton{background:#f2f3f5; color:#333; border:1px solid #b8bec9; font-weight:bold;"
                f"padding:6px 20px; {radius}}} QPushButton:checked{{background:#2f6feb; color:white;}}")
            group.addButton(b)
            bar.addWidget(b)
        bar.addStretch(1)
        self.estop = QtWidgets.QPushButton("STOP ALL")
        self.estop.setMinimumHeight(38)
        self.estop.setStyleSheet("background:#b3261e; color:white; font-weight:bold; padding:6px 18px;")
        self.estop.setToolTip("Stop wheels, release stepper, disarm tower, stop the running test")
        bar.addWidget(self.estop)
        outer.addLayout(bar)

        # ---- body: connections | mode pages, then log
        self.case = CaseMode(self.shared)
        self.func = FuncMode(self.shared)
        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(self.case)
        self.stack.addWidget(self.func)
        self.conn = ConnectionsPanel(self.shared, self.settings)
        body = QtWidgets.QHBoxLayout()
        body.addWidget(self.conn)
        body.addWidget(self.stack, 1)
        top = QtWidgets.QWidget()
        top.setLayout(body)

        self.logbox = QtWidgets.QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setMaximumBlockCount(1500)
        self.logbox.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        logw = QtWidgets.QWidget()
        ll = QtWidgets.QVBoxLayout(logw)
        ll.setContentsMargins(0, 0, 0, 0)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Log"))
        self.hide_s = QtWidgets.QCheckBox("hide robot scan lines (S,...)")
        self.hide_s.setChecked(True)
        clear = QtWidgets.QPushButton("Clear")
        clear.clicked.connect(self.logbox.clear)
        row.addWidget(self.hide_s)
        row.addStretch(1)
        row.addWidget(clear)
        ll.addLayout(row)
        ll.addWidget(self.logbox)

        split = QtWidgets.QSplitter(Qt.Vertical)
        split.addWidget(top)
        split.addWidget(logw)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 1)
        outer.addWidget(split, 1)

        for key, link in links.items():
            link.line_received.connect(lambda text, k=key: self._rx(k, text))
            link.tx.connect(lambda text, k=key: self.log(f"{k} -> {text}"))
            link.state_changed.connect(
                lambda state, detail, k=key: state in ("open", "error", "closed") and
                self.log(f"{k}: {state} {detail}".rstrip()))

        self.btn_case.clicked.connect(lambda: self.set_mode(0))
        self.btn_func.clicked.connect(lambda: self.set_mode(1))
        self.estop.clicked.connect(self.stop_all)
        self.set_mode(self.settings.get("mode", 0))

    def set_mode(self, index):
        if index != 1:
            self.func.deactivate()      # no wheels moving from a hidden tab
        self.stack.setCurrentIndex(index)
        (self.btn_func if index == 1 else self.btn_case).setChecked(True)

    def log(self, text):
        self.logbox.appendPlainText(f"{time.strftime('%H:%M:%S')}  {text}")

    def _rx(self, key, text):
        if self.hide_s.isChecked() and re.match(r"^S,", text):
            return
        self.log(f"{key} <- {text}")

    def stop_all(self):
        self.case.stop_run()
        self.func.stop_all()
        links = self.shared.links
        if links["robot"].is_open:
            for _ in range(3):
                links["robot"].send("D,0,0,0", quiet=True)
        if links["tower"].is_open:
            links["tower"].send("X")
        if links["bench"].is_open:
            links["bench"].send("ALLOFF")
        self.log("STOP ALL")

    def closeEvent(self, e):
        self.stop_all()
        save_settings({"mode": self.stack.currentIndex(), "targets": self.conn.targets(),
                       "camera": self.shared.camera_url()})
        for link in self.shared.links.values():
            link.close_link()
        super().closeEvent(e)


def apply_light(app):
    app.setStyle("Fusion")
    app.setPalette(app.style().standardPalette())


def main():
    QtWidgets.QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QtWidgets.QApplication(sys.argv)
    apply_light(app)
    win = MainWindow()
    win.resize(1320, 860)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
