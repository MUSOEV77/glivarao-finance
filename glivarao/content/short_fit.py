"""Keep Shorts at 30-55 seconds, never over 59 (see daily_v2.fit_short_voice).

1. Before voicing, the script is trimmed to SHORT_MAX_WORDS (120) words: whole sentences are removed from the
   middle scenes (the hook in the first scene and the closing scene are kept), longest scenes first.
2. It is voiced BEFORE rendering and the real audio length is measured with ffprobe; over SHORT_REDO_SECONDS (55 s)
   the script is trimmed in proportion and voiced again (at most 2 times).
3. Still over SHORT_TEMPO_SECONDS (58 s): sped up with ffmpeg atempo, at most SHORT_MAX_TEMPO (1.15x).
4. Still over SHORT_MAX_SECONDS (59 s): not rendered, held, and you get an alert. The finished file is measured
   again after rendering and a Short over 59 s is never sent to Telegram.
"""
from __future__ import annotations

import re

SENT = re.compile(r"(?<=[.!?])\s+")


def _words(text: str) -> int:
    return len(text.replace("*", "").split())


def trim_to_words(script, max_words: int, keep_min_scenes: int = 3):
    """Remove whole sentences (never the hook or the closing scene) until the narration fits max_words."""
    scenes = [s.model_copy() for s in script.scenes]
    total = sum(_words(s.narration) for s in scenes)
    if total <= max_words:
        return script
    while total > max_words:
        middle = [i for i in range(1, len(scenes) - 1) if scenes[i].narration.strip()]
        if not middle:  # only hook + close left: trim the close's extra sentences, then the hook's
            middle = [i for i in (len(scenes) - 1, 0) if len(SENT.split(scenes[i].narration.strip())) > 1]
            if not middle:
                break
        i = max(middle, key=lambda k: _words(scenes[k].narration))
        sents = SENT.split(scenes[i].narration.strip())
        drop = sents.pop()  # the last sentence of that scene
        scenes[i] = scenes[i].model_copy(update={"narration": " ".join(sents)})
        total -= _words(drop)
    kept = [s for s in scenes if s.narration.strip()]
    if len(kept) < keep_min_scenes:
        kept = [s for s in scenes if s.narration.strip()] or scenes[:1]
    return script.model_copy(update={"scenes": kept})


def merge_tiny_scenes(script, min_words: int = 6):
    """Scenes with fewer than `min_words` spoken words are merged into a neighbour (the previous scene; the first
    scene into the next), so no clip is voiced on its own with only a few words. Scenes with a chart keep it."""
    scenes = [s for s in script.scenes]
    k = 0
    while len(scenes) > 2 and k < len(scenes):
        n = len(scenes[k].narration.split())
        if n == 0 or n >= min_words:
            k += 1
            continue
        if k == 0:
            nxt = scenes[1]
            scenes[1] = nxt.model_copy(update={"narration": f"{scenes[0].narration} {nxt.narration}".strip(),
                                               "heading": scenes[0].heading or nxt.heading})
            scenes.pop(0)
        else:
            prev = scenes[k - 1]
            upd = {"narration": f"{prev.narration} {scenes[k].narration}".strip()}
            if prev.chart.kind == "none" and scenes[k].chart.kind != "none":
                upd["chart"] = scenes[k].chart
            scenes[k - 1] = prev.model_copy(update=upd)
            scenes.pop(k)
    return script if len(scenes) == len(script.scenes) else script.model_copy(update={"scenes": scenes})


def words_for(seconds_now: float, words_now: int, target_seconds: float) -> int:
    """Words to keep so a Short that runs seconds_now lands near target_seconds (always at least 5 fewer)."""
    if seconds_now <= 0:
        return words_now
    return max(40, min(words_now - 5, int(words_now * target_seconds / seconds_now)))


class ShortTooLong(RuntimeError):
    def __init__(self, msg: str, seconds: float = 0.0, rendered: bool = False):
        super().__init__(msg)
        self.seconds, self.rendered = seconds, rendered


__all__ = ["merge_tiny_scenes", "trim_to_words", "words_for", "ShortTooLong"]
