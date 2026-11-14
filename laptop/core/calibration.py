"""Turns tape-measure numbers into the model constants, and bearings into pan-servo angles."""
import config as C


def v_max_from(distance_cm, seconds, stick=1.0):
    """Robot drove distance_cm in `seconds` at this stick value -> cm/s at full stick."""
    if seconds <= 0 or stick <= 0 or distance_cm <= 0:
        raise ValueError("distance, time and stick must be above zero")
    return distance_cm / seconds / stick


def w_max_from(degrees, seconds, turn=1.0):
    """Robot turned `degrees` on the spot in `seconds` at this turn value -> deg/s at full turn."""
    if seconds <= 0 or turn <= 0 or degrees <= 0:
        raise ValueError("angle, time and turn must be above zero")
    return degrees / seconds / turn


def retune_turn(w_measured, k_now, w_target=90.0):
    """Pick a new mixing gain K so a full turn gives about w_target deg/s. Returns (K, expected W_MAX).
    Turn rate is proportional to K, and K is kept between 0.2 and 1."""
    k = max(0.2, min(1.0, k_now * w_target / w_measured))
    return round(k, 3), round(w_measured * k / k_now, 1)


def sync_delay_from(one_way_ms):
    """Delay for the screen craft so it lines up with the robot (0 below 15 ms: not worth it)."""
    return 0 if one_way_ms is None or one_way_ms < 15 else int(round(one_way_ms))


def aim_servo(bearing):
    """Pan servo angle (0..180) that sends the ball `bearing` degrees off the tower-to-Earth line."""
    table = sorted((float(b), float(s)) for b, s in C.AIM_TABLE) if C.AIM_TABLE else None
    if table and len(table) >= 2:
        if bearing <= table[0][0]:
            (b0, s0), (b1, s1) = table[0], table[1]
        elif bearing >= table[-1][0]:
            (b0, s0), (b1, s1) = table[-2], table[-1]
        else:
            i = next(i for i in range(1, len(table)) if bearing <= table[i][0])
            (b0, s0), (b1, s1) = table[i - 1], table[i]
        servo = s0 + (s1 - s0) * (bearing - b0) / ((b1 - b0) or 1.0)
    else:
        servo = C.AIM_CENTER_DEG + C.AIM_GAIN * bearing
    return int(round(max(0.0, min(180.0, servo))))


def save(**values):
    return C.save_local(**values)


def scale_after_test(old, commanded, measured):
    """A test commanded `commanded` (cm or degrees) at the current constant `old`; the tape says `measured`.
    The robot moved measured/commanded as far as the model thought, so the constant is scaled by that ratio."""
    if commanded <= 0 or measured <= 0 or old <= 0:
        raise ValueError("numbers must be above zero")
    return round(old * measured / commanded, 2)
