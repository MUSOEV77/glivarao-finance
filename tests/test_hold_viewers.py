"""Grab and keep viewers: the 0-30 s opening structure, the first line matching title + thumbnail, a visual change
every 2-3 s in the first 30 s and every 4-6 s after (numbers count up, no logo during the hook, motion and big
text from frame 1), and no repeats of the previous video (7-video rotation). Fact rules are unchanged."""
import numpy as np
import pytest
from PIL import Image

from glivarao.compliance import opening_issues, retention_issues
from glivarao.models import ChartSpec, Scene, Script
from glivarao.render import doodle as R
from glivarao.studio import variety

DISC = "This video is for education only and isn't financial advice."

BEFORE_LONG = ("Welcome back to the channel. Today we're going to talk about credit cards and how interest works. "
               "Credit cards are a common way to pay for things. Many banks offer them with different features. "
               "They have been around for decades, and the first ones were made of cardboard. Over time, plastic "
               "cards became the norm, and then chips were added for safety. There are many types, such as rewards "
               "cards, travel cards and store cards, and each one works a little differently from the others.")
AFTER_LONG = ("As of November 2026, your card balance probably costs you 22.36% a year. That costs you real money "
              "in interest, every single month, for years. Most people never check the one statement line that "
              "shows it, so it keeps growing quietly. By the end, you'll know the one move that stops it, and "
              "here's the part most people miss.")


def _script(first: str, fmt="long", title="Credit Card Interest: What 22.36% Costs You", thumb="Your Card Rate",
            ending="Today, open your statement and find your rate.", style="explainer", slot=None):
    filler = " ".join(["You can check this today, and it matters for your budget."] * 30)
    scenes = [Scene(heading="Hook", narration=first + " " + (filler if fmt == "long" else "")),
              Scene(heading="What to do", narration=f"{ending} {DISC}")]
    return Script(format=fmt, topic="credit card interest", title=title, description="d", thumbnail_text=thumb,
                  scenes=scenes, style=style, variety_slot=slot)


def test_before_opening_fails_after_opening_passes():
    bad = opening_issues(_script(BEFORE_LONG))
    assert any("0-5 s" in i for i in bad) and any("5-15 s" in i for i in bad) and any("promise" in i for i in bad)
    assert any("intro" in i for i in retention_issues(_script(BEFORE_LONG)))
    assert opening_issues(_script(AFTER_LONG)) == []


def test_first_line_must_match_title_and_thumbnail():
    s = _script(AFTER_LONG, title="Five Budget Apps Compared", thumb="Budget Apps")
    got = opening_issues(s)
    assert any("title" in i for i in got) and any("thumbnail" in i for i in got)


def test_short_hook_lands_in_1_5_seconds():
    assert opening_issues(_script("Your card charges you 22.36% a year.", "short", thumb="Your Card Rate")) == []
    late = opening_issues(_script("Here is something about cards that charges you 22.36%.", "short"))
    assert any("1.5 s" in i for i in late)


def _video(durations, sentence_len=3.0):
    starts, scenes, sents = [0.0], [], []
    for d in durations:
        n = max(1, int(d / sentence_len))
        sents.append([(k * d / n, (k + 1) * d / n, "You pay $1,800 in interest." if k % 3 == 0 else "Words here.")
                      for k in range(n)])
        starts.append(starts[-1] + d)
        scenes.append(Scene(heading="H", narration="x", key_points=["one point"]))
    return starts, scenes, sents


@pytest.mark.parametrize("durations", [[12, 9, 31, 22, 40, 18], [4, 4, 45, 60, 7], [61, 30, 2, 33]])
def test_never_static(durations):
    starts, scenes, sents = _video(durations)
    shots = [R.shots_for(sc, sents[i], starts[i + 1] - starts[i], i == 0, starts[i]) for i, sc in enumerate(scenes)]
    times = R.change_times(shots, starts[:-1])
    assert R.pacing_issues(times, starts[-1]) == []
    assert shots[0][0].kind == "hook"                                   # big text from frame 1
    assert any(s.kind == "number" for sl in shots for s in sl)          # key numbers on screen
    # the old planner (one change every 6-10 s) fails this check
    assert R.pacing_issues([float(t) for t in range(0, int(starts[-1]), 8)], starts[-1])


