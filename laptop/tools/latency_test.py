"""Round-trip latency to the robot and the tower: 500 pings, then min / median / 95th percentile / max and the loss.
One way is half of the round trip. Target: median under 100 ms, loss under 2 percent.

    python tools/latency_test.py            real devices (found by discovery)
    python tools/latency_test.py --sim      against the software devices
    python tools/latency_test.py --count 200 --only robot"""
import argparse
import statistics
import sys
import time

import _net
from core.clock import now_us
from devio import protocol as P


def run(net, role, count, gap=0.02):
    link = net.links[role]
    tr = link.best()
    if tr is None:
        return None
    got = {}
    sent = 0
    orig = link.on_line

    def spy(name, line):
        m = P.decode(line)
        if m and m[0] == "Q" and m[1] >= 900000:
            got[m[1]] = (now_us() - m[2]) / 1000.0
        else:
            orig(name, line)
    link.on_line = spy
    try:
        for i in range(count):
            seq = 900000 + i
            tr.send(P.encode("P", seq, now_us()))
            sent += 1
            time.sleep(gap)
        time.sleep(0.6)
    finally:
        link.on_line = orig
    return sorted(got.values()), sent


def report(role, res, count):
    if res is None:
        print("%-6s not connected" % role)
        return False
    rtts, sent = res
    loss = 100.0 * (sent - len(rtts)) / max(1, sent)
    if not rtts:
        print("%-6s no replies, loss 100%%" % role)
        return False
    p95 = rtts[min(len(rtts) - 1, int(len(rtts) * 0.95))]
    med = statistics.median(rtts)
    ok = med / 2 < 100 and loss < 2
    print("%-6s %d pings | round trip ms: min %.1f  median %.1f  p95 %.1f  max %.1f | one way ~ %.1f ms | loss %.1f %%  %s"
          % (role, sent, rtts[0], med, p95, rtts[-1], med / 2, loss, "PASS" if ok else "FAIL"))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--count", type=int, default=500)
    ap.add_argument("--only", choices=("robot", "tower"))
    a = ap.parse_args()
    net = _net.Net(sim=a.sim)
    roles = [a.only] if a.only else ["robot", "tower"]
    print("looking for %s ..." % ", ".join(roles))
    net.wait_for(roles, 12.0)
    ok = True
    for r in roles:
        ok &= report(r, run(net, r, a.count), a.count)
    net.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
