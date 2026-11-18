"""The director turns a scene's narration (with exact sentence timings) into a shot plan:
set, character blocking, gesture cues, camera moves, prop/chart cues and the transition in.

Choices come from the words being spoken, so motion lands on the right line, and are varied with a
seeded RNG so consecutive scenes and sentences don't repeat the same movement.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from ..models import Scene
from .easing import ease_in_out, lerp, Noise
from .rig import Pose
from .sets import LAYOUTS, STAGE_H, STAGE_W

# Gesture library: arm/hand targets plus facial hints. Idle motion is layered on top at runtime.
GESTURES: dict[str, Pose] = {
    "idle": Pose(l_sh=10, l_el=12, r_sh=10, r_el=12),
    "explain": Pose(l_sh=34, l_el=68, r_sh=34, r_el=68, l_hand="open", r_hand="open", brow=0.25),
    "explain_r": Pose(l_sh=10, l_el=14, r_sh=48, r_el=58, r_hand="open", brow=0.2),
    "explain_l": Pose(l_sh=48, l_el=58, r_sh=12, r_el=16, l_hand="open", brow=0.2),
    "present": Pose(l_sh=22, l_el=40, r_sh=78, r_el=18, r_hand="open", look_x=0.9, head=4, brow=0.35),
    "point": Pose(l_sh=10, l_el=14, r_sh=96, r_el=6, r_hand="point", look_x=1.0, head=5, brow=0.3),
    "point_up": Pose(l_sh=10, l_el=14, r_sh=30, r_el=128, r_hand="point", brow=0.8, smile=0.7),
    "hmm": Pose(l_sh=24, l_el=96, r_sh=26, r_el=142, r_hand="point", look_x=0.5, look_y=-0.8, head=-6,
                brow=0.5, smile=0.0),
    "shrug": Pose(l_sh=30, l_el=96, r_sh=30, r_el=96, l_hand="open", r_hand="open", head=7, brow=1.0, smile=0.1),
    "count": Pose(l_sh=24, l_el=96, r_sh=40, r_el=108, r_hand="point", l_hand="open", brow=0.3),
    "cheer": Pose(l_sh=148, l_el=16, r_sh=148, r_el=16, smile=1.0, brow=0.7),
    "thumbs": Pose(l_sh=10, l_el=14, r_sh=36, r_el=104, r_hand="thumb", smile=1.0, brow=0.4),
    "worry": Pose(l_sh=22, l_el=102, r_sh=22, r_el=102, worry=1.0, smile=-0.5, look_y=0.4),
    "welcome": Pose(l_sh=40, l_el=30, r_sh=40, r_el=30, l_hand="open", r_hand="open", smile=0.9, brow=0.5),
}

KEYWORDS = [  # (regex, gesture) checked in order
    (r"\?", "shrug"),
    (r"\b(first|second|third|one|two|three|step|steps)\b", "count"),
    (r"\b(grow|grows|growth|win|free|gain|wealth|rich|more|bigger|doubles?)\b", "present"),
    (r"\b(catch|mistake|risk|debt|lose|losing|cost|costs|fee|fees|wait|late|danger|trap)\b", "worry"),
    (r"\b(secret|idea|here's|imagine|remember|key|trick)\b", "point_up"),
    (r"(\$|\d|%|percent|dollars?)", "point"),
    (r"\b(start|today|now|do it|great|good news)\b", "thumbs"),
]
ROTATION = ["explain", "explain_r", "idle", "explain_l", "explain", "present"]

TRANSITIONS = ["push", "iris", "fade", "push", "wipe"]

FINANCE_SET_HINTS = [
    (r"\b(home|house|rent|mortgage|budget|kitchen|family|takeout|lunch)\b", "home"),
    (r"\b(fed|inflation|economy|recession|market|wall street|jobs|city)\b", "city"),
    (r"\b(bank|savings account|loan|credit|interest rate|deposit)\b", "bank"),
]


@dataclass
class Cue:
    t: float
    gesture: str


@dataclass
class ActorPlan:
    name: str
    x: float                 # stage x where the actor stands
    scale: float
    speaking: bool
    cues: list[Cue]
    enter: str = "none"      # walk_in | hop_in | none
    enter_from: float = -300.0
    seed: int = 0
    emphasis: list[tuple[float, float]] = field(default_factory=list)
    questions: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class CamKey:
    t: float
    cx: float
    cy: float
    zoom: float


@dataclass
class ScenePlan:
    set: str
    transition: str
    actors: list[ActorPlan]
    camera: list[CamKey]
    punches: list[float]
    chart_start: float | None
    chart_dur: float
    icon_start: float | None
    notes: list[tuple[str, float]]
    fx: list[tuple[str, float]]
    duration: float
    seed: int

    def cam(self, t: float, noise: Noise) -> tuple[float, float, float]:
        keys = self.camera
        if t <= keys[0].t:
            k = keys[0]
            cx, cy, z = k.cx, k.cy, k.zoom
        else:
            cx, cy, z = keys[-1].cx, keys[-1].cy, keys[-1].zoom
            for a, b in zip(keys, keys[1:]):
                if a.t <= t <= b.t:
                    e = ease_in_out((t - a.t) / max(1e-6, b.t - a.t))
                    cx, cy, z = lerp(a.cx, b.cx, e), lerp(a.cy, b.cy, e), lerp(a.zoom, b.zoom, e)
                    break
        for tp in self.punches:  # quick, soft punch-in on emphasized lines
            d = t - tp
            if 0 <= d < 0.9:
                z *= 1 + 0.045 * (d / 0.18 if d < 0.18 else max(0.0, 1 - (d - 0.18) / 0.72) ** 2)
        cx += noise(t) * 4  # barely-there handheld drift keeps frames alive
        cy += noise(t + 50) * 3
        return cx, cy, z


def _gesture_for(text: str, prev: str, rng: random.Random, i: int) -> str:
    low = text.lower()
    for pat, g in KEYWORDS:
        if re.search(pat, low) and g != prev:
            return g
    options = [g for g in ROTATION if g != prev]
    return options[(i + rng.randint(0, 2)) % len(options)]


def choose_set(scene: Scene, index: int, prev: list[str]) -> str:
    if scene.set:
        return scene.set
    if scene.chart.kind != "none":
        cand = "board"
    else:
        cand = None
        text = (scene.heading + " " + scene.narration).lower()
        for pat, name in FINANCE_SET_HINTS:
            if re.search(pat, text):
                cand = name
                break
        cand = cand or ["studio", "home", "studio", "bank", "city"][index % 5]
    if len(prev) >= 2 and prev[-1] == prev[-2] == cand:  # avoid three in a row
        cand = "studio" if cand != "studio" else "home"
    return cand


def _sentence_cue(sentences, words: set[str]) -> float | None:
    for s in sentences:
        if words & set(re.findall(r"[a-z0-9$%]+", s.text.lower())):
            return s.start
    return None


def plan_scene(scene: Scene, sentences, duration: float, index: int, prev_sets: list[str],
               first: bool, fps: int = 24) -> ScenePlan:
    rng = random.Random(index * 7919 + 17)
    set_name = choose_set(scene, index, prev_sets)
    L = LAYOUTS[set_name]
    has_chart = scene.chart.kind != "none"
    duo = scene.character == "duo"
    lead = "penny" if scene.character == "penny" else "max"

    # --- blocking
    max_scale = 0.84
    actors: list[ActorPlan] = []
    main_x = 520 if not duo else 420
    cues, prev_g = [], "idle"
    first_g = "welcome" if first else None
    for i, s in enumerate(sentences):
        g = first_g if (i == 0 and first_g) else _gesture_for(s.text, prev_g, rng, i + index)
        if has_chart and i > 0 and g in ("explain", "explain_r", "explain_l", "idle") and rng.random() < 0.5:
            g = "present"
        cues.append(Cue(s.start, g))
        prev_g = g
    emph = [(s.start, s.end) for s in sentences if s.emphasis]
    ques = [(s.start, s.end) for s in sentences if s.question]
    enter = scene.entrance or ("walk_in" if first or (index % 4 == 2 and not has_chart) else "none")
    actors.append(ActorPlan(lead, main_x, max_scale if lead == "max" else 1.0, True,
                            cues or [Cue(0, "idle")], enter, -350, seed=index, emphasis=emph, questions=ques))
    if duo:
        pc = []
        for c in cues:  # Penny reacts rather than mirrors: cheer on good news, worry on bad, else idle
            pc.append(Cue(c.t + 0.25, {"present": "cheer", "thumbs": "thumbs", "worry": "worry",
                                        "shrug": "shrug", "point_up": "hmm"}.get(c.gesture, "idle")))
        actors.append(ActorPlan("penny", main_x + 400, 0.9, False, pc,
                                "hop_in" if index % 2 else "walk_in", STAGE_W + 300, seed=index + 100))

    # --- content cues
    chart_start = icon_start = None
    if has_chart:
        num_cue = next((s.start for s in sentences if re.search(r"[\d$%]|percent|dollars", s.text.lower())), None)
        chart_start = max(0.5, num_cue if num_cue is not None else duration * 0.2)
    else:
        icon_start = 0.35 if not first else 1.8
    chart_dur = min(4.5, max(2.0, duration * 0.45))
    notes = []
    for k, point in enumerate(scene.key_points[:3]):
        words = {w for w in re.findall(r"[a-z0-9$%]+", point.lower()) if len(w) > 3}
        t0 = _sentence_cue(sentences, words)
        notes.append((point, (t0 if t0 is not None else duration * (0.25 + 0.2 * k)) + 0.2))
    fx = []
    text = scene.narration.lower()
    if scene.money_fx == "coins" or (scene.money_fx is None and re.search(r"\b(save|saves|saving|sets aside|coins?|piggy)\b", text)):
        fx.append(("coins", (_sentence_cue(sentences, {"save", "saves", "saving", "aside", "coins", "coin"}) or 1.0) + 0.3))
    if scene.money_fx == "bills" or (scene.money_fx is None and re.search(r"\b(invest|invests|spend|spending|pay|paid|fees?)\b", text)):
        fx.append(("bills", (_sentence_cue(sentences, {"invest", "invests", "spend", "pay", "fee", "fees"}) or 1.2) + 0.2))

    # --- camera
    bx0, by0, bx1, by1 = L.board
    board_c = ((bx0 + bx1) / 2, (by0 + by1) / 2)
    char_c = (main_x + (150 if duo else 0), L.floor_y - 520)
    wide = CamKey(0, STAGE_W / 2, STAGE_H / 2, 0.9)
    style = rng.choice(["push", "reveal", "pan"]) if not first else "push"
    keys = []
    if style == "reveal":  # open close on the character, pull out to reveal the content
        keys = [CamKey(0, char_c[0] + 120, char_c[1] + 40, 1.32), CamKey(min(2.6, duration * 0.3), wide.cx, wide.cy, 0.92)]
    elif style == "pan":
        keys = [CamKey(0, STAGE_W / 2 - 90, STAGE_H / 2, 0.97), CamKey(duration * 0.5, STAGE_W / 2 + 60, STAGE_H / 2, 1.0)]
    else:
        keys = [wide, CamKey(duration * 0.6, STAGE_W / 2 + 20, STAGE_H / 2 - 10, 0.98)]
    if chart_start is not None:  # move in on the chart while it draws, so numbers are readable
        t0 = max(keys[-1].t + 0.2, chart_start - 0.2)
        keys.append(CamKey(t0, keys[-1].cx, keys[-1].cy, keys[-1].zoom))
        keys.append(CamKey(t0 + 1.3, board_c[0] - 230, board_c[1] + 60, 1.04))
    keys.append(CamKey(max(keys[-1].t + 0.5, duration), keys[-1].cx + 15, keys[-1].cy, keys[-1].zoom * 1.035))
    keys.sort(key=lambda k: k.t)
    punches = [s for s, _ in emph]

    transition = scene.transition or ("fade" if first else TRANSITIONS[index % len(TRANSITIONS)])
    return ScenePlan(set_name, transition, actors, keys, punches, chart_start, chart_dur, icon_start, notes, fx,
                     duration, index)

