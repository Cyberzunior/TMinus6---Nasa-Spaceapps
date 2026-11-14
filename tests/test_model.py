import math
import config as C
from core import calibration as cal
from core.model import Pose, angdiff, in_arc, mix, predict_pose, shape_axis, start_pose, step_pose


def test_dead_zone_and_curve():
    assert shape_axis(0.05) == 0.0 and shape_axis(-0.079) == 0.0
    assert shape_axis(1.0) == 1.0 and shape_axis(-1.0) == -1.0
    assert 0 < shape_axis(0.2) < 0.2                     # expo flattens the centre
    assert shape_axis(0.5) > 0 > shape_axis(-0.5)


def test_mix_straight_and_tank_turn():
    s, t, l, r = mix(1.0, 0.0)
    assert (l, r) == (255, 255)
    s, t, l, r = mix(0.0, 1.0)
    assert l == -r and l > 0                              # turn on the spot
    assert mix(-0.5, 0.0)[2:] == (-128, -128)


def test_mix_scales_speed_and_turn_together():
    """If a wheel would overflow, the craft must slow exactly like the robot does."""
    s, t, l, r = mix(1.0, 1.0)
    assert max(abs(l), abs(r)) <= 255
    assert abs(s - 1.0 / (1 + C.TURN_GAIN)) < 1e-9 and abs(t - s) < 1e-9


def test_same_numbers_both_bodies():
    """The robot's wheel command and the craft's motion come from one mix() call: unmixing the wheels gives the craft numbers."""
    for sp, tu in ((0.3, 0.7), (-0.8, 0.2), (1.0, -1.0), (0.0, 0.5)):
        s, t, l, r = mix(sp, tu)
        s2 = (l + r) / 2 / C.MAX_PWM
        t2 = (l - r) / 2 / C.MAX_PWM / C.TURN_GAIN
        assert abs(s - s2) < 0.01 and abs(t - t2) < 0.02


def test_step_pose_straight_and_turn():
    p = Pose(0, 0, 0)
    step_pose(p, 1.0, 0.0, 2.0)
    assert abs(p.x - 2 * C.V_MAX) < 1e-9 and abs(p.y) < 1e-9
    p = Pose(0, 0, 0)
    step_pose(p, 0.0, 1.0, 1.0)
    assert abs(p.theta - C.W_MAX) < 1e-9 and p.x == 0


def test_predict_does_not_move_the_pose():
    p = Pose(10, 5, 30)
    q = predict_pose(p, 1.0, 0.2, 2.0)
    assert (p.x, p.y, p.theta) == (10, 5, 30) and (q.x, q.y) != (10, 5)


def test_angles_and_arcs():
    assert angdiff(350, 10) == -20 and angdiff(10, 350) == 20
    assert in_arc(0, (315, 45)) and in_arc(350, (315, 45)) and not in_arc(90, (315, 45))
    assert in_arc(180, (135, 225)) and not in_arc(270, (135, 225))


def test_start_pose_on_the_ring_heading_along_it():
    p = start_pose()
    assert abs(p.radius() - C.ORBIT_R) < 1e-9
    step_pose(p, 1.0, 0.0, 0.5)
    assert abs(p.radius() - C.ORBIT_R) < 1.5            # first move follows the ring (tangent)


def test_calibration_numbers():
    assert cal.scale_after_test(15.0, 50.0, 40.0) == 12.0
    assert cal.scale_after_test(90.0, 360.0, 330.0) == 82.5
    assert cal.sync_delay_from(8) == 0 and cal.sync_delay_from(40) == 40 and cal.sync_delay_from(None) == 0
    k, w = cal.retune_turn(60.0, 0.6, 90.0)
    assert k > 0.6 and 80 < w <= 90.5
    try:
        cal.scale_after_test(15.0, 50.0, 0.0)
        assert False
    except ValueError:
        pass


def test_aim_servo_maps_bearing_to_angle():
    old = C.AIM_TABLE
    try:
        C.AIM_TABLE = []
        assert cal.aim_servo(0) == int(C.AIM_CENTER_DEG) and cal.aim_servo(1000) == 180 and cal.aim_servo(-1000) == 0
        C.AIM_TABLE = [[-30, 50], [0, 90], [30, 140]]
        assert cal.aim_servo(0) == 90 and cal.aim_servo(15) == 115 and cal.aim_servo(-30) == 50
    finally:
        C.AIM_TABLE = old
