"""Shared by the command-line tools: starts discovery and the links without the game window."""
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import config as C  # noqa: E402
from core.events import Bus  # noqa: E402
from core.state import SharedState  # noqa: E402
from devio.discovery import SerialScanner, UdpHub  # noqa: E402
from devio.links import RobotLink, StationLink, TowerLink, link_thread  # noqa: E402


class Net:
    def __init__(self, sim=False, log=None, hub_port=None):
        self.log = log or (lambda m: None)
        self.state, self.bus = SharedState(), Bus()
        self.links = {"robot": RobotLink(self.state, self.bus, self.log), "tower": TowerLink(self.state, self.bus, self.log),
                      "station": StationLink(self.state, self.bus, self.log)}
        self.hub = UdpHub(self.links, self.log, port=hub_port)
        self.scanner = SerialScanner(self.links, self.log, C.WEATHER_PORT, enabled=not sim)
        self.stop = threading.Event()
        self.sims = []
        if sim:
            from devio.sim_devices import SimRobot, SimStation, SimTower
            s = SimStation()
            self.sims = [SimRobot(self.hub.port), SimTower(self.hub.port), s]
            self.scanner.add_sim("SIM-STATION", s.port, "station")
            self.sim_station = s
        for fn in (self.hub.run, self.scanner.run, lambda: link_thread(list(self.links.values()), self.stop, self.state)):
            threading.Thread(target=fn, daemon=True).start()
        for s in self.sims:
            s.start()

    def wait_for(self, roles, timeout=10.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if all(self.links[r].connected for r in roles):
                return True
            time.sleep(0.1)
        return False

    def drain(self):
        return self.bus.drain(100000)

    def close(self):
        for r in ("robot",):
            self.links[r].send("D,0,0,0")
        self.stop.set()
        self.hub.close()
        self.scanner.close()
        for s in self.sims:
            s.stop()
