"""Thumbnail rules (credit card long video bug): the headline is a complete 2-4 word phrase, never cut; one
fact-sheet number -> a big number badge only (no line, no years); a line chart only with >= 3 real data points;
`thumb-remake` makes the thumbnail again and sends it to Telegram. Code-drawn: nothing paid."""
import json
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from glivarao import daily_v2
from glivarao.art import doodle as D
from glivarao.art.ai_visuals import bold_words, headline_problem
from glivarao.content.brief import Brief, Fact

CARD = ("As of November 2026, the average interest rate on credit card accounts that were assessed interest was "
        "22.36%.", "https://www.federalreserve.gov/releases/g19/current/")
SERIES = ("US household debt was $14.15 trillion in 2019, $15.58 trillion in 2021 and $17.06 trillion in 2023.",
          "https://www.newyorkfed.org/microeconomics/hhdc")


def _script(text, title="Stuck On The Minimum? How Credit Card Interest Works", topic="credit card interest"):
    return SimpleNamespace(thumbnail_text=text, title=title, topic=topic)


@pytest.mark.parametrize("text,ok", [("Stuck On The", False), ("Stuck On The Minimum", True), ("Debt", False),
                                     ("Pay More Than The Minimum", False), ("Your Card Rate", True),
                                     ("The BNPL Trap?", True), ("Interest Eats Your", False)])
def test_headline_must_be_a_complete_2_to_4_word_phrase(text, ok):
    assert (headline_problem(text) == "") is ok


def test_cut_headline_is_rejected_and_regenerated_never_cut():
    got = bold_words(_script("Stuck On The"), 3)
    assert len(got) == 3 and "STUCK ON THE" not in got
    for h in got:
        assert headline_problem(h) == "", h
    # a complete 4-word phrase is used whole (never cut to 3 words)
    assert bold_words(_script("Stuck On The Minimum"), 3)[0] == "STUCK ON THE MINIMUM"
    # too long: rejected, not truncated
    assert all(not h.startswith("WHY PAYING") for h in bold_words(_script("Why paying the minimum keeps you broke"), 3))
    assert D.statement("STUCK ON THE MINIMUM") == "Stuck On The Minimum."


def test_one_number_gives_a_badge_and_no_chart():
    assert D.thumb_data([CARD], 2026) == {"value": "22.36% APR", "points": [], "pair": None, "label": ""}
    # two numbers ('up from 6.26% a year earlier') are still not a series: badge only
    assert D.thumb_data([("The 30-year mortgage rate averaged 7.28%, up from 6.26% a year earlier.", "u")],
                        2026)["points"] == []


def test_three_real_points_give_a_line_chart():
    d = D.thumb_data([SERIES, CARD], 2026)
    assert [y for y, _ in d["points"]] == ["2019", "2021", "2023"] and d["value"] == "$17.1T"


def _green_in_panel(img):
    a = np.asarray(img, dtype=np.int16)[380:700, 30:760]
    return int(((abs(a[..., 0] - D.GREEN[0]) < 30) & (abs(a[..., 1] - D.GREEN[1]) < 30) &
                (abs(a[..., 2] - D.GREEN[2]) < 30)).sum())


def test_badge_thumbnail_has_no_line_and_no_years(tmp_path):
    info = {}
    img = D.thumbnail("Stuck On The Minimum", "worried", tmp_path / "t.jpg", value="22.36% APR",
                      start_year="2025", end_year="2026", info=info)
    assert info["years"] == [] and info["value"] and D.phone_readability(info) == []
    assert _green_in_panel(img) < 200                                    # no green trend line
    assert len(info["statement"]) == 2                                   # 4 words on 2 lines, nothing cut
    for b in info["statement"] + [info["value"]]:
        assert 0 <= b[0] and b[2] <= 1280 and b[3] <= 720


def test_chart_thumbnail_only_with_real_points(tmp_path):
    info = {}
    d = D.thumb_data([SERIES], 2026)
    img = D.thumbnail("Debt Keeps Climbing", "worried", tmp_path / "t.jpg", value=d["value"], points=d["points"],
                      info=info)
    assert len(info["years"]) == 2 and _green_in_panel(img) > 1000 and D.phone_readability(info) == []
    info2 = {}
    D.thumbnail("Debt Keeps Climbing", "worried", tmp_path / "t2.jpg", value="$17.1T", points=d["points"][:2],
                info=info2)
    assert info2["years"] == []                                          # 2 points: no chart


class FakeTG:
    def __init__(self):
        self.calls = []

    def call(self, method, files=None, **params):
        self.calls.append((method, params))
        return {"ok": True}


