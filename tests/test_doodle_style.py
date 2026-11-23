"""Doodle style v2: Max designed once (Nano Banana) -> 8 transparent cutouts reused everywhere; full pictures behind
every shot (key scenes + scene library); every text inside the safe area; <= 15% empty frames; $2 cap for the
samples command; cost estimate within the image budget. Nano Banana is simulated (no paid call)."""
import json
import random
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from glivarao.art import doodle as D
from glivarao.art import doodle_prep, max_assets
from glivarao.models import ChartSpec, Scene, Script
from glivarao.render import doodle as R

PRICES = {"1K": 0.0336, "2K": 0.0504}


class FakeNanoBanana:
    """Draws a simple character on magenta (poses) or a busy full-frame scene (16:9 / 9:16)."""

    def __init__(self):
        self.spent_usd, self.calls, self._cache = 0.0, [], {}

    def price(self, size):
        return PRICES[size]

    def generate(self, prompt, size="1K", aspect="1:1", refs=None):
        key = (prompt, size, aspect)
        if key in self._cache:                       # like the real client: the same request is free
            return self._cache[key].copy()
        img = self._draw(prompt, size, aspect, refs)
        self._cache[key] = img
        return img.copy()

    def _draw(self, prompt, size, aspect, refs):
        self.calls.append((prompt[:60], size, aspect, len(refs or [])))
        self.spent_usd += PRICES[size]
        r = random.Random(len(self.calls))
        if "magenta" in prompt:
            img = Image.new("RGB", (768, 1024), (255, 0, 255))
            d = ImageDraw.Draw(img)
            d.ellipse((290, 120, 480, 310), fill=(240, 200, 170), outline=(0, 0, 0), width=8)
            d.ellipse((320, 190, 370, 240), fill=(255, 255, 255), outline=(0, 0, 0), width=5)
            d.rectangle((270, 310, 500, 650), fill=(31, 138, 76), outline=(0, 0, 0), width=8)
            d.rectangle((300, 650, 470, 960), fill=(200, 180, 140), outline=(0, 0, 0), width=8)
            return img
        w, h = (1152, 2048) if aspect == "9:16" else (2048, 1152)
        img = Image.new("RGB", (w, h), (120, 170, 200))
        d = ImageDraw.Draw(img)
        for _ in range(900):
            x, y, s = r.randint(0, w), r.randint(0, h), r.randint(20, 160)
            d.rectangle((x, y, x + s, y + s * 0.8), fill=tuple(r.randint(40, 230) for _ in range(3)),
                        outline=(20, 20, 20), width=4)
        return img


@pytest.fixture
def ds(settings, tmp_path):
    return replace(settings, doodle_ref_path=str(tmp_path / "character" / "doodle_reference.png"),
                   doodle_library_dir=str(tmp_path / "library"), theme="doodle")


def test_key_out_removes_background_and_keeps_enclosed_areas():
    img = FakeNanoBanana().generate("pose, magenta background", "1K", "3:4")
    cut = max_assets.key_out(img)
    a = np.asarray(cut.getchannel("A"))
    assert a[0, 0] == 0 and a[-1, -1] == 0                       # background gone
    assert max_assets.check_cutout(cut, img.size) == []
    eye = a[(215 - 120) + 12 - 10, (345 - 270) + 12]               # white eye inside the head stays opaque
    assert eye == 255
    rgb = np.asarray(cut.convert("RGB"), dtype=np.int16)
    assert not ((rgb[..., 0] > 200) & (rgb[..., 2] > 200) & (rgb[..., 1] < 90) & (a > 128)).any()


def test_max_designed_once_with_8_poses_then_reused_for_free(ds):
    gi = FakeNanoBanana()
    r = max_assets.design(ds, gi, cap_usd=2.0)
    assert r["made"] and max_assets.ready(ds) and len(gi.calls) == 9            # master + 8 poses
    assert all(c[3] == 1 for c in gi.calls[1:])                                  # every pose uses the master
    assert set(max_assets.POSES) == {"explaining", "pointing", "worried", "shocked", "thinking", "happy", "sad",
                                     "cheering"}
    assert max_assets.design(ds, gi, cap_usd=2.0)["made"] is False and len(gi.calls) == 9   # never again
    assert max_assets.load_pose(ds, "confident").mode == "RGBA"                   # mood -> pose mapping
    assert Image.open(max_assets.sheet_path(ds)).size == (1536, 864)


def test_design_stops_before_exceeding_the_cap(ds):
    with pytest.raises(max_assets.DesignBudget):
        max_assets.design(ds, FakeNanoBanana(), cap_usd=0.2)


