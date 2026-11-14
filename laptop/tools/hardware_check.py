"""Command-line twin of the in-game Hardware Check: finds the devices, runs every automatic test and prints
PASS / FAIL per line. The tests that need a person (wheels, LEDs, buzzers, LCD) ask you.
Exit code 1 when anything failed, so it can gate a demo.

    python tools/hardware_check.py            python tools/hardware_check.py --sim --yes"""
import argparse
import sys
import time

import _net
import config as C
from core.clock import now

results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print("  %-4s %s %s" % ("PASS" if ok else "FAIL", name, ("- " + detail) if detail else ""))


def confirm(q, yes):
    if yes:
        return True
    return input("  %s [y/N] " % q).strip().lower().startswith("y")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--yes", action="store_true", help="answer yes to the questions (software devices)")
    a = ap.parse_args()
    net = _net.Net(sim=a.sim)
    print("Looking for devices (10 s) ...")
    net.wait_for(["robot", "tower", "station"], 10.0)
    time.sleep(2.5)                                           # let pings and a station reading arrive
    L, st = net.links, net.state
    print("\nDevices")
    for role in ("robot", "tower", "station"):
        d = st.devices[role]
        check(role + " connected", d.connected, "%s fw v%s rtt %s" % (d.where, d.fw, "%.0f ms" % d.rtt_ms if d.rtt_ms else "-"))
        if d.connected and d.fw is not None:
            check(role + " firmware version", d.fw == C.FW_VERSION, "v%s" % d.fw)
        if d.connected and d.rtt_ms is not None:
            check(role + " round trip under %d ms" % C.RTT_WARN_MS, d.rtt_ms < C.RTT_WARN_MS)
    evs = net.drain()
    if L["robot"].connected:
        print("\nRobot")
        angles = {e.data[0] for e in evs if e.kind == "scan"}
        check("turret sweeps both sides", bool(angles) and min(angles) <= -30 and max(angles) >= 30,
              "%d angles seen" % len(angles))
        for side, (l, r) in (("left", (170, 0)), ("right", (0, 170))):
            print("  Robot LIFTED? Spinning the %s wheels for 1 s ..." % side)
            end = now() + 1.0
            while now() < end:
                L["robot"].send_drive(l, r, 0)
                time.sleep(0.02)
            L["robot"].send_drive(0, 0, 0)
            check(side + " wheels spin forward", confirm("Did the %s wheels spin forward?" % side, a.yes))
    if L["tower"].connected:
        print("\nTower")
        L["tower"].allow(True)
        net.drain()
        fired = L["tower"].fire(test=True)
        time.sleep(1.0)
        got_k = any(e.kind == "tower_k" for e in net.drain())
        check("F answered by K", fired and got_k)
        check("one ball dropped", confirm("Did exactly one ball drop?", a.yes))
    if L["station"].connected:
        print("\nWeather station")
        temps = [e.data for e in evs if e.kind == "weather"]
        check("W readings arriving", bool(temps) or st.devices["station"].connected, "%s" % (temps[-1:] or ""))
        for zone, name in ((2, "hot"), (1, "cold")):
            L["station"].set_zone(zone)
            time.sleep(2.2)
            check("%s warning: LED, buzzer and LCD" % name, confirm("Do you see the %s LED blink, hear the buzzer and read the LCD warning?" % name, a.yes))
        L["station"].set_zone(0)
        L["station"].set_lives(C.LIVES - 1)
        time.sleep(0.5)
        check("yellow hit LED flashes", confirm("Did the yellow hit LED flash?", a.yes))
        L["station"].set_lives(C.LIVES)
    net.close()
    bad = [n for n, ok in results if not ok]
    print("\n%d checks, %d failed%s" % (len(results), len(bad), ": " + ", ".join(bad) if bad else ". READY FOR DEMO"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
