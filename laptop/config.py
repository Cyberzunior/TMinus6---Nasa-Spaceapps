"""T-Minus_6 settings. Committed defaults live here; personal overrides (Wi-Fi, camera URL, calibration)
go in config.local.json next to this file (git-ignored). Every number in the game is a value in this file.

Use:  import config as C ; C.V_MAX          Change + save:  C.save_local(V_MAX=14.2)"""
import json
import os

# ---- Gamepad (numbers differ by OS and driver: run tools/gamepad_test.py and fix them here or in config.local.json)
AXIS_TURN = 0            # left stick left/right
AXIS_SPEED = 1           # left stick up/down (up is negative)
AXIS_BRAKE = 4           # left trigger  (-1 released .. 1 pressed), -1 = not used
AXIS_BOOST = 5           # right trigger
BTN_CONFIRM = 0          # A
BTN_CAMERA = 1           # B
BTN_FIRE = 2             # X (practice mode only)
BTN_AUTOPILOT = 3        # Y
BTN_BACK = 6             # Back / View: Hardware Check
BTN_RESTART = 7          # Start: pause, restart, hold 2 s to re-sync
DEAD_ZONE = 0.08
EXPO = 0.25              # stick response curve: 0 = linear, 1 = cubic
TRIGGER_BASE = 1.0       # speed scale with no trigger pressed; boost raises it to 1.0, brake lowers it to 0.5
INPUT_HZ = 120           # gamepad / mixer thread rate
RUMBLE = True

# ---- Movement model (measure with tools/calibrate_robot.py)
V_MAX = 15.0             # cm/s at full stick
W_MAX = 90.0             # deg/s at full turn
TURN_GAIN = 0.6          # K in left = speed + K*turn, right = speed - K*turn
MAX_PWM = 255
SEND_HZ = 50             # D lines per second
CMD_EPS = 0.03           # send at once when speed or turn moved more than this
SYNC_DELAY_MS = 0        # delay the screen craft so it matches the robot's real motion (0 = instant)
DRIFT_CORRECTION = 0.5   # 0..1: how hard a bumper contact pulls the robot ghost onto the debris it hit

# ---- Board (cm). Earth at the centre; angles: 0 = right, 90 = bottom (player side), clockwise on screen
BOARD_W = 120.0
BOARD_H = 80.0
EARTH_R = 7.5
ORBIT_R = 28.0           # the spec's 40 cm ring does not fit an 80 cm board; raise this on a bigger board
ORBIT_DIR = 1            # 1 = clockwise seen from above, -1 = counter-clockwise
START_ANGLE = 270.0
CRAFT_R = 5.0
SCENARIO_FILE = "scenario.json"

# ---- Links and discovery
UDP_PORT = 5005
ROBOT_ADDR = None        # "192.168.43.50" or "ip:port": skips discovery
TOWER_ADDR = None
WEATHER_PORT = None      # "COM4": skips the serial scan
CAMERA_URL = None        # "http://<ip>:81/stream" (ESP32-CAM) or the phone app's URL
WIFI_SSID = ""           # only documentation for the team; put the real ones in config.local.json
WIFI_PASSWORD = ""
PING_MS = 500
LINK_TIMEOUT_S = 2.0
RTT_WARN_MS = 80.0
LOSS_WARN = 0.05
FW_VERSION = 2
SERIAL_BAUD = 115200
SERIAL_SCAN_S = 3.0
SIM_ROBOT_DELAY_MS = 40
SIM_TOWER_K_MS = 120

# ---- Robot sensors on the map
USE_ROBOT_SCAN = True    # turn S,angle,cm readings into hazards
SCAN_SIGN = 1            # -1 if the turret's positive angle is to the left
SENSOR_FWD = 6.0         # ultrasonic sensor distance ahead of the robot centre, cm
SCAN_MAX_CM = 100.0
DETECT_TTL_S = 3.0       # a detected object is forgotten this long after the last echo

# ---- Lives and hits
LIVES = 15
SHIELD_S = 1.5