LONG_HEADINGS = ["Is the national debt a problem for your household budget and your savings account?",
                 "Supercalifragilisticexpialidocious-interest-rate-explanations-without-any-spaces-at-all",
                 "Why houses got so expensive", "A", "The average card rate"]


@pytest.mark.parametrize("portrait", [False, True])
@pytest.mark.parametrize("kind", ["title", "number", "chart", "points"])
def test_every_text_fits_inside_the_safe_area(kind, portrait):
    size = (1080, 1920) if portrait else (1920, 1080)
    sx0, sy0, sx1, sy1 = R.safe_box(size, portrait)
    for heading in LONG_HEADINGS:
        sc = Scene(heading=heading, narration="x", key_points=[heading, "Pay the highest rate first " * 3, "ok"],
                   chart=ChartSpec(kind="bar_compare", title=heading, values=[1, 2, 3], labels=["a", "b", heading]))
        ov = R.build_overlay(sc, R.Shot(0, 8, kind, heading, {"num": "$1,368,500,000,000.00"}), size, portrait)
        assert ov.text_boxes, kind
        for b in ov.text_boxes:
            assert sx0 <= b[0] and sy0 <= b[1] and b[2] <= sx1 and b[3] <= sy1, (kind, portrait, heading, b)
        alpha = np.asarray(ov.img.getchannel("A"))
        # nothing past the margins or over the captions except the card's faint soft shadow
        assert alpha[:, :sx0 - 2].max() <= 40 and alpha[:, sx1 + 12:].max() <= 40
        assert alpha[sy1 + 14:, :].max() <= 40


def _scene_script(fmt="long"):
    scenes = [Scene(heading="Card bills at night", narration="The bills keep coming. The rate was 22.36% a year."),
              Scene(heading="Home prices", narration="Home prices climbed faster than paychecks.",
                    chart=ChartSpec(kind="line_series", values=[1, 1.1, 1.2, 1.3, 2, 3], title="Prices")),
              Scene(heading="What to do", narration="This video is for education only and isn't financial advice.")]
    return Script(format=fmt, topic="t", title="t", description="", thumbnail_text="", scenes=scenes)


def test_prepare_gives_every_scene_a_full_picture_and_frames_are_not_empty(ds, tmp_path):
    gi = FakeNanoBanana()
    max_assets.design(ds, gi)
    script, stats = doodle_prep.prepare(_scene_script(), tmp_path / "job", replace(ds, doodle_key_scenes_long=1),
                                        gi=gi)
    assert stats["key_ai"] == 1 and stats["library"] == 2
    assert all(s.bg_path and Path(s.bg_path).exists() for s in script.scenes)
    assert script.scenes[0].max_pose_path is None                     # key scene: Max already acts in it
    assert all(s.max_pose_path for s in script.scenes[1:])            # library place + Max cutout
    for i in range(2):
        fr = R.DoodleFrames(script, i, [(0.0, 7.0, "a"), (7.0, 14.0, "b 22.36%")], 14 * 24)
        for f in (0, 100, 200):
            img = fr.frame(f, False)
            assert img.size == (1920, 1080) and R.empty_ratio(img) <= 0.15
    # Shorts: portrait pictures
    sscript, _ = doodle_prep.prepare(_scene_script("short"), tmp_path / "s", ds, gi=gi)
    assert all("portrait" in s.bg_path or "key_" in s.bg_path for s in sscript.scenes)
    img = R.DoodleFrames(sscript, 1, [(0.0, 8.0, "x")], 8 * 24).frame(10, True)
    assert img.size == (1080, 1920) and R.empty_ratio(img) <= 0.15


def test_no_pictures_means_editorial_fallback_not_an_empty_video(ds, tmp_path):
    with pytest.raises(doodle_prep.DoodleUnavailable, match="Max has not been designed"):
        doodle_prep.prepare(_scene_script(), tmp_path, ds)
    max_assets.design(ds, FakeNanoBanana())
    with pytest.raises(doodle_prep.DoodleUnavailable, match="no scene pictures"):
        doodle_prep.prepare(_scene_script(), tmp_path, ds)            # paid images off, empty library


def test_old_empty_doodle_frame_would_fail_the_empty_check():
    blank = D.paper(1920, 1080).copy()
    Pen = D.Pen(blank)
    Pen.text((600, 400), "22.36%", 200)
    assert R.empty_ratio(blank) > 0.5


def test_cost_estimate_fits_the_image_budget(settings):
    e = doodle_prep.estimate(settings)
    assert e["per_long"] == pytest.approx(6 * 0.0504, abs=1e-3)
    assert e["per_short"] == pytest.approx(0.0336, abs=1e-3)
    assert e["per_month"] == pytest.approx(16 * 6 * 0.0504 + 90 * 0.0336, abs=0.01)
    assert e["fits"] and e["per_month"] + e["library_once"] < settings.image_monthly_budget_usd


