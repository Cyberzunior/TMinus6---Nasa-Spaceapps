import json
import os
import tempfile
import config as C
from devio import protocol as P


def test_decode_every_message():
    assert P.decode("D,255,-255,1") == ("D", 255, -255, 1)
    assert P.decode("S,-45,120,0") == ("S", -45, 120, 0)
    assert P.decode("B,L") == ("B", "L")
    assert P.decode("W,23.4,41,2") == ("W", 23.4, 41, 2)
    assert P.decode("Z,1") == ("Z", 1) and P.decode("H,14") == ("H", 14) and P.decode("V,31.5") == ("V", 31.5)
    assert P.decode("F") == ("F",) and P.decode("K") == ("K",) and P.decode("X") == ("X",) and P.decode("R") == ("R",)
    assert P.decode("A,120") == ("A", 120)
    assert P.decode("P,5,123456789") == ("P", 5, 123456789) and P.decode("Q,5,123") == ("Q", 5, 123)
    assert P.decode("HELLO,robot,2,192.168.1.50") == ("HELLO", "robot", 2, "192.168.1.50")
    assert P.decode("I,weather,2") == ("I", "weather", 2) and P.decode("I?") == ("I?",) and P.decode("WHO?") == ("WHO?",)
    assert P.decode("T,20,100,350") == ("TUNE", 20, 100, 350)       # tower tuning
    assert P.decode("T,23.5,40") == ("T", 23.5, 40.0)                # robot air sensor
    assert P.decode(b"G\r\n") == ("G",)


def test_decode_ignores_garbage_never_raises():
    for bad in ("", "   ", "nonsense", "D,1,2", "D,a,b,c", "S,1", "W,x,y,z", "Z", ",,,,", "D," + "9" * 80, "\x00\xff"):
        assert P.decode(bad) is None


def test_encode_limits_length():
    assert P.encode("D", 1, -2, 0) == "D,1,-2,0"
    try:
        P.encode("HELLO", "x" * 70)
        assert False
    except ValueError:
        pass


def test_split_datagram():
    assert P.split_datagram(b"D,1,2,0\nX\r\n\n") == ["D,1,2,0", "X"]


def test_config_defaults_sane():
    assert C.LIVES == 15 and C.SHIELD_S == 1.5 and C.HOT_C == 30 and C.COLD_C == 18 and C.UDP_PORT == 5005
    assert C.AP_WARN_CM == 40 and C.AP_DANGER_CM == 25 and C.DEAD_ZONE == 0.08 and C.SEND_HZ == 50


def test_config_bad_file_gives_messages_not_tracebacks():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "c.json")
    try:
        C.MESSAGES.clear()
        open(p, "w").write("{ not json")
        assert C.load_local(p) == {} and C.MESSAGES and "could not be read" in C.MESSAGES[-1]
        open(p, "w").write(json.dumps({"V_MAX": "fast", "NOPE": 1, "W_MAX": 77.0, "_help": "x"}))
        C.MESSAGES.clear()
        used = C.load_local(p)
        assert used == {"W_MAX": 77.0} and C.W_MAX == 77.0 and C.V_MAX == 15.0
        assert any("wrong type" in m for m in C.MESSAGES) and any("unknown" in m for m in C.MESSAGES)
    finally:
        C.reset_defaults()
        C.MESSAGES.clear()


def test_config_save_roundtrip():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "c.json")
    try:
        assert C.save_local(path=p, V_MAX=12.5, SYNC_DELAY_MS=40, BOGUS=1, HOT_C="hot")
        data = json.load(open(p))
        assert data == {"V_MAX": 12.5, "SYNC_DELAY_MS": 40} and C.V_MAX == 12.5
        C.reset_defaults()
        C.load_local(p)
        assert C.V_MAX == 12.5
    finally:
        C.reset_defaults()
