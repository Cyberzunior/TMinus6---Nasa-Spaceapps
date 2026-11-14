"""Keyboard drive when no gamepad is paired: W A S D or the arrow keys. Returns (speed, turn)."""
import pygame


def read_keys():
    k = pygame.key.get_pressed()
    speed = (1.0 if (k[pygame.K_UP] or k[pygame.K_w]) else 0.0) - (1.0 if (k[pygame.K_DOWN] or k[pygame.K_s]) else 0.0)
    turn = (1.0 if (k[pygame.K_RIGHT] or k[pygame.K_d]) else 0.0) - (1.0 if (k[pygame.K_LEFT] or k[pygame.K_a]) else 0.0)
    return speed, turn