def test_shots_are_6_to_10_seconds():
    sents = [(0.0, 2.5, "a"), (2.5, 5.0, "b"), (5.0, 9.5, "c"), (9.5, 12.0, "d"), (12.0, 37.0, "long one"),
             (37.0, 40.0, "e")]
    shots = R.plan_shots(sents, 41.0)
    assert shots[0][0] == 0.0 and shots[-1][1] == 41.0
    assert all(4.0 <= e - s <= 10.0 for s, e, _ in shots)


def test_style_samples_command_cap_cost_checks_and_telegram(ds, store, tmp_path, monkeypatch, capsys):
    from glivarao import __main__ as cli
    from glivarao.publish.telegram import TelegramClient, poll_decisions
    from glivarao.studio import style_samples as S
    from tests.conftest import FakeTelegramSession

    gi = FakeNanoBanana()
    res = S.make(ds, gi, tmp_path / "samples")
    assert res["usd"] == pytest.approx(0.0504 + 8 * 0.0336 + 3 * 0.0504, abs=1e-3) and res["usd"] <= S.CAP_USD
    assert all(not [c for c in v if "outside" in c or "empty (" in c] for v in res["checks"].values())
    assert len(res["frames"]) == 3 and len(res["thumbs"]) == 3
    assert "per long video" in S.summary(ds, res) and "fits" in S.summary(ds, res)
    s = replace(ds, telegram_bot_token="T", telegram_approver_chat_id="42")
    tg = FakeTelegramSession()
    client = TelegramClient("T", session=tg)
    S.send(s, res, client)
    methods = [m for m, _ in tg.calls]
    assert methods.count("sendMediaGroup") == 2 and methods.count("sendPhoto") == 1
    assert "$0." in json.dumps(tg.calls[0][1]) and "style:doodle-v2" in json.dumps(tg.calls[-1][1])
    env = tmp_path / ".env"
    env.write_text("GLIVARAO_THEME=editorial\n")
    monkeypatch.setenv("ENV_FILE", str(env))
    tg.updates = [{"update_id": 1, "callback_query": {"id": "c", "from": {"id": 42}, "data": "style:doodle-v2",
                                                      "message": {"chat": {"id": 42}}}}]
    poll_decisions(store, s, client)
    assert S.approved(store) and "GLIVARAO_THEME=doodle" in env.read_text()
    # the CLI prints the money spent
    monkeypatch.setattr("glivarao.art.gemini_image.GeminiImage", lambda st: FakeNanoBanana())
    monkeypatch.setattr(cli, "get_settings", lambda: ds)
    cli.main(["style-samples", "--out", str(tmp_path / "cli")])
    assert "NANO BANANA SPENT BY THIS COMMAND: $" in capsys.readouterr().out


def test_thumbnail_uses_the_max_cutout(ds, tmp_path):
    max_assets.design(ds, FakeNanoBanana())
    img = D.thumbnail("Debt Wins", "worried", tmp_path / "t.jpg", max_img=max_assets.load_pose(ds, "worried"))
    arr = np.asarray(img, dtype=np.int16)
    green = (abs(arr[..., 0] - 31) < 25) & (abs(arr[..., 1] - 138) < 25) & (abs(arr[..., 2] - 76) < 25)
    assert img.size == (1280, 720) and green[:, 800:].sum() > 5000      # Max's sweater on the right
    assert D.statement("THE BNPL TRAP?") == "The BNPL Trap."


def test_enclosed_magenta_next_to_the_face_is_removed_and_check_fails_above_0_1_percent():
    img = FakeNanoBanana().generate("pose, magenta background", "1K", "3:4")
    d = ImageDraw.Draw(img)
    d.line([(480, 330), (560, 200), (470, 110)], fill=(0, 0, 0), width=14)        # an arm up to the head ...
    d.polygon([(482, 300), (540, 205), (482, 140)], fill=(255, 0, 255))           # ... enclosing magenta
    d.ellipse((330, 195, 342, 207), fill=(236, 40, 230))                          # a magenta-ish glint in the glasses
    cut = max_assets.key_out(img)
    assert max_assets.magenta_share(cut) <= max_assets.MAGENTA_MAX
    assert max_assets.check_cutout(cut, img.size) == []
    dirty = cut.copy()
    ImageDraw.Draw(dirty).rectangle((100, 300, 135, 335), fill=(255, 0, 255, 255))   # ~0.5% magenta blob
    probs = max_assets.check_cutout(dirty, img.size)
    assert any("magenta" in x for x in probs)


