"""Subtitle cue timing plus SRT (for YouTube captions) and ASS (burned-in, styled) writers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Cue:
    start: float
    end: float
    text: str


def chunk_text(text: str, max_words: int) -> list[str]:
    """Split narration into readable caption chunks, preferring sentence/comma boundaries."""
    chunks: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        words = sentence.split()
        while words:
            if len(words) <= max_words:
                chunks.append(" ".join(words))
                break
            cut = max_words
            for i in range(max_words, max(2, max_words // 2) - 1, -1):  # break after a comma if possible
                if words[i - 1].endswith(","):
                    cut = i
                    break
            chunks.append(" ".join(words[:cut]))
            words = words[cut:]
    return [c for c in chunks if c]


def scene_cues(text: str, start: float, speech_dur: float, max_words: int) -> list[Cue]:
    chunks = chunk_text(text, max_words)
    total = sum(len(c) for c in chunks) or 1
    t, cues = start, []
    for c in chunks:
        d = speech_dur * len(c) / total
        cues.append(Cue(t, t + d, c))
        t += d
    return cues


def _ts_srt(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _ts_ass(t: float) -> str:
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def write_srt(cues: list[Cue], path: Path) -> Path:
    lines = []
    for i, c in enumerate(cues, 1):
        lines += [str(i), f"{_ts_srt(c.start)} --> {_ts_srt(c.end)}", c.text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_ass(cues: list[Cue], path: Path, w: int, h: int, portrait: bool, margin_v: int | None = None,
              theme: str = "cartoon") -> Path:
    size = 76 if portrait else 62
    if margin_v is None:
        margin_v = int(h * 0.355) if portrait else 40  # Shorts: between chart and character, above the UI overlay
    style = (f"Style: Default,Patrick Hand,{size},&H00FFFFFF,&H000000FF,&H402E2226,&H402E2226,0,0,0,0,100,100,2,0,3,10,0,"
             f"2,80,80,{margin_v},1")
    if theme == "editorial":  # documentary lower captions: Inter Bold, white on a soft ink box
        size = 62 if portrait else 50
        style = (f"Style: Default,Inter,{size},&H00FFFFFF,&H000000FF,&H301D1816,&H301D1816,-1,0,0,0,100,100,0.5,0,3,"
                 f"14,0,2,90,90,{margin_v},1")
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    body = []
    for c in cues:
        text = c.text.replace("{", "(").replace("}", ")").replace("\n", " ")
        body.append(f"Dialogue: 0,{_ts_ass(c.start)},{_ts_ass(c.end)},Default,,0,0,0,,{{\\fad(80,60)}}{text}")
    path.write_text(header + "\n".join(body) + "\n", encoding="utf-8")
    return path
