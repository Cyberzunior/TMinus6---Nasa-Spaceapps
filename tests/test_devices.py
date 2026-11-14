"""Discovery, links, simulated devices and the safety rules, over real loopback sockets."""
import threading
import time
import config as C
from core.clock import now
from core.events import Bus
from core.state import SharedState
from devio import protocol as P
from devio.links import RobotLink, StationLink, TowerLink
from devio.sim_devices import FakeSerial, SimRobot, SimStation, SimTower
import _net


def wait(cond, timeout=6.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_all_devices_found_within_10_seconds_without_typing_an_address():
    net = _net.Net(sim=True)
    try:
        t0 = time.time()
        assert net.wait_for(["robot", "tower", "station"], 10.0)
        assert time.time() - t0 < 10.0
        assert wait(lambda: net.state.devices["robot"].rtt_ms is not None and net.state.devices["tower"].rtt_ms is not None)
        assert net.state.devices["robot"].fw == 2 and net.state.devices["tower"].color() == "green"
    finally:
        net.close()


def test_rtt_and_loss_are_measured():
    net = _net.Net(sim=True)
    try:
        net.wait_for(["robot"], 8.0)
        time.sleep(2.5)
        d = net.state.devices["robot"]
        assert d.rtt_ms is not None and 0 < d.rtt_ms < 150 and d.loss == 0.0
    finally:
        net.close()


def test_robot_failsafe_stops_within_300_ms_and_game_over_latches():
    net = _net.Net(sim=True)
    try:
        net.wait_for(["robot"], 8.0)
        robot, sim = net.links["robot"], net.sims[0]
        for _ in range(25):
            robot.send_drive(255, 255, 0)
            time.sleep(0.02)
        assert sim.pose.x > 0.5                              # it drives while commands arrive
        x = sim.pose.x
        time.sleep(0.45)                                     # commands stop: the 300 ms timeout
        x1 = sim.pose.x
        time.sleep(0.4)
        assert abs(sim.pose.x - x1) < 0.01 and x1 - x < 15 * 0.5   # at most ~0.3 s of travel, then still
        robot.latch(True)
        assert wait(lambda: sim.latched and robot.latch_confirmed, 2.0)
        assert robot.send_drive(100, 100, 0) is False        # the laptop does not even send while latched
        robot.latch(False)
        assert wait(lambda: not sim.latched, 2.0)
    finally:
        net.close()


def test_robot_front_stop_blocks_forward_even_with_autopilot_off():
    net = _net.Net(sim=True)
    try:
        net.wait_for(["robot"], 8.0)
        robot, sim = net.links["robot"], net.sims[0]
        sim.pose.x, sim.pose.y, sim.pose.theta = 50.0, 0.0, 0.0     # facing the right border, 10 cm away
        for _ in range(100):
            robot.send_drive(255, 255, 0)
            time.sleep(0.02)
        assert sim.pose.x < 60.0 - C.CRAFT_R + 0.01                  # never through the border
        assert sim.front_cm < 8.5
        back = sim.pose.x
        robot.send_drive(-255, -255, 0)
        time.sleep(0.2)
        assert sim.pose.x <= back + 0.001                            # reverse still works
    finally:
        net.close()


def test_tower_fire_safety_rules():
    net = _net.Net(sim=True)
    try:
        net.wait_for(["tower"], 8.0)
        t, sim = net.links["tower"], net.sims[1]
        assert not t.fire()                                  # not allowed outside PLAY / practice
        t.allow(True)
        net.drain()
        assert t.fire() and wait(lambda: any(e.kind == "tower_k" for e in net.drain()), 2.0)
        assert not t.fire()                                  # 2 s since the previous F
        assert sim.balls == 1
        t.last_fire = now() - 3.0
        t.set_armed(False)
        assert not t.fire() and sim.balls == 1               # disarmed: no F, even allowed
        time.sleep(0.2)
        assert sim.armed is False
        t.set_armed(True)
        assert wait(lambda: sim.armed, 1.0)
        t.allow(False)                                       # game over: never
        assert not t.fire()
        assert not t.fire(test=False)
    finally:
        net.close()


def test_sim_tower_answers_k_and_ignores_double_f():
    net = _net.Net(sim=True)
    try:
        net.wait_for(["tower"], 8.0)
        sim = net.sims[1]
        tr = net.links["tower"].best()
        net.drain()
        tr.send("F")
        tr.send("F")
        time.sleep(0.5)
        assert sim.balls == 1
        assert sum(1 for e in net.drain() if e.kind == "tower_k") == 1
    finally:
        net.close()


def test_station_unplug_and_replug_without_restarting():
    net = _net.Net(sim=True)
    try:
        net.wait_for(["station"], 8.0)
        st = net.links["station"]
        assert wait(lambda: st.connected)
        net.sim_station.port.closed = True                  # pull the USB cable
        assert wait(lambda: not st.connected, 2.0)
        assert net.state.devices["station"].color() == "red"
        new = SimStation()
        new.start()
        net.scanner.add_sim("SIM-NEW", new.port, "station")  # plug it back in
        assert wait(lambda: st.connected, 3.0)
        assert wait(lambda: net.state.devices["station"].connected)
        new.stop()
    finally:
        net.close()


def test_robot_power_off_and_back_on_reconnects_within_5_seconds():
    net = _net.Net(sim=True)
    try:
        net.wait_for(["robot"], 8.0)
        r = net.links["robot"]
        net.sims[0].stop()                                   # the robot loses power
        assert wait(lambda: not r.connected, 4.0)
        assert net.state.devices["robot"].color() == "red"
        new = SimRobot(net.hub.port)                         # it comes back (new socket, same hub)
        new.start()
        net.sims.append(new)
        t0 = time.time()
        assert wait(lambda: r.connected, 5.0) and time.time() - t0 < 5.0
    finally:
        net.close()


def test_station_virtual_logic_matches_the_firmware_rules():
    s = SimStation()
    s._line("Z,2")
    assert s.state == 2 and s.lcd() == ("!! HOT ZONE !!", "MOVE AWAY NOW!")
    s._line("Z,1")
    assert s.state == 1 and s.lcd() == ("!! COLD ZONE !!", "MOVE AWAY NOW!")
    s._line("Z,0")
    assert s.state == 0 and s.lcd()[1] == "H 40%"
    s.set_air(31.0)
    s._update()
    assert s.state == 2
    s.set_air(29.5)
    s._update()
    assert s.state == 2                                      # hysteresis
    s.set_air(28.9)
    s._update()
    assert s.state == 0
    s._line("H,14")
    assert s.hit_until > now()
    s._line("G")
    assert s.lcd() == ("SIGNAL LOST", "GAME OVER")
    s._line("R")
    assert s.lives == 15 and not s.over
    out = []
    s.port.feed_from_device = lambda line: out.append(line)
    s._line("I?")
    assert out == ["I,weather,2"]


def test_state_colors_green_yellow_red():
    from core.state import DeviceStatus
    d = DeviceStatus("robot")
    assert d.color() == "red"
    d.connected = True
    assert d.color() == "green"
    d.rtt_ms = 120.0
    assert d.color() == "yellow"
    d.rtt_ms, d.loss = 20.0, 0.1
    assert d.color() == "yellow"
    d.loss, d.fw = 0.0, 1
    assert d.color() == "yellow" and "mismatch" in d.problem()


def test_resync_resends_lives_zone_and_latch_on_reconnect():
    st, bus = SharedState(), Bus()
    sent = []
    link = StationLink(st, bus, lambda m: None)
    link.attach("X", lambda line: sent.append(line))
    link.lives, link.over = 11, False
    link.resync()
    assert "R" in sent and "H,11" in sent
    sent.clear()
    link.over = True
    link.resync()
    assert sent == ["G"]
    rl = RobotLink(st, bus, lambda m: None)
    rl.attach("Y", lambda line: sent.append(line))
    rl.latched = True
    sent.clear()
    rl.resync()
    assert sent == ["X"]
