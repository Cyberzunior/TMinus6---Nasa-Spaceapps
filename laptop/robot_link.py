"""Sends text lines to the robot or the tower. Wi-Fi (UDP) by default; use serial for the USB-C fallback."""
import socket


class UdpLink:
    def __init__(self, addr):
        self.addr = addr
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)

    def send(self, line):
        self.sock.sendto((line + "\n").encode(), self.addr)

    def recv_lines(self):
        out = []
        try:
            while True:
                data, _ = self.sock.recvfrom(256)
                out += data.decode(errors="ignore").splitlines()
        except BlockingIOError:
            pass
        return out


class SerialLink:
    def __init__(self, port, baud=115200):
        import serial
        self.ser = serial.Serial(port, baud, timeout=0)
        self.buf = b""

    def send(self, line):
        self.ser.write((line + "\n").encode())

    def recv_lines(self):
        self.buf += self.ser.read(256)
        *lines, self.buf = self.buf.split(b"\n")
        return [l.decode(errors="ignore").strip() for l in lines if l.strip()]
