"""Hot / cold warnings from three sources: the station's DHT11, the optional robot DHT11 and the game zones.
The most severe state wins (HOT over COLD over NORMAL). Also spike detection, trend and the 60 s history."""
import collections
import config as C

NORMAL, COLD, HOT = 0, 1, 2
NAMES = ("NORMAL", "COLD", "HOT")


class Hysteresis:
    """Sensor state with 1 C of hysteresis, the same rule the station firmware uses."""

    def __init__(self):
        self.state = NORMAL

    def update(self, temp):
        if self.state == NORMAL:
            if temp > C.HOT_C:
                self.state = HOT
            elif temp < C.COLD_C:
                self.state = COLD
        elif self.state == HOT and temp < C.HOT_C - C.HYST_C:
            self.state = NORMAL
        elif self.state == COLD and temp > C.COLD_C + C.HYST_C:
            self.state = NORMAL
        return self.state


class WeatherModel:
    def __init__(self):
        self.reset()

    def reset(self):
        self.temp = self.hum = None          # station air
        self.robot_temp = self.robot_hum = None
        self.station_hyst, self.robot_hyst = Hysteresis(), Hysteresis()
        self.station_state = NORMAL          # what the station itself reports (already includes our zone)
        self.zone = NORMAL                   # from the craft's position on the ring
        self.forced = None                   # demo keys H / K / N
        self.state = NORMAL
        self.history = collections.deque()   # (t, temp) for 60 s
        self.spike_until = -1.0
        self.spike_armed = True
        self.trend = "steady"
        self.last_reading_t = None

    # ---- inputs
    def on_station(self, temp, hum, state, t):
        self.temp, self.hum, self.station_state, self.last_reading_t = temp, hum, state, t
        self.station_hyst.update(temp)
        self.history.append((t, temp))

    def on_robot_air(self, temp, hum, t):
        self.robot_temp, self.robot_hum = temp, hum
        self.robot_hyst.update(temp)

    def station_lost(self):
        self.temp = self.hum = self.last_reading_t = None
        self.station_hyst = Hysteresis()
        self.station_state = NORMAL

    def set_zone(self, zone):
        self.zone = zone

    def game_zone(self):
        """What the laptop tells the station with Z: the forced demo zone, else the craft's zone, else the robot's
        own air sensor (so the station also warns when the robot's DHT11 says hot or cold)."""
        if self.forced is not None:
            return self.forced
        return max(self.zone, self.robot_hyst.state if self.robot_temp is not None else NORMAL)

    # ---- once a frame
    def update(self, t):
        """Returns a list of events: ("state", old, new) and ("spike", delta)."""
        events = []
        while self.history and t - self.history[0][0] > 60.0:
            self.history.popleft()
        sensor = self.station_hyst.state if self.temp is not None else NORMAL
        new = max(sensor, self.game_zone())
        if new != self.state:
            events.append(("state", self.state, new))
            self.state = new
        recent = [v for (ts, v) in self.history if t - ts <= C.SPIKE_WINDOW_S]
        delta = (max(recent) - min(recent)) if len(recent) >= 2 else 0.0
        if delta >= C.SPIKE_C:
            if self.spike_armed:
                self.spike_armed = False
                self.spike_until = t + 5.0
                events.append(("spike", delta))
        else:
            self.spike_armed = True
        if t < self.spike_until:
            self.trend = "spike"
        elif len(recent) >= 2 and recent[-1] - recent[0] > 0.5:
            self.trend = "rising"
        elif len(recent) >= 2 and recent[-1] - recent[0] < -0.5:
            self.trend = "falling"
        else:
            self.trend = "steady"
        return events

    def spike_active(self, t):
        return t < self.spike_until

    def name(self):
        return NAMES[self.state]
