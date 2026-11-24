"""Shorts covers: big complete hook, large Max, rotating colors/layouts; no background reused within 10 Shorts."""
import numpy as np

from glivarao.art import doodle as D
from glivarao.render import doodle as R
from glivarao.studio import variety


def test_cover_styles_rotate_and_never_repeat_back_to_back():
    styles = [variety.cover_style(n) for n in range(12)]
    assert all(a[0] != b[0] and a[1] != b[1] for a, b in zip(styles, styles[1:]))
    assert {s[0] for s in styles} == {"green", "gold", "cream", "dark"}


def test_cover_has_big_text_and_large_max():
    img = D.cover("Miss December 15", "dark", "text_left", emotion="shocked")
    a = np.asarray(img.convert("RGB"), dtype=int)
    assert img.size == (1080, 1920)
    bright_top = (a[:700].mean(axis=2) > 200).mean()
    assert bright_top > 0.03                                  # big light hook text on the dark top
    green = (abs(a[..., 0] - 31) < 25) & (abs(a[..., 1] - 138) < 25) & (abs(a[..., 2] - 76) < 25)
    rows = np.where(green.any(axis=1))[0]
    assert rows.min() > 960                                   # Max sits under the hook, never over it


def test_card_phrases_use_only_the_scripts_own_words():
    txt = "It's the cutoff for a January 1 start, so act now."
    p = R.key_phrase(txt)
    assert p == "It's the cutoff for a January 1 start"
    assert set(p.lower().split()) <= set(txt.lower().replace(",", " ").replace(".", " ").split())


def test_shorts_never_reuse_a_background_from_the_last_10(store):
    from glivarao.art import scene_library

    used = []
    for n in range(10):
        place = scene_library.place_for("credit card bills", avoid_set=frozenset(used[-10:]))
        assert place not in used[-10:], (n, place)
        used.append(place)


def test_cover_shows_the_key_number_and_never_a_happy_max():
    import numpy as np

    plain = np.asarray(D.cover("Your Card Rate", "green", "text_top"), dtype=int)
    withn = np.asarray(D.cover("Your Card Rate", "green", "text_top", number="22.36%"), dtype=int)
    assert np.abs(plain - withn).sum() > 0
    assert D.HOOK_EMOTION["warning"] in ("worried", "shocked") and "happy" not in D.HOOK_EMOTION.values()


def test_render_draft_uses_the_saved_script_without_writing(settings, store, monkeypatch):
    import pytest

    from glivarao import daily_v2
    from glivarao.content.brief import Brief, Fact
    from glivarao.models import JobStatus, Scene, Script

    job = store.create("long", "ACA")
    out = settings.output_dir / job.id
    out.mkdir(parents=True)
    sc = Script(format="long", topic="t", title="t", description="", thumbnail_text="",
                scenes=[Scene(heading="h", narration="x")])
    (out / "script.json").write_text(sc.model_dump_json())
    (out / "brief.json").write_text(Brief("2026-11-24", "aca_marketplace", "ACA", "x", "US", "aca", 1.0, "high",
                                          [], "", [], [], facts=[Fact("DATA", "x", "s", "u")]).to_json())
    store.transition(job, JobStatus.SCRIPTED, "")
    store.transition(job, JobStatus.REJECTED_COMPLIANCE, "pacing")
    monkeypatch.setattr(daily_v2, "recheck", lambda *a: ["still bad"])
    with pytest.raises(ValueError, match="still fails"):
        daily_v2.render_draft(settings, store, job.id, send=False)
    monkeypatch.setattr(daily_v2, "recheck", lambda *a: [])
    monkeypatch.setattr("glivarao.scriptgen.claude._ask", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    seen = []
    monkeypatch.setattr(daily_v2, "render_and_review",
                        lambda j, s, *a, **k: seen.append(j.status) or (j.id, "long", "pending_approval", "v", ""))
    r = daily_v2.render_draft(settings, store, job.id, send=False)
    assert r[2] == "pending_approval" and seen == [JobStatus.SCRIPTED]       # no Claude call, rendered from file
