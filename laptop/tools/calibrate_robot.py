"""Measure the robot once so the screen and the table match. Writes V_MAX, W_MAX (and K) to config.local.json.

  1. Forward: the robot drives for the time the game expects to cover 50 cm. You measure the real distance.
  2. Turn: the robot spins for the time the game expects to cover 360 degrees. You type the degrees it really turned.
Robot on the table with 60 cm of clear space, a tape measure at hand, hand on the power switch.

    python tools/calibrate_robot.py            python tools/calibrate_robot.py --sim"""
import argparse
import sys
import time

import _net
import config as C
from core import calibration as cal


def ask(prompt):
    while True:
        try:
            return float(input(prompt).strip())
        except ValueError:
            print("  type a number, for example 47.5")


def drive(net, left, right, seconds):
    end = time.time() + seconds
    while time.time() < end:
        net.links["robot"].send_drive(left, right, 0)
        time.sleep(0.02)
    net.links["robot"].send_drive(0, 0, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true")
    a = ap.parse_args()
    net = _net.Net(sim=a.sim)
    print("Looking for the robot ...")
    if not net.wait_for(["robot"], 12.0):
        print("Robot not found. Power it on, join the same hotspot, or set ROBOT_ADDR in config.local.json.")
        net.close()
        return 1
    new = {}
    input("\nStep 1: put the robot on a start line. Press Enter to drive forward. ")
    secs = 50.0 / (0.5 * C.V_MAX)
    drive(net, int(0.5 * C.MAX_PWM), int(0.5 * C.MAX_PWM), secs)
    new["V_MAX"] = cal.scale_after_test(C.V_MAX, 50.0, ask("How many cm did it drive (the game expected 50)? "))
    input("\nStep 2: Press Enter to spin on the spot. ")
    k = int(C.TURN_GAIN * C.MAX_PWM)
    drive(net, k, -k, 360.0 / C.W_MAX)
    new["W_MAX"] = cal.scale_after_test(C.W_MAX, 360.0, ask("How many degrees did it turn (the game expected 360)? "))
    print("\nNew values:", new)
    if input("Save to config.local.json? [Y/n] ").strip().lower() in ("", "y", "yes"):
        cal.save(**new)
        print("Saved.")
    net.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
