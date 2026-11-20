"""Keep Shorts short: 40-55 seconds, never over 60.

1. Before voicing, the script is trimmed to SHORT_MAX_WORDS (110) words: whole sentences are removed from the
   middle scenes (the hook in the first scene and the closing scene are kept), longest scenes first.
2. After voicing, the real audio length is measured; if it is over SHORT_REDO_SECONDS (58 s) the script is
   trimmed in proportion to the overshoot and voiced again (at most 2 times).
3. A Short still over SHORT_MAX_SECONDS (60 s) is never sent: the job fails and you get an alert.
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


def words_for(seconds_now: float, words_now: int, target_seconds: float) -> int:
    """Words to keep so a Short that runs seconds_now lands near target_seconds (always at least 5 fewer)."""
    if seconds_now <= 0:
        return words_now
    return max(40, min(words_now - 5, int(words_now * target_seconds / seconds_now)))


class ShortTooLong(RuntimeError):
    pass


__all__ = ["trim_to_words", "words_for", "ShortTooLong"]
