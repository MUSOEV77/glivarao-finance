"""Editorial documentary theme for the animated renderer (GLIVARAO_THEME=editorial, the default).

Each scene becomes a sequence of visual *beats* that follow the narration sentence by sentence:
  chapter  - chapter card (long videos): kicker + large serif heading + highlighter swipe
  figure   - the key number in the sentence, counting up, colour-coded (crimson cost, green growth, navy)
  chart    - full-frame editorial chart drawing on
  points   - ledger-style numbered list building item by item
  plate    - serif statement + archival duotone illustration plate
Beats hold at least MIN_BEAT seconds, crossfade into each other, and the content layer has a slow
documentary push-in. Chrome: chapter kicker, rule, wordmark and a thin progress line.
Same frame API as SceneFrames (frame(f, portrait)), so the parallel segment renderer is shared.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from PIL import Image, ImageDraw

from ..anim.director import ScenePlan
from ..anim.easing import ease_in_out, ease_out, progress
from ..art.charts_editorial import draw_editorial_chart
from ..art.editorial_style import (PAL, apply_grain, draw_text, duotone_plate, face, find_figure, fit_lines,
                                   format_figure, highlighter, paper_bg, soft_shadow, split_figure, tone, wrap)
from ..models import Script

W, H, FPS = 1920, 1080, 24
PW, PH = 1080, 1920
MIN_BEAT = 2.8
FADE = 0.45
CHAPTER_SEC = 2.6
QUOTE_MAX_WORDS = 26
PORTRAIT_PANEL = (230, 680)      # (top, height) of the Shorts visual panel
PORTRAIT_WORDS = (940, 560)      # (top, height) of the Shorts words band
PORTRAIT_CAPTION_MARGIN_V = PH - 1300  # captions sit inside the words band
KEY_TERMS = re.compile(r"\b(interest|apr|minimum|fees?|credit|score|debt|savings?|budget|invest\w*|index|compound\w*|"
                       r"tax\w*|emergency|fund|balance|retire\w*|scam\w*|fraud|dispute|loan|mortgage|rate|"
                       r"inflation|habit|automate|early|time|never|always|first)\b", re.I)


@dataclass
class Beat:
    kind: str
    t0: float
    t1: float
    figure: str = ""
    tone: str = "navy"
    label: str = ""
    text: str = ""                 # quote beats: the sentence shown as kinetic type
    span: tuple = (0.0, 0.0)       # quote beats: when that sentence is spoken (scene time)


def _label_for(scene, figure: str) -> str:
    for kp in scene.key_points:
        if figure.split()[0].strip("$%") in kp:
            return kp
    if scene.chart.kind != "none" and scene.chart.title:
        return scene.chart.title
    return scene.heading


def plan_beats(scene, sentences, plan: ScenePlan, long_form: bool) -> list[Beat]:
    """sentences: [(start, end, text)]. Deterministic, so the main process (SFX) and workers agree."""
    dur = plan.duration
    beats: list[Beat] = []
    if long_form:
        beats.append(Beat("chapter", 0.0, min(CHAPTER_SEC, dur)))
    note_times = [nt for _, nt in plan.notes]
    sticky = None
    for st, en, text in sentences:
        if scene.chart.kind != "none" and plan.chart_start is not None and en > plan.chart_start:
            cand = Beat("chart", max(st, plan.chart_start - 0.3), dur)
            sticky = "chart"
        elif sticky == "chart":
            continue
        elif scene.key_points and note_times and en >= min(note_times) - 0.2 and not find_figure(text):
            cand = Beat("points", max(st, min(note_times) - 0.3), dur)
            sticky = "points"
        elif sticky == "points":
            continue
        else:
            fig = find_figure(text)
            if fig:
                cand = Beat("figure", st, dur, fig, tone(text), _label_for(scene, fig))
            elif len(text.split()) <= QUOTE_MAX_WORDS and (not beats or beats[-1].kind != "chapter"
                                                          or not long_form or len(sentences) == 1):
                cand = Beat("quote", st, dur, text=text, span=(st, en))
            else:
                cand = Beat("plate", st, dur)
        cur = beats[-1] if beats else None
        if cur and cur.kind == cand.kind and cur.figure == cand.figure and cur.text == cand.text:
            continue
        if cur:
            earliest = cur.t1 if cur.kind == "chapter" else cur.t0 + MIN_BEAT
            if cand.t0 < earliest:
                limit = dur - 0.8 if cand.kind in ("chart", "points") else min(en - 0.6, dur - 0.8)
                if earliest >= limit:
                    continue
                cand.t0 = earliest
        beats.append(cand)
    if not beats:
        beats.append(Beat("plate", 0.0, dur))
    beats[0].t0 = 0.0
    for a, b in zip(beats, beats[1:]):
        a.t1 = b.t0
    beats[-1].t1 = dur
    return beats


def editorial_cues(beats_per_scene: list[list[Beat]], plans, scene_starts: list[float]) -> list[tuple[float, str]]:
    """Restrained sound design: a soft whoosh between scenes, a light pop on each new beat, a chime when a
    chart completes."""
    cues = []
    for beats, plan, t0 in zip(beats_per_scene, plans, scene_starts):
        if t0 > 0:
            cues.append((t0 + 0.02, "whoosh"))
        for b in beats[1:]:
            cues.append((t0 + b.t0 + 0.05, "pop"))
        if plan.chart_start is not None and any(b.kind == "chart" for b in beats):
            cb = next(b for b in beats if b.kind == "chart")
            cues.append((t0 + max(cb.t0, plan.chart_start) + plan.chart_dur, "chime"))
    return sorted(cues)


class EditorialFrames:
    def __init__(self, script: Script, idx: int, plan: ScenePlan, env, sentences, offset: float = 0.0,
                 total: float = 0.0, n_scenes: int = 1):
        self.script, self.scene, self.plan, self.idx = script, script.scenes[idx], plan, idx
        self.long = script.format == "long"
        self.beats = plan_beats(self.scene, sentences, plan, self.long)
        self.offset, self.total, self.n = offset, total or plan.duration, n_scenes
        self._cache: dict = {}

    # ------------------------------------------------------------ beat content (RGBA, content-box size)
    def _chapter(self, w, h, tb, portrait):
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img, "RGBA")
        a = int(255 * ease_out(progress(tb, 0.0, 0.5)))
        kicker = "GLIVARAO FINANCE" if self.idx == 0 else f"CHAPTER {self.idx:02d}"
        lines, size = fit_lines(self.scene.heading, "serif", 124 if not portrait else 104, w * 0.86, 2, 60)
        cy = h * 0.46
        y = cy - (len(lines) - 1) * size * 0.54
        ky = y - size * 0.5 - 70
        draw_text(d, (w / 2, ky), kicker, "sans_bold", 28, "crimson", anchor="mm", tracking=7, alpha=a)
        kw = face("sans_bold", 28).getlength(kicker) + 7 * len(kicker)
        rl = min(220, (w - kw) / 2 - 60) * ease_out(progress(tb, 0.15, 0.6))
        for sgn in (-1, 1):
            x = w / 2 + sgn * (kw / 2 + 30)
            d.line([(x, ky), (x + sgn * rl, ky)], fill=(*PAL["crimson"], a), width=3)
        rise = (1 - ease_out(progress(tb, 0.1, 0.6))) * 26
        for k, ln in enumerate(lines):
            yy = y + k * size * 1.08 + rise
            if k == len(lines) - 1:
                lw = face("serif", size).getlength(ln)
                highlighter(d, w / 2 - lw / 2 - 12, yy + size * 0.12, w / 2 + lw / 2 + 12, yy + size * 0.46,
                            progress(tb, 0.55, 0.55), alpha=int(140 * a / 255))
            draw_text(d, (w / 2, yy), ln, "serif", size, "ink", anchor="mm", alpha=a)
        return img

    def _figure(self, b: Beat, w, h, tb, portrait):
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img, "RGBA")
        pre, value, dec, suf = split_figure(b.figure)
        count = ease_out(progress(tb, 0.05, 1.1))
        shown = format_figure(pre, value * count if value >= 10 else value, dec, suf)
        final = format_figure(pre, value, dec, suf)
        col = b.tone
        text_w = w * (0.92 if portrait else 0.58)
        size = 300 if not portrait else 230
        while face("sans_xbold", size).getlength(final) > text_w and size > 90:
            size -= 8
        x = w / 2 if portrait else w * 0.04
        anchor = "ms" if portrait else "ls"
        base = h * (0.52 if portrait else 0.56)
        fw = face("sans_xbold", size).getlength(final)
        hx0 = (x - fw / 2) if portrait else x
        highlighter(d, hx0 - 14, base - size * 0.30, hx0 + fw + 14, base + size * 0.04,
                    progress(tb, 0.7, 0.5), alpha=110)
        draw_text(d, (x, base), shown, "sans_xbold", size, col, anchor=anchor)
        la = int(255 * ease_out(progress(tb, 0.35, 0.5)))
        lines, lsize = fit_lines(b.label, "serif_it", 50 if not portrait else 46, text_w, 2, 30)
        for k, ln in enumerate(lines):
            draw_text(d, (x, base + 40 + lsize * 0.9 + k * lsize * 1.15), ln, "serif_it", lsize, "sub",
                      anchor="ma" if portrait else "la", alpha=la)
        if not portrait:
            self._plate(img, int(w * 0.66), int(h * 0.10), int(w * 0.32), tb, small=True)
        return img

    def _plate(self, img, x, y, size, tb, small=False):
        a = ease_out(progress(tb, 0.1 if not small else 0.4, 0.6))
        if a <= 0:
            return
        key = ("plate", size)
        if key not in self._cache:
            card = Image.new("RGBA", (size, size), (*PAL["paper2"], 255))
            dd = ImageDraw.Draw(card)
            dd.rectangle((0, 0, size - 1, size - 1), outline=PAL["ink"], width=2)
            dd.rectangle((14, 14, size - 15, size - 15), outline=(*PAL["rule"], 255), width=1)
            art = duotone_plate(self.scene.illustration, int(size * 0.78))
            card.paste(art, ((size - art.width) // 2, (size - art.height) // 2), art)
            sh = soft_shadow((size, size), 16, 55)
            self._cache[key] = (card, sh)
        card, sh = self._cache[key]
        dy = int((1 - a) * 30)
        if a < 1:
            card = card.copy()
            card.putalpha(card.getchannel("A").point(lambda v: int(v * a)))
            sh = sh.copy()
            sh.putalpha(sh.getchannel("A").point(lambda v: int(v * a)))
        img.alpha_composite(sh, (x - 32 + 10, y - 32 + 14 + dy))
        img.alpha_composite(card, (x, y + dy))

    def _plate_beat(self, w, h, tb, portrait):
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        if portrait:
            self._plate(img, int(w * 0.16), int(h * 0.04), int(min(w * 0.68, h * 0.92)), tb)
            return img
        d = ImageDraw.Draw(img, "RGBA")
        a = int(255 * ease_out(progress(tb, 0.0, 0.5)))
        lines, size = fit_lines(self.scene.heading, "serif", 112, w * 0.52, 3, 56)
        y = h * 0.5 - (len(lines) * size * 1.08) / 2
        for k, ln in enumerate(lines):
            draw_text(d, (w * 0.04, y + k * size * 1.08), ln, "serif", size, "ink", alpha=a)
        yr = y + len(lines) * size * 1.08 + 26
        d.line([(w * 0.04, yr), (w * 0.04 + 180 * ease_out(progress(tb, 0.3, 0.6)), yr)],
               fill=(*PAL["crimson"], a), width=5)
        if self.scene.key_points and not self.plan.notes:
            pass
        self._plate(img, int(w * 0.60), int(h * 0.02), int(min(w * 0.36, h * 0.96)), tb)
        return img

    def _points(self, w, h, t, portrait):
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img, "RGBA")
        items = self.plan.notes[:3]
        size = 66 if not portrait else 52
        num_w = 130 if not portrait else 100
        rows = []
        for text, nt in items:
            lines, s2 = fit_lines(text, "serif", size, w - num_w - 40, 3, 34)
            rows.append((lines, s2, nt))
        total_h = sum(len(l) * s2 * 1.12 + 70 for l, s2, _ in rows)
        y = max(10, (h - total_h) / 2)
        for k, (lines, s2, nt) in enumerate(rows):
            a = ease_out(progress(t, nt - 0.15, 0.45))
            if a <= 0:
                break
            al = int(255 * a)
            dx = (1 - a) * 40
            draw_text(d, (8 + dx, y + s2 * 0.85), f"{k + 1:02d}", "sans_xbold", int(s2 * 0.8), "crimson", alpha=al,
                      anchor="ls")
            for j, ln in enumerate(lines):
                draw_text(d, (num_w + dx, y + s2 * 0.85 + j * s2 * 1.12), ln, "serif", s2, "ink", alpha=al,
                          anchor="ls")
            y += len(lines) * s2 * 1.12 + 40
            d.line([(0, y), ((w) * a, y)], fill=(*PAL["rule"], al), width=2)
            y += 30
        return img

    def _quote(self, b: Beat, w, h, t, portrait):
        """Kinetic pull-quote: the spoken sentence appears word by word in sync with the narration; key terms
        and emphasised words get the amber highlighter. (Burned-in captions are muted during quote beats.)"""
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img, "RGBA")
        raw = b.text
        emph = {w.lower() for seg in re.findall(r"\*([^*]+)\*", raw) for w in re.findall(r"[\w'$%,.]+", seg)}
        clean = raw.replace("*", "")
        max_w = w * (0.86 if not portrait else 0.94)
        nw = len(clean.split())
        start = (128 if nw <= 8 else 112 if nw <= 14 else 96) if not portrait else (96 if nw <= 10 else 82)
        max_lines = 4 if not portrait else 5
        lines, size = fit_lines(clean, "serif", start, max_w, max_lines, 40)
        while len(lines) * size * 1.18 > h - 30 and size > 40:  # the whole sentence must fit the box
            lines, size = fit_lines(clean, "serif", size - 4, max_w, max_lines, 40)
        if len(" ".join(lines).split()) < len(clean.split()):  # never drop words: allow extra lines at min size
            lines = wrap(clean, "serif", size, max_w)
        words = [wd for ln in lines for wd in ln.split()]
        n = max(1, len(words))
        st, en = b.span
        speak = max(0.6, en - st)
        lead_in = 0.15  # words land just before they're spoken
        f = face("serif", size)
        lh = size * 1.18
        y0 = max(6, h / 2 - len(lines) * lh / 2)
        k = 0
        chars = [len(x) + 1 for x in words]
        cum = [sum(chars[:i]) for i in range(n + 1)]
        for li, ln in enumerate(lines):
            x = (w - f.getlength(ln)) / 2 if portrait else w * 0.04
            y = y0 + li * lh
            for wd in ln.split():
                tw = st + speak * cum[k] / cum[-1] - lead_in
                a = ease_out(progress(t, tw, 0.22))
                ww = f.getlength(wd)
                key = wd.lower().strip(".,;:!?\"'") in emph or KEY_TERMS.search(wd)
                if key and a > 0:
                    highlighter(d, x - 4, y + size * 0.52, x + ww + 4, y + size * 0.92, progress(t, tw + 0.1, 0.3),
                                alpha=120)
                draw_text(d, (x, y + size * 0.9 + (1 - a) * 10), wd, "serif", size,
                          "ink" if not key else "navy", anchor="ls", alpha=int(255 * a))
                x += ww + f.getlength(" ")
                k += 1
        mark_a = int(255 * ease_out(progress(t, b.t0, 0.4)))
        if not portrait:
            draw_text(d, (w * 0.04 - 8, y0 - 18), "\u201c", "serif", 150, "crimson", anchor="lb", alpha=mark_a)
        return img

    def _chart(self, w, h, t, compact):
        pr = progress(t, self.plan.chart_start or 0, self.plan.chart_dur)
        key = ("chart", w, h)
        if pr >= 1:
            if key not in self._cache:
                self._cache[key] = draw_editorial_chart(self.scene.chart, w, h, 1.0, compact)
            return self._cache[key]
        return draw_editorial_chart(self.scene.chart, w, h, pr, compact)

    def _beat_img(self, b: Beat, w, h, t, portrait):
        tb = t - b.t0
        if b.kind == "chapter":
            return self._chapter(w, h, tb, portrait)
        if b.kind == "figure":
            return self._figure(b, w, h, tb, portrait)
        if b.kind == "chart":
            return self._chart(w, h, t, portrait)
        if b.kind == "points":
            return self._points(w, h, t, portrait)
        if b.kind == "quote":
            return self._quote(b, w, h, t, portrait)
        return self._plate_beat(w, h, tb, portrait)

    def _content(self, w, h, t, portrait):
        i = max(k for k, b in enumerate(self.beats) if b.t0 <= t + 1e-6)
        cur = self._beat_img(self.beats[i], w, h, t, portrait)
        tb = t - self.beats[i].t0
        if i > 0 and tb < FADE:
            e = ease_in_out(tb / FADE)
            prev = self._beat_img(self.beats[i - 1], w, h, t, portrait)
            out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            p2 = prev.copy()
            p2.putalpha(p2.getchannel("A").point(lambda v: int(v * (1 - e))))
            out.alpha_composite(p2)
            c2 = cur.copy()
            c2.putalpha(c2.getchannel("A").point(lambda v: int(v * e)))
            out.alpha_composite(c2, (0, int((1 - e) * 22)))
            return out
        return cur

    # ------------------------------------------------------------ composition
    def _push(self, img: Image.Image, t: float) -> Image.Image:
        z = 1 + 0.022 * ease_in_out(min(1.0, t / max(3.0, self.plan.duration)))
        if z <= 1.0005:
            return img
        w, h = img.size
        nw, nh = int(w * z), int(h * z)
        big = img.resize((nw, nh), Image.BILINEAR)
        return big.crop(((nw - w) // 2, (nh - h) // 2, (nw - w) // 2 + w, (nh - h) // 2 + h))

    def _chrome(self, frame: Image.Image, t: float, portrait: bool, show_kicker: bool):
        d = ImageDraw.Draw(frame, "RGBA")
        fw, fh = frame.size
        mx = 120 if not portrait else 60
        ky = 74 if not portrait else 150
        if show_kicker:
            a = int(255 * ease_out(progress(t, 0.1, 0.5)))
            lead = f"{self.idx:02d}" if self.long and self.idx else ""
            x = mx
            if lead:
                draw_text(d, (x, ky), lead, "sans_xbold", 26, "crimson", anchor="lm", alpha=a)
                x += face("sans_xbold", 26).getlength(lead) + 22
            head = self.scene.heading.upper()
            lines, size = fit_lines(head, "sans_semi", 24, fw - x - mx - (260 if not portrait else 0), 1, 16)
            draw_text(d, (x, ky), lines[0], "sans_semi", size, "ink", anchor="lm", tracking=3, alpha=a)
        ry = ky + 36
        rl = (fw - 2 * mx) * ease_out(progress(t, 0.0, 0.8))
        d.line([(mx, ry), (mx + rl, ry)], fill=PAL["rule"], width=2)
        if not portrait:
            draw_text(d, (fw - mx, ky), "GLIVARAO FINANCE", "sans_bold", 20, "faint", anchor="rm", tracking=4)
        else:
            draw_text(d, (fw / 2, 80), "GLIVARAO FINANCE", "sans_bold", 22, "faint", anchor="mm", tracking=5)
        # programme progress line
        pr = min(1.0, (self.offset + t) / max(1e-6, self.total))
        y = fh - 6
        d.line([(0, y), (fw, y)], fill=(*PAL["rule"], 255), width=4)
        d.line([(0, y), (fw * pr, y)], fill=PAL["navy"], width=4)

    def frame(self, f: int, portrait: bool = False) -> Image.Image:
        t = f / FPS
        if portrait:
            return self._portrait(f, t)
        frame = paper_bg(W, H).copy()
        cw, ch = W - 240, 760
        content = self._content(cw, ch, t, False)
        frame.paste(content, (120, 160), content)
        frame = self._push(frame, t)
        in_chapter = self.beats[0].kind == "chapter" and t < self.beats[0].t1 + FADE * 0.5
        self._chrome(frame, t, False, show_kicker=not in_chapter)
        return apply_grain(frame, f)

    def _portrait(self, f: int, t: float) -> Image.Image:
        """Shorts 1080x1920: visual panel on top, words in the middle band (kinetic quote, or the burned-in
        captions at PORTRAIT_CAPTION_Y), bottom quarter left clear for the Shorts UI."""
        frame = paper_bg(PW, PH).copy()
        cw, ch = PW - 120, PORTRAIT_PANEL[1]
        i = max(k for k, b in enumerate(self.beats) if b.t0 <= t + 1e-6)
        b = self.beats[i]
        if b.kind in ("quote", "plate", "chapter"):
            panel = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            size = int(min(cw * 0.72, ch * 0.96))
            self._plate(panel, (cw - size) // 2, (ch - size) // 2, size, t)
        else:
            panel = self._content(cw, ch, t, True)
        frame.paste(panel, (60, PORTRAIT_PANEL[0]), panel)
        if b.kind == "quote":
            words = self._quote(b, cw, PORTRAIT_WORDS[1], t, True)
            frame.paste(words, (60, PORTRAIT_WORDS[0]), words)
        frame = self._push(frame, t)
        self._chrome(frame, t, True, show_kicker=True)
        return apply_grain(frame, f)


def quote_windows(beats_per_scene: list[list[Beat]], scene_starts: list[float]) -> list[tuple[float, float]]:
    """Absolute (start, end) of each quote beat's own sentence, where the kinetic quote replaces captions."""
    out = []
    for beats, t0 in zip(beats_per_scene, scene_starts):
        for b in beats:
            if b.kind == "quote":
                out.append((t0 + max(b.t0, b.span[0]), t0 + min(b.t1, b.span[1] + 0.3)))
    return out


def sentence_tuples(narration) -> list[tuple[float, float, str]]:
    return [(s.start, s.end, s.text) for s in narration.sentences]


__all__ = ["EditorialFrames", "plan_beats", "editorial_cues", "quote_windows", "sentence_tuples", "Beat"]
