"""Line protocol v2: ASCII text lines, comma separated, at most 64 characters, one line per UDP datagram.
The same lines travel over UDP, USB serial and the UNO Q Bridge. decode() returns a typed tuple or None
(unknown or malformed lines are ignored, never raised)."""
MAX_LEN = 64
FW = 2

# kind -> field types (i int, f float, s text)
_SPEC = {
    "HELLO": "sis", "I": "si", "WHO?": "", "I?": "",
    "P": "ii", "Q": "ii",
    "D": "iii", "X": "", "R": "",
    "S": "iii", "B": "s", "T": "ff",
    "F": "", "A": "i", "K": "", "C": "iii",
    "W": "fii", "Z": "i", "V": "f", "H": "i", "G": "",
}


def encode(*parts):
    line = ",".join(str(p) for p in parts)
    if len(line) > MAX_LEN:
        raise ValueError("line longer than %d characters: %r" % (MAX_LEN, line))
    return line


def decode(line):
    if isinstance(line, bytes):
        line = line.decode("ascii", "ignore")
    line = line.strip()
    if not line or len(line) > MAX_LEN:
        return None
    parts = line.split(",")
    kind, fields = parts[0], parts[1:]
    if kind == "T" and len(fields) == 3:          # T,rest,push,ms to the tower; T,temp,hum from the robot
        kind = "TUNE"
        types = "iii"
    else:
        types = _SPEC.get(kind)
    if types is None or len(fields) != len(types):
        return None
    out = [kind]
    try:
        for f, t in zip(fields, types):
            out.append(int(f) if t == "i" else float(f) if t == "f" else f)
    except ValueError:
        return None
    return tuple(out)


def split_datagram(data):
    """A datagram or a serial chunk may hold several lines."""
    if isinstance(data, bytes):
        data = data.decode("ascii", "ignore")
    return [l for l in data.replace("\r", "").split("\n") if l.strip()]
