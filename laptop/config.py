"""Settings. Change these after running gamepad_test.py and measuring the robot."""
# Gamepad (numbers differ between Windows, Mac and Linux: run gamepad_test.py)
AXIS_TURN = 0          # left stick left/right
AXIS_SPEED = 1         # left stick up/down (up is negative)
BTN_AUTOPILOT = 3      # Y
BTN_CAMERA = 1         # B
BTN_RESTART = 7        # Start
DEAD_ZONE = 0.08

# Links
WEATHER_PORT = "COM4"              # the UNO R3 USB port (Linux/Mac: /dev/ttyACM0)
WEATHER_BAUD = 115200
ROBOT_ADDR = ("192.168.1.50", 5005)   # UNO Q #1, set after it joins the hotspot
TOWER_ADDR = ("192.168.1.51", 5005)   # UNO Q #2

# Robot motion (measure these, see docs: calibration)
MAX_PWM = 255          # the firmware also has its own speed cap
TURN_GAIN = 0.6        # k in left = v + k*w, right = v - k*w
LIVES = 15