def _pic(tmp_path, portrait):
    rng = np.random.default_rng(3)
    size = (1080, 1920) if portrait else (1920, 1080)
    arr = rng.integers(40, 220, (size[1] // 8, size[0] // 8, 3), dtype=np.uint8)
    p = tmp_path / f"bg_{portrait}.png"
    Image.fromarray(arr).resize(size, Image.NEAREST).save(p)
    return str(p)


@pytest.mark.parametrize("portrait", [True, False])
def test_frame_1_has_motion_big_text_and_no_logo(tmp_path, portrait):
    sc = Scene(heading="Your card rate", narration="Your card charges you 22.36% a year.", bg_path=_pic(tmp_path, portrait))
    script = Script(format="short" if portrait else "long", topic="t", title="t", description="", thumbnail_text="",
                    scenes=[sc, sc])
    fr = R.DoodleFrames(script, 0, [(0.0, 2.4, "Your card charges you 22.36% a year.")], 24 * 6)
    f0, f1 = (np.asarray(fr.frame(k, portrait), dtype=np.int16) for k in (0, 1))
    assert np.abs(f0 - f1).mean() > 0.3                                  # moving from the first frame
    assert fr.shots[0].kind == "hook" and fr.overlay(0, portrait).text_boxes   # big text on frame 1
    big = max(b[3] - b[1] for b in fr.overlay(0, portrait).text_boxes)
    assert big >= (1920 if portrait else 1080) * 0.06
    # no logo during the hook: the brand mark corner is identical with and without the mark until 5 s
    late = R.DoodleFrames(script, 1, [(0.0, 6.0, "words")], 24 * 6, offset=10.0)
    assert fr.offset + 0 < R.NO_LOGO_UNTIL <= late.offset


def test_numbers_count_up_on_screen():
    assert R.count_text("$1,368.5 billion", 0.5) == "$684.2 billion"
    assert R.count_text("22.36%", 0.5) == "11.18%" and R.count_text("22.36%", 1.0) == "22.36%"
    sc = Scene(heading="Interest", narration="x", chart=ChartSpec())
    script = Script(format="long", topic="t", title="t", description="", thumbnail_text="", scenes=[sc, sc])
    fr = R.DoodleFrames(script, 1, [(0.0, 3.0, "Words."), (3.0, 7.0, "You pay $1,800 in interest.")], 24 * 7,
                        offset=40.0)
    k = next(i for i, s in enumerate(fr.shots) if s.kind == "number")
    early = np.asarray(fr.overlay(k, False, 1).img)
    final = np.asarray(fr.overlay(k, False, 6).img)
    assert np.abs(early.astype(int) - final.astype(int)).sum() > 0      # the number grows on screen


def test_rotation_never_repeats_the_previous_video():
    rot = variety.ROTATION + variety.ROTATION[:1]
    for a, b in zip(rot, rot[1:]):
        assert all(a[k] != b[k] for k in ("hook", "music", "layout", "pose")), (a, b)
    music = variety.MUSIC + variety.MUSIC[:1]
    assert all(a[0] != b[0] and a[1] != b[1] for a, b in zip(music, music[1:]))
    assert len({r["hook"] for r in variety.ROTATION}) == 7


def test_script_repeats_are_errors_claude_must_fix(store):
    prev = variety.script_fingerprint(_script(AFTER_LONG, ending="Today, open your statement and find your rate."))
    same = _script(AFTER_LONG, ending="Today, open your statement and find your rate.", slot=1)
    got = variety.script_issues(same, prev)
    assert any("structure" in i for i in got) and any("opening line" in i for i in got)
    assert any("ending line" in i for i in got) and any("hook type" in i for i in got)
    other = _script("Is your card balance really costing you 22.36% a year? That costs you real money in interest, "
                    "every single month, for years. Most people never check the one statement line that shows it, so "
                    "it keeps growing. By the end, you'll know the one move that stops it, and here's the part most "
                    "people miss.", ending="Tonight, write down every balance and its rate.", style="myth_vs_fact",
                    slot=2)
    assert variety.script_issues(other, prev) == []
    assert any("Won't" not in i for i in retention_issues(same, prev))


def test_seven_videos_in_a_row_never_repeat(store):
    from glivarao.art import scene_library

    used_prev: set = set()
    for n in range(14):
        sl = variety.slot(variety.next_slot(store, "long"))
        places = [scene_library.place_for("credit card bills at home", avoid_set=frozenset(used_prev)),
                  scene_library.place_for("bank savings", avoid_set=frozenset(used_prev))]
        fp = {"structure": ["explainer", "myth_vs_fact", "case_study"][n % 3], "hook_type": sl["hook"],
              "opening": f"line {n}", "ending": f"end {n}", "backgrounds": places, "opening_pose": sl["pose"],
              "thumb_layout": sl["layout"], "music": sl["music"]}
        assert variety.record(store, "long", fp) == [], n
        used_prev = set(places)
    hist = variety.history(store, "long")
    assert [h["hook_type"] for h in hist[:7]] == list(variety.HOOK_TYPES)


def test_place_for_avoids_the_previous_videos_places():
    from glivarao.art import scene_library

    first = scene_library.place_for("hospital insurance")
    assert scene_library.place_for("hospital insurance", avoid_set=frozenset({first})) != first


def test_thumbnail_layouts_stay_readable():
    from glivarao.art import doodle as D

    for layout in ("max_right", "max_left", "panel_top"):
        info = {}
        D.thumbnail("Stuck On The Minimum", "worried", None, value="22.36% APR", layout=layout, info=info)
        assert D.phone_readability(info) == [], layout
        for b in info["statement"] + [info["value"]]:
            assert 0 <= b[0] and b[2] <= 1280 and 0 <= b[1] and b[3] <= 720, (layout, b)


def test_rotation_table_lists_seven_slots():
    t = variety.rotation_table()
    assert len(t.splitlines()) == 8 and "number" in t and "warning" in t
