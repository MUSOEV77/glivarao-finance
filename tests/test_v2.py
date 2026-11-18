"""Tests for the v2 voice (Kokoro) and animation engine."""
import json
import shutil
from pathlib import Path

import pytest

from glivarao.anim.actor import Actor, envelope
from glivarao.anim.director import GESTURES, plan_scene
from glivarao.anim.rig import Pose, draw_max, draw_penny
from glivarao.models import Scene, Script
from glivarao.tts import TTSError, synthesize
from glivarao.tts.kokoro import MODEL, Sentence, normalize_text, split_sentences

HAS_KOKORO = MODEL.exists()
try:
    import kokoro_onnx  # noqa: F401
    import misaki  # noqa: F401
except ImportError:
    HAS_KOKORO = False


def test_finance_text_normalization():
    t = normalize_text("Max your 401(k), then the S&P 500 vs. bonds over 5-10 years; $2.5M goal & a 403(b).")
    assert "four-oh-one-K" in t and "S and P five hundred" in t and "versus" in t
    assert "5 to 10 years" in t and "2.5 million dollars" in t and "four-oh-three-B" in t and "&" not in t


def test_sentence_split_keeps_emphasis_and_questions():
    parts = split_sentences("After thirty? *Over a hundred thousand.* The end. $5 is fine.")
    assert parts == ["After thirty?", "*Over a hundred thousand.*", "The end.", "$5 is fine."]


def test_placeholder_voices_refused_in_production(settings, tmp_path):
    prod = settings.__class__(**{**settings.__dict__, "mode": "production"})
    for provider in ("espeak", "silent"):
        with pytest.raises(TTSError, match="never allowed in production"):
            synthesize("hello", tmp_path / "x.wav", prod, provider=provider)


@pytest.mark.skipif(not HAS_KOKORO, reason="Kokoro model/runtime not installed")
def test_kokoro_narration_timings_and_pronunciation():
    from glivarao.tts.kokoro import KokoroEngine

    n = KokoroEngine.get().narrate("Max your 401(k) match. Then open a Roth IRA. Does FICO matter? *Yes.*")
    assert [s.question for s in n.sentences] == [False, False, True, False]
    assert n.sentences[-1].emphasis and n.unknown_words == []
    for a, b in zip(n.sentences, n.sentences[1:]):
        assert a.end < b.start  # a natural pause separates every sentence
    assert 6 < n.duration < 16 and abs(float(abs(n.audio).max()) - 0.89) < 0.01


def test_rig_draws_and_blends():
    a, b = Pose(), GESTURES["cheer"]
    mid = a.blend(b, 0.5)
    assert a.r_sh < mid.r_sh < b.r_sh
    assert draw_max(mid, 0.5).size == (390, 560) and draw_penny(mid, 0.5).getbbox() is not None


def _sentences(*texts, gap=0.4, dur=2.0):
    out, t = [], 0.1
    for x in texts:
        out.append(Sentence(x, t, t + dur, "*" in x, x.endswith("?")))
        t += dur + gap
    return out


def test_director_follows_the_words():
    scene = Scene(heading="h", narration="x", character="duo",
                  chart={"kind": "compound_growth", "params": {"principal": 0, "rate": 0.07, "years": 10, "monthly": 100}})
    sents = _sentences("Let me explain.", "Is that worth it?", "It grows to 17,000 dollars.", "The catch is fees.")
    plan = plan_scene(scene, sents, 10.0, 3, [], first=False)
    gestures = [c.gesture for c in plan.actors[0].cues]
    assert gestures[1] == "shrug" and gestures[3] == "worry"
    assert plan.chart_start == pytest.approx(sents[2].start)  # chart draws when the number is spoken
    assert plan.set == "board" and len(plan.actors) == 2 and not plan.actors[1].speaking
    assert [k.t for k in plan.camera] == sorted(k.t for k in plan.camera)
    assert all(g in GESTURES for c in plan.actors[1].cues for g in [c.gesture])


def test_actor_walks_in_and_lip_syncs():
    import numpy as np

    scene = Scene(heading="h", narration="x", entrance="walk_in")
    plan = plan_scene(scene, _sentences("Hello there."), 5.0, 0, [], first=True)
    audio = np.concatenate([np.zeros(24000), 0.5 * np.sin(np.linspace(0, 2000, 48000))]).astype("float32")
    actor = Actor(plan.actors[0], envelope(audio, 24000, 24), 24)
    _, x0, _ = actor.state(0.0)
    _, x_end, _ = actor.state(4.0)
    assert x0 < 0 < x_end == plan.actors[0].x
    assert actor.state(0.5)[0].mouth == 0 and actor.state(2.0)[0].mouth > 0.3


@pytest.mark.skipif(not (HAS_KOKORO and shutil.which("ffmpeg")), reason="needs Kokoro + ffmpeg")
def test_render_animated_end_to_end(settings, tmp_path):
    from glivarao.render.animated import render_animated
    from glivarao.render.video import probe

    data = json.loads(Path("config/samples/sample_60s.json").read_text())
    data["scenes"] = data["scenes"][2:4]  # chart scene + duo scene keeps the test quick
    script = Script.model_validate(data)
    res = render_animated(script, tmp_path / "v2", settings, workers=2)
    info = probe(res.video)
    assert (info["width"], info["height"]) == (1920, 1080) and info["audio_codec"] == "aac"
    assert abs(info["duration"] - res.duration) < 0.3 and res.unknown_words == []
    assert "-->" in res.srt.read_text()
