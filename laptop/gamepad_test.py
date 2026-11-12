"""Run this first. Pair the gamepad over Bluetooth, run the script, press every button
and move the sticks. It prints the numbers you need for config.py."""
import pygame

pygame.init()
pygame.joystick.init()
if pygame.joystick.get_count() == 0:
    raise SystemExit("No gamepad found. Pair it in the Bluetooth settings first.")
pad = pygame.joystick.Joystick(0)
pad.init()
print("Gamepad:", pad.get_name(), "| axes:", pad.get_numaxes(), "| buttons:", pad.get_numbuttons())
clock = pygame.time.Clock()
while True:
    for e in pygame.event.get():
        if e.type == pygame.JOYBUTTONDOWN:
            print("button", e.button)
        elif e.type == pygame.JOYAXISMOTION and abs(e.value) > 0.5:
            print("axis", e.axis, round(e.value, 2))
        elif e.type == pygame.QUIT:
            raise SystemExit
    clock.tick(60)
