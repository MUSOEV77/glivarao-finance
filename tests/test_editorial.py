"""Editorial documentary theme: beat planning, figure parsing, caption muting, frames, charts, thumbnails."""
from pathlib import Path

import pytest

from glivarao.anim.director import plan_scene
from glivarao.art.charts_editorial import draw_editorial_chart
from glivarao.art.editorial_style import find_figure, split_figure, format_figure, tone, words_to_number
from glivarao.models import ChartSpec, Scene, Script
from glivarao.render.editorial import (MIN_BEAT, EditorialFrames, editorial_cues, plan_beats, quote_windows)
from glivarao.render.thumbnail_editorial import make_thumbnail_editorial
from glivarao.tts.kokoro import Sentence

DISC = "This video is for education only and isn't financial advice."


def timed(texts, gap=0.4, wps=2.6):
    out, t = [], 0.0
    for x in texts:
        d = len(x.split()) / wps
        out.append(Sentence(x, t, t + d))
        t += d + gap
    return out, t


def scene_and_plan(texts, idx=1, **kw):
    sc = Scene(heading="The minimum payment trap", narration=" ".join(texts), **kw)
    sents, dur = timed(texts)
    plan = plan_scene(sc, sents, dur, idx, [], first=idx == 0)
    return sc, [(s.start, s.end, s.text) for s in sents], plan


@pytest.mark.parametrize("text,fig", [
    ("You'd pay $8,887 in interest.", "$8,887"), ("That's up 58% from last year.", "58%"),
    ("It takes about 20 years.", "20 years"), ("They filed 8,107 complaints.", "8,107"),
    ("Say you owe five thousand dollars at twenty-four percent.", "$5,000"),
    ("Nothing numeric here.", None)])
def test_find_figure(text, fig):
    assert find_figure(text) == fig


def test_figure_split_and_format_roundtrip():
    assert split_figure("$8,887") == ("$", 8887.0, 0, "")
    assert split_figure("24 percent") == ("", 24.0, 0, "%")
    assert format_figure(*split_figure("$1,234.50")) == "$1,234.50"
    assert words_to_number("a hundred and fifty") == 150 and words_to_number("twenty-four") == 24


def test_tone():
    assert tone("You pay $8,887 in interest") == "crimson" and tone("your savings grow") == "green"


def test_beats_follow_sentences_and_hold_minimum():
    sc, sents, plan = scene_and_plan([
        "Credit card interest is charged in small monthly slices.",
        "Pay only the minimum and you'd pay $8,887 in interest over the years on that card balance.",
        "That is more than the original balance itself, which surprises almost everyone who sees it.",
        "So what can you actually do about it today?"])
    beats = plan_beats(sc, sents, plan, long_form=True)
    assert beats[0].kind == "chapter" and beats[0].t0 == 0
    assert any(b.kind == "figure" and b.figure == "$8,887" and b.tone == "crimson" for b in beats)
    for a, b in zip(beats, beats[1:]):
        assert a.t1 == b.t0 and (b.t0 - a.t0 >= MIN_BEAT - 1e-6 or a.kind == "chapter")
    assert beats[-1].t1 == pytest.approx(plan.duration)


def test_chart_and_points_are_sticky():
    chart = ChartSpec(kind="bar_compare", title="Total interest", labels=["Minimum", "$200/month"],
                      values=[8887, 2001], unit="$", source="Calculated example")
    sc, sents, plan = scene_and_plan(["Let's compare two plans side by side for the same card.",
                                      "Minimum payments cost $8,887 in total interest.",
                                      "A fixed payment costs far less.", "The difference is huge."], chart=chart)
    beats = plan_beats(sc, sents, plan, long_form=False)
    i = next(k for k, b in enumerate(beats) if b.kind == "chart")
    assert all(b.kind == "chart" for b in beats[i:])


def test_quote_windows_mute_captions_only_during_their_sentence():
    sc, sents, plan = scene_and_plan(["Here's the catch.", "It is a floor, not a target, and most people miss it."])
    beats = plan_beats(sc, sents, plan, long_form=False)
    wins = quote_windows([beats], [10.0])
    assert wins and all(10.0 <= a < b <= 10.0 + plan.duration + 0.3 for a, b in wins)
    cues = editorial_cues([beats], [plan], [10.0])
    assert cues[0] == (10.02, "whoosh")


def _script(fmt):
    scenes = [Scene(heading="How card interest works", narration="Pay only the minimum and you pay $8,887 in interest.",
                    illustration="credit_card", key_points=["Pay more than the minimum"]),
              Scene(heading="Wrap up", narration="Here's the takeaway. " + DISC,
                    chart=ChartSpec(kind="compound_growth", title="$150/month at 7%",
                                    params={"principal": 0, "rate": 0.07, "years": 30, "monthly": 150}))]
    return Script(format=fmt, topic="t", title="Credit Card Interest, Explained", description="d",
                  thumbnail_text="$8,887 In Interest", scenes=scenes)


@pytest.mark.parametrize("fmt,size", [("long", (1920, 1080)), ("short", (1080, 1920))])
def test_frames_render_every_beat(fmt, size):
    script = _script(fmt)
    for i, sc in enumerate(script.scenes):
        sents, dur = timed([sc.narration])
        plan = plan_scene(sc, sents, dur, i, [], first=i == 0)
        ef = EditorialFrames(script, i, plan, None, [(s.start, s.end, s.text) for s in sents], 0, dur * 2, 2)
        for b in ef.beats:
            img = ef.frame(int((b.t0 + 0.6) * 24), portrait=fmt == "short")
            assert img.size == size and img.mode == "RGB"


@pytest.mark.parametrize("kind", ["compound_growth", "bar_compare", "line_series", "pie_split"])
def test_editorial_charts_animate(kind):
    spec = ChartSpec(kind=kind, title="A chart", labels=["A", "B", "C"], values=[10, 30, 20], unit="$",
                     source="Illustrative example", params={"principal": 1000, "rate": 0.07, "years": 20,
                                                            "monthly": 100})
    a = draw_editorial_chart(spec, 1200, 600, 0.3)
    b = draw_editorial_chart(spec, 1200, 600, 1.0)
    assert a.size == b.size == (1200, 600) and a.tobytes() != b.tobytes()


def test_editorial_thumbnails(tmp_path):
    s = _script("long")
    p = make_thumbnail_editorial(s, tmp_path / "t.jpg")
    q = make_thumbnail_editorial(s.model_copy(update={"format": "short"}), tmp_path / "s.jpg", portrait=True)
    from PIL import Image

    assert Image.open(p).size == (1280, 720) and Image.open(q).size == (1080, 1920)
    assert p.stat().st_size < 2_000_000