# ---- Asteroids and the tower
ASTEROID_R = 1.5
ASTEROID_SPEED = 25.0    # cm/s: the paper ball's measured speed
ASTEROID_WARN_S = 1.0
ASTEROID_GAP_S = 6.0     # minimum time between asteroids
ASTEROID_GAP_JITTER_S = 4.0
ASTEROID_K_TIMEOUT_S = 0.25
LANE_WIDTH = 16.0        # an asteroid can only hit while it is this close (total width) to the orbit ring
TOWER_HAS_PAN = True
TOWER_MIN_FIRE_GAP_S = 2.0
TOWER_REST_DEG = 20
TOWER_PUSH_DEG = 100
TOWER_PUSH_MS = 350
AIM_CENTER_DEG = 90.0    # pan servo angle that points the ramp at Earth
AIM_GAIN = 1.0           # servo degrees per degree of bearing (-1 flips the direction)
AIM_TABLE = []           # optional [[bearing_deg, servo_deg], ...] from calibration; overrides the two numbers above

# ---- Weather
HOT_C = 30.0
COLD_C = 18.0
HYST_C = 1.0
HOT_ZONE = [135.0, 225.0]    # sunlit arc of the ring, degrees
COLD_ZONE = [315.0, 45.0]    # Earth's shadow arc
COLD_LED_COLOR = "blue"      # the station has a separate blue LED for cold (an early note said red)
SPIKE_C = 3.0
SPIKE_WINDOW_S = 10.0
ZONE_KEEPALIVE_S = 2.0
WEATHER_LOG_S = 5.0
WEATHER_TURN_PENALTY = 0.2   # turn rate lost in a hot or cold zone (0 = off)

# ---- Auto-pilot
AP_CRUISE = 0.8
AP_NUDGE = 0.3
AP_WARN_CM = 40.0
AP_DANGER_CM = 25.0
AP_WARN_SPEED = 0.7
AP_DANGER_SPEED = 0.4
AP_SAFE_CM = 3.0
AP_HORIZON_S = 3.0
AP_CLEAR_S = 1.0

# ---- Screen, sound, misc
RENDER_W = 1920
RENDER_H = 1080
FULLSCREEN = False
WINDOW_W = 1600
WINDOW_H = 900
VSYNC = True
POSTFX = 2               # 0 off, 1 light, 2 full
MASTER_VOLUME = 0.7
DEMO_MODE = False
BEST_TIME = 0.0          # best seconds survived, saved by the game
RESTART_TO_PLAY = False  # after game over, Start goes straight back to PLAY
PRIVACY_NO_SAVE_FRAMES = True
LOG_KEEP = 20
# Demo mode script: [seconds, action]. Actions: "asteroid", "hot", "cold", "normal"
DEMO_SCRIPT = [[8, "asteroid"], [20, "hot"], [28, "normal"], [34, "asteroid"], [46, "cold"], [54, "normal"],
               [60, "asteroid"]]

# ----------------------------------------------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_FILE = os.path.join(HERE, "config.local.json")
MESSAGES = []            # problems found while loading, shown at start instead of a traceback
_DEFAULTS = {k: v for k, v in dict(globals()).items() if k.isupper() and k not in ("HERE", "LOCAL_FILE", "MESSAGES")}


def _ok(key, value):
    default = _DEFAULTS[key]
    if default is None:
        return value is None or isinstance(value, (str, int))
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, type(default))


def load_local(path=None):
    """Overlay config.local.json on the defaults. Bad or unknown entries are skipped with a clear message."""
    path = path or LOCAL_FILE
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("the file must hold one JSON object")
    except (OSError, ValueError) as e:
        MESSAGES.append("config.local.json could not be read (%s). Using the defaults." % e)
        return {}
    used = {}
    for key, value in data.items():
        if key.startswith("_"):
            continue
        if key not in _DEFAULTS:
            MESSAGES.append("config.local.json: unknown setting %r ignored." % key)
        elif not _ok(key, value):
            MESSAGES.append("config.local.json: %s = %r has the wrong type, default %r kept." % (key, value, _DEFAULTS[key]))
        else:
            globals()[key] = used[key] = value
    return used


def save_local(path=None, **values):
    """Change settings now and remember them in config.local.json."""
    path = path or LOCAL_FILE
    data = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    if not isinstance(data, dict):
        data = {}
    for key, value in values.items():
        if key in _DEFAULTS and _ok(key, value):
            globals()[key] = data[key] = value
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except OSError as e:
        MESSAGES.append("could not write config.local.json (%s)" % e)
        return False


def reset_defaults():
    globals().update(_DEFAULTS)


load_local()
