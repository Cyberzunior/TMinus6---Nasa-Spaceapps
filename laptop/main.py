"""Starter: gamepad -> one movement model -> robot. The game, auto-pilot, camera and tower go on top of this."""
import pygame
import config as C
from model import dead_zone, wheel_mix
from robot_link import UdpLink

pygame.init()
pygame.joystick.init()
if pygame.joystick.get_count() == 0:
    raise SystemExit("No gamepad. Pair it first and run gamepad_test.py")
pad = pygame.joystick.Joystick(0)
pad.init()
robot = UdpLink(C.ROBOT_ADDR)
autopilot, lives = False, C.LIVES
clock = pygame.time.Clock()

while True:
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            raise SystemExit
        if e.type == pygame.JOYBUTTONDOWN and e.button == C.BTN_AUTOPILOT:
            autopilot = not autopilot
            print("autopilot", autopilot)
    speed = -dead_zone(pad.get_axis(C.AXIS_SPEED))      # up on the stick = forward
    turn = dead_zone(pad.get_axis(C.AXIS_TURN))
    left, right = wheel_mix(speed, turn)
    robot.send(f"D,{left},{right},{int(autopilot)}")    # 50 times a second
    for line in robot.recv_lines():
        pass                                            # S,... scan and B,... bumper lines go to the auto-pilot
    clock.tick(50)