def test_thumb_remake_regenerates_and_sends(settings, store, tmp_path):
    from glivarao.models import Script
    from glivarao.scriptgen.prompts import normalize_direction
    from tests.test_e2e_dryrun import fake_claude

    s = replace(settings, theme="doodle", doodle_ref_path=str(tmp_path / "ref.png"),
                doodle_library_dir=str(tmp_path / "lib"), telegram_approver_chat_id="42")
    d = fake_claude("x", "long", 1)
    d["scenes"] = [normalize_direction(sc) for sc in d["scenes"]]
    script = Script.model_validate({**d, "format": "long", "topic": "Credit card interest",
                                    "thumbnail_text": "Stuck On The"})
    job = store.create("long", "Credit card interest")
    out = s.output_dir / job.id
    out.mkdir(parents=True)
    (out / "script.json").write_text(script.model_dump_json())
    b = Brief("2026-11-23", "credit_card", "Credit card interest", "debt", "US", "cards", 1.0, "high", [], "", [], [],
              facts=[Fact("DATA", CARD[0], "Federal Reserve G.19", CARD[1])])
    (out / "brief.json").write_text(b.to_json())
    (out / "metadata.json").write_text(json.dumps({"title": "t", "thumbnail_options": ['doodle (code-drawn) "STUCK ON THE"']}))
    job.thumbnail_path = str(out / "thumbnail_2.jpg")     # you had picked option 2
    job.video_path = str(out / "video.mp4")
    store.save(job)
    tg = FakeTG()
    r = daily_v2.thumb_remake(s, store, job.id, client=tg)
    assert r["theme"] == "doodle" and len(r["how"]) == 3
    assert all("number badge 22.36% APR" in h and "STUCK ON THE\"" not in h for h in r["how"])
    assert all((out / f"thumbnail_{k}.jpg").exists() for k in (1, 2, 3))
    assert store.get(job.id).thumbnail_path.endswith("thumbnail_2.jpg")   # your pick is kept
    assert json.loads((out / "metadata.json").read_text())["thumbnail_options"] == r["how"]
    methods = [m for m, _ in tg.calls]
    assert methods[0] == "sendMessage" and methods.count("sendPhoto") == 3


def test_long_thumbnail_styles_rotate_and_badge_is_the_surprising_number():
    from glivarao.studio.fact_library import ACA

    styles = [D.thumb_style(n) for n in range(12)]
    assert all(a[0] != b[0] and a[1] != b[1] for a, b in zip(styles, styles[1:]))
    assert {s[1] for s in styles} == set(D.THUMB_LAYOUTS) and {s[0] for s in styles} == set(D.THUMB_BG)
    assert D.thumb_data([(f.text, f.url) for f in ACA], 2026)["value"] != "100%"
    for pal, lay in styles[:4]:
        info = {}
        D.thumbnail("Miss December 15", "worried", None, value="$15,960", layout=lay, palette=pal,
                    prop="hospital", info=info)
        assert D.phone_readability(info) == [], (pal, lay)


def test_real_visuals_only_and_short_emotional_headline():
    from glivarao.studio.fact_library import R_401K
    from glivarao.studio.launch_plan import CARD_RATE, MORTGAGE

    d = D.thumb_data([(MORTGAGE.text, MORTGAGE.url)], 2026)
    assert d["pair"] == ("6.26%", "a year earlier", "7.28%", "now") and D.visual_options(d)[:2] == ["bars",
                                                                                                    "before_after"]
    assert D.thumb_data([(R_401K.text, R_401K.url)], 2026)["pair"] == ("$24,500", "2026", "$25,500", "2027")
    card = D.thumb_data([(CARD_RATE.text, CARD_RATE.url)], 2026)
    assert card["pair"] is None and D.visual_options(card) == ["badge"]          # never an invented comparison
    heads = bold_words(_script("Stuck On The Minimum"), 3, max_words=3)
    assert all(len(h.split()) <= 3 and headline_problem(h, 3) == "" for h in heads)
    for vis in ("bars", "before_after"):
        info = {}
        D.thumbnail("Don't Be Fooled", "worried", None, value=d["value"], visual=vis, pair=d["pair"],
                    layout="max_right", palette="cream", prop="house", info=info)
        assert D.phone_readability(info) == [], vis


def test_lone_percent_badge_gets_a_label_and_poses_rotate():
    from glivarao.studio.fact_library import EMERGENCY

    d = D.thumb_data([(f.text, f.url) for f in EMERGENCY], 2026)
    assert d["value"] == "55%" and d["label"] == "have 3 months saved"
    assert 2 <= len(d["label"].split()) <= 4
    info = {}
    D.thumbnail("It Adds Up", "pointing", None, value=d["value"], value_label=d["label"], info=info)
    assert D.phone_readability(info) == []
    poses = {D.pose_for(h, n) for h in D.POSES_FOR_HOOK for n in range(3)}
    assert "happy" not in poses and len(poses) >= 5
    assert len({D.pose_for("warning", n) for n in range(3)}) == 3