def test_a_pose_that_stays_dirty_fails_the_design_instead_of_being_kept(ds, monkeypatch):
    monkeypatch.setattr(max_assets, "check_cutout", lambda cut, size: ["0.50% magenta left on the figure"])
    gi = FakeNanoBanana()
    with pytest.raises(max_assets.MaxNotClean, match="magenta"):
        max_assets.design(ds, gi, cap_usd=2.0)
    assert len(gi.calls) == 1 + 8 * len(max_assets.ATTEMPTS)                     # every pose tried 4 times
    assert not max_assets.ready(ds)                                               # nothing kept


def test_repair_recuts_cached_poses_for_free_and_keeps_the_master(ds, tmp_path):
    from glivarao.studio import style_samples as S

    gi = FakeNanoBanana()
    max_assets.design(ds, gi)
    master = (max_assets.max_dir(ds) / "master.png").read_bytes()
    n = len(gi.calls)
    res = S.repair(ds, gi, tmp_path / "fix", cap=1.0)
    assert res["usd"] == 0 and len(gi.calls) == n                                   # cached: nothing paid
    assert (max_assets.max_dir(ds) / "master.png").read_bytes() == master
    assert len(res["thumbs"]) == 3 and all(v == ["readable at 160x90"] for v in res["checks"].values())


@pytest.mark.parametrize("words,value,y0,y1", [("Debt Wins", "$19.1T", "2019", "2026"),
                                              ("Homes Got Expensive", "7.28%", "2025", "2026"),
                                              ("$40 Trillion Owed", "$40.7T", "2019", "2026"),
                                              ("Minimum Payment Trap", "$1,368.5B", "2021", "2026")])
def test_thumbnail_number_badge_panel_and_phone_readability(ds, tmp_path, words, value, y0, y1):
    max_assets.design(ds, FakeNanoBanana())
    info = {}
    img = D.thumbnail(words, "worried", tmp_path / "t.jpg", value=value, start_year=y0, end_year=y1,
                      max_img=max_assets.load_pose(ds, "worried"), info=info)
    assert D.phone_readability(info) == [], D.phone_readability(info)
    assert info["value"] and info["years"] == []     # one number: badge only, no years (not a trend)
    for b in info["statement"] + [info["value"]]:
        assert 0 <= b[0] and 0 <= b[1] and b[2] <= 1280 and b[3] <= 720             # inside the thumbnail
    arr = np.asarray(img, dtype=np.int16)
    vb = info["value"]
    region = arr[vb[1]:vb[3], vb[0]:vb[2]]
    gold = (abs(region[..., 0] - 224) < 40) & (abs(region[..., 1] - 165) < 40) & (region[..., 2] < 110)
    assert gold.mean() > 0.08                                                         # the number is gold
    bg = arr[5:40, 5:40].reshape(-1, 3).mean(axis=0)
    assert bg.mean() < 236 and bg[0] > bg[2] + 15                                     # warmer, darker paper


def test_key_number_from_facts_for_production_thumbnails():
    assert D.compact_number("$1,368.5 billion") == "$1.4T" and D.compact_number("$208 billion") == "$208B"
    assert D.key_number(["As of the third quarter of 2026, US household debt was $19.1 trillion, up $5 trillion "
                         "since the end of 2019."], 2026) == ("$19.1T", "2019", "2026")
    assert D.key_number(["As of November 19, 2026, the 30-year fixed mortgage rate averaged 7.28%, up from 6.26% a "
                         "year earlier."], 2026) == ("7.28%", "2025", "2026")
    assert D.key_number(["no numbers here"], 2026) == ("", "", "")


def test_cli_repair_sends_only_sheet_and_thumbnails_and_prints_cost(ds, tmp_path, monkeypatch, capsys):
    from glivarao import __main__ as cli
    from glivarao.studio import style_samples as S

    fake = FakeNanoBanana()
    max_assets.design(ds, fake)
    sent = {}
    monkeypatch.setattr("glivarao.art.gemini_image.GeminiImage", lambda st: fake)
    monkeypatch.setattr(cli, "get_settings", lambda: ds)
    monkeypatch.setattr(S, "send_thumbs", lambda st, res, client=None: sent.update(res=res))
    monkeypatch.setattr(S, "send", lambda *a, **k: pytest.fail("full samples must not be resent"))
    cli.main(["style-samples", "--repair-max", "--send-thumbs", "--out", str(tmp_path / "o")])
    out = capsys.readouterr().out
    assert "NANO BANANA SPENT BY THIS COMMAND: $0.00 (cap $1.00)" in out and sent["res"]["frames"] == []
