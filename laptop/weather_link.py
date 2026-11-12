"""USB serial link to the weather station (UNO R3). Lines: W,temp,hum,state  (state 0 normal, 1 cold, 2 hot)."""
import serial


class WeatherLink:
    def __init__(self, port, baud=115200):
        self.ser = serial.Serial(port, baud, timeout=0)
        self.buf = b""
        self.temp, self.hum, self.state = None, None, 0

    def poll(self):
        self.buf += self.ser.read(256)
        *lines, self.buf = self.buf.split(b"\n")
        for l in lines:
            p = l.decode(errors="ignore").strip().split(",")
            if len(p) == 4 and p[0] == "W":
                try:
                    self.temp, self.hum, self.state = float(p[1]), int(p[2]), int(p[3])
                except ValueError:
                    pass

    def send(self, line):
        self.ser.write((line + "\n").encode())

    def set_lives(self, n): self.send(f"H,{n}")
    def game_over(self): self.send("G")
    def reset(self): self.send("R")
    def virtual_temp(self, c): self.send(f"V,{c:.1f}")
