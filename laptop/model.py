"""Shared movement model: one speed and one turn drive the game craft AND the robot."""
from config import DEAD_ZONE, TURN_GAIN, MAX_PWM


def dead_zone(x):
    return 0.0 if abs(x) < DEAD_ZONE else x


def wheel_mix(speed, turn):
    """speed, turn in -1..1  ->  (left, right) in -MAX_PWM..MAX_PWM"""
    left = speed + TURN_GAIN * turn
    right = speed - TURN_GAIN * turn
    m = max(1.0, abs(left), abs(right))        # keep the ratio if one side would overflow
    return int(MAX_PWM * left / m), int(MAX_PWM * right / m)
