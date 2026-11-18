"""Per-frame character motion: gesture blending, idle life, lip sync, blinks, walking and reactions."""
from __future__ import annotations

import math
import random

import numpy as np

from .director import GESTURES, ActorPlan
from .easing import Noise, clamp, ease_in_out, ease_out
from .rig import Pose

BLEND = 0.42       # seconds to move between gestures
WALK_SPEED = 520.0  # stage px per second


class Actor:
    def __init__(self, plan: ActorPlan, envelope: np.ndarray | None, fps: int):
        self.p, self.env, self.fps = plan, envelope, fps
        s = plan.seed
        self.n = [Noise(s * 13 + k, rate) for k, rate in enumerate([0.35, 0.5, 0.8, 0.6, 0.7, 2.6, 0.25])]
        rng = random.Random(s + 5)
        self.blinks, t = [], rng.uniform(0.8, 2.0)
        while t < 600:
            self.blinks.append(t)
            t += rng.uniform(2.2, 5.2) if rng.random() > 0.15 else 0.3  # occasional double blink
        dist = abs(plan.x - plan.enter_from)
        self.walk_dur = dist / WALK_SPEED if plan.enter == "walk_in" else (0.8 if plan.enter == "hop_in" else 0.0)

    # -- helpers ----------------------------------------------------------------------------
    def loud(self, t: float) -> float:
        if self.env is None or not len(self.env):
            return 0.0
        i = int(t * self.fps)
        return float(self.env[i]) if 0 <= i < len(self.env) else 0.0

    def _gesture_pose(self, t: float) -> Pose:
        cues = self.p.cues
        if t < cues[0].t:
            return GESTURES["idle"]
        idx = max(i for i, c in enumerate(cues) if c.t <= t)
        prev = GESTURES[cues[idx - 1].gesture] if idx > 0 else GESTURES["idle"]
        cur = GESTURES[cues[idx].gesture]
        return prev.blend(cur, ease_in_out((t - cues[idx].t) / BLEND))

    def _blink(self, t: float) -> float:
        for b in self.blinks:
            d = t - b
            if 0 <= d < 0.16:
                return 1 - abs(d - 0.08) / 0.08
            if b > t:
                break
        return 0.0

    # -- main -----------------------------------------------------------------------------------
    def state(self, t: float) -> tuple[Pose, float, float]:
        """Returns (pose, stage_x, extra_y) at time t."""
        n = self.n
        p = self._gesture_pose(t)
        pose = Pose(**{k: getattr(p, k) for k in p.__dataclass_fields__})

        # idle life: breathing, weight shift, small arm drift so nothing is ever frozen
        breath = math.sin(t * 2 * math.pi / 3.8)
        pose.bob += breath * 2.0
        pose.torso += n[0](t) * 1.6
        pose.head += n[1](t) * 2.6
        pose.l_sh += n[2](t) * 3.5
        pose.r_sh += n[3](t + 9) * 3.5
        pose.l_el += n[3](t) * 5
        pose.r_el += n[4](t) * 5

        x, extra_y = self.p.x, 0.0
        if self.p.speaking:
            a = self.loud(t)
            pose.mouth = clamp(a * 1.15)
            pose.mouth_w = n[5](t)
            pose.head += a * 2.5 * math.sin(t * 8.5)          # talking nods follow the voice
            pose.r_el += a * 7 * math.sin(t * 5.3)            # beat gestures on stressed syllables
            pose.l_el += a * 5 * math.sin(t * 4.7 + 1)
            for s, e in self.p.emphasis:
                if s <= t <= e:
                    pose.brow = max(pose.brow, 0.8)
            for s, e in self.p.questions:
                if s <= t <= e:
                    pose.brow = max(pose.brow, 0.9)
                    pose.head += 5 * ease_out((t - s) / 0.4)
        else:
            pose.mouth = 0.0
            pose.smile = max(pose.smile, 0.45)
            pose.look_x = -0.8  # listening: looks toward the speaker
            pose.head += 2 * math.sin(t * 1.3)

        pose.look_x += n[6](t) * 0.25
        pose.blink = max(pose.blink, self._blink(t))

        # entrances
        if self.p.enter == "walk_in" and t < self.walk_dur + 0.35:
            direction = 1 if self.p.x > self.p.enter_from else -1
            if t < self.walk_dur:
                frac = t / self.walk_dur
                x = self.p.enter_from + (self.p.x - self.p.enter_from) * (1 - (1 - frac) ** 1.6)
                ph = t * 2 * math.pi * 1.9
                pose.l_hip, pose.r_hip = 20 * math.sin(ph), -20 * math.sin(ph)
                pose.l_knee = max(0.0, 40 * math.sin(ph + math.pi / 2))
                pose.r_knee = max(0.0, -40 * math.sin(ph + math.pi / 2))
                pose.l_sh, pose.r_sh = 14 - 16 * math.sin(ph), 14 + 16 * math.sin(ph)
                pose.l_el, pose.r_el = 18, 18
                pose.l_hand = pose.r_hand = "rest"
                pose.bob = -abs(math.sin(ph)) * 10
                pose.torso += 4 * direction
                pose.look_x = direction * 0.6
                pose.mouth *= 0.6
            else:
                settle = ease_out((t - self.walk_dur) / 0.35)
                pose.l_hip, pose.r_hip = -3 * settle, 3 * settle
        elif self.p.enter == "hop_in" and t < self.walk_dur:
            frac = t / self.walk_dur
            x = self.p.enter_from + (self.p.x - self.p.enter_from) * ease_out(frac)
            extra_y = -abs(math.sin(frac * math.pi * 3)) * 70 * (1 - frac)
            pose.l_sh = pose.r_sh = 120
            pose.smile = 1.0
        return pose, x, extra_y


def envelope(audio: np.ndarray, sr: int, fps: int) -> np.ndarray:
    """Per-frame mouth-open amount from narration: RMS with fast attack / slower release."""
    hop = sr // fps
    n = int(math.ceil(len(audio) / hop))
    rms = np.array([np.sqrt(np.mean(audio[i * hop:(i + 1) * hop] ** 2)) if i * hop < len(audio) else 0.0
                    for i in range(n)], dtype=np.float32)
    ref = np.percentile(rms[rms > 1e-4], 90) if np.any(rms > 1e-4) else 1.0
    raw = np.clip(rms / (ref or 1.0), 0, 1)
    out = np.zeros_like(raw)
    v = 0.0
    for i, r in enumerate(raw):
        v = v + (r - v) * (0.75 if r > v else 0.35)
        out[i] = v if v > 0.08 else 0.0
    return out
