"""Easing curves, springs and smooth noise for natural motion."""
from __future__ import annotations

import math
import random


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def progress(t: float, start: float, dur: float) -> float:
    return clamp((t - start) / dur) if dur > 0 else float(t >= start)


def ease_in_out(t: float) -> float:
    t = clamp(t)
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out(t: float) -> float:
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in(t: float) -> float:
    t = clamp(t)
    return t * t * t


def ease_out_back(t: float, s: float = 1.70158) -> float:
    t = clamp(t)
    return 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2


def spring(t: float, freq: float = 2.2, damping: float = 5.0) -> float:
    """0 -> 1 with a natural damped overshoot."""
    if t <= 0:
        return 0.0
    return 1 - math.exp(-damping * t) * math.cos(2 * math.pi * freq * t)


class Noise:
    """Smooth 1-D value noise in [-1, 1] (cosine-interpolated random lattice)."""

    def __init__(self, seed: int, rate: float = 0.6):
        rng = random.Random(seed)
        self.v = [rng.uniform(-1, 1) for _ in range(512)]
        self.rate = rate

    def __call__(self, t: float) -> float:
        x = t * self.rate
        i = int(math.floor(x))
        f = x - i
        a, b = self.v[i % 512], self.v[(i + 1) % 512]
        w = (1 - math.cos(f * math.pi)) / 2
        return a + (b - a) * w
