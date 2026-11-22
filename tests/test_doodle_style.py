"""Doodle style: same Max every time, 6-10 s shots with camera moves, brand mark, thumbnails (2-3 word statement
ending with a period, one simple chart, Max), style samples + Telegram approval (old style stays until approved)."""
import hashlib
import io
import json
import shutil
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from glivarao.art import doodle as D
from glivarao.models import ChartSpec, Scene, Script
from glivarao.render import doodle as R


def _png(img) -> str:
    b = io.BytesIO()
    img.save(b, "PNG")
    return hashlib.sha256(b.getvalue()).hexdigest()


def test_max_reference_sheet_is_identical_every_time(tmp_path):
    a, b = D.reference_sheet(tmp_path / "a.png"), D.reference_sheet()
    assert _png(a) == _png(b) and a.size == (1536, 1024)
    assert _png(D.max_figure("worried")) == _png(D.max_figure("worried"))
    assert _png(D.max_figure("worried")) != _png(D.max_figure("happy"))      # emotions differ, Max doesn't


def test_shots_are_6_to_10_seconds():
    sents = [(0.0, 2.5, "a"), (2.5, 5.0, "b"), (5.0, 9.5, "c"), (9.5, 12.0, "d"), (12.0, 37.0, "long one"),
             (37.0, 40.0, "e")]
    shots = R.plan_shots(sents, 41.0)
    assert shots[0][0] == 0.0 and shots[-1][1] == 41.0
    assert all(b[0] == pytest.approx(a[1]) for a, b in zip(shots, shots[1:]))   # back to back
    assert all(4.0 <= e - s <= 10.0 for s, e, _ in shots), [round(e - s, 1) for s, e, _ in shots]
    assert R.plan_shots([(0.0, 5.0, "only")], 5.0) == [(0.0, 5.0, "only")]


def test_frames_cut_between_shots_and_camera_moves_within_a_shot():
    sc = Scene(heading="How card interest piles up", narration="x", illustration="credit_card",
               chart=ChartSpec(kind="line_series", values=[1, 2, 2, 3, 5, 8], title="Interest (illustration)"))
    script = Script(format="long", topic="t", title="t", description="", thumbnail_text="", scenes=[sc])
    fr = R.DoodleFrames(script, 0, [(0.0, 7.0, "first"), (7.0, 14.0, "As of November 2026 it was 22.36%.")], 14 * 24)
    a, b, c, d, e = (np.asarray(fr.frame(f, False), dtype=np.int16) for f in (0, 100, 101, 167, 168))
    assert a.shape == (1080, 1920, 3)
    step = np.abs(b - c).mean()                           # one frame of slow camera movement
    assert 0 < step and np.abs(a - b).mean() > step       # the camera keeps moving through the shot
    assert np.abs(d - e).mean() > 5 * step                # hard cut at 7 s to a different drawing
    assert [s.kind for s in fr.shots] == ["title", "chart"]
    top_right = a[10:70, 1700:1910]
    assert ((top_right[..., 1] > 110) & (top_right[..., 0] < 80)).sum() > 50    # green GLIVARAO mark on screen
    assert fr.frame(0, True).size == (1080, 1920)       # Shorts


def test_thumbnail_statement_chart_and_size(tmp_path):
    assert D.statement("MINIMUM PAYMENT TRAP") == "Minimum Payment Trap."
    assert D.statement("THE BNPL TRAP?") == "The BNPL Trap."
    assert D.statement("debt wins") == "Debt Wins."
    img = D.thumbnail("Debt Wins", "worried", tmp_path / "t.jpg")
    assert img.size == (1280, 720) and (tmp_path / "t.jpg").exists()
    arr = np.asarray(img, dtype=np.int16)
    green = (abs(arr[..., 0] - 31) < 25) & (abs(arr[..., 1] - 138) < 25) & (abs(arr[..., 2] - 76) < 25)
    gold = (abs(arr[..., 0] - 224) < 25) & (abs(arr[..., 1] - 165) < 25) & (abs(arr[..., 2] - 38) < 30)
    grey = (abs(arr[..., 0] - 150) < 12) & (abs(arr[..., 1] - 150) < 12) & (abs(arr[..., 2] - 146) < 12)
    assert green.sum() > 2000 and gold.sum() > 100 and grey.sum() > 200   # sweater/spike, gold dot, history line


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_style_samples_and_telegram_approval(settings, store, tmp_path, monkeypatch):
    from glivarao.publish.telegram import TelegramClient, poll_decisions
    from glivarao.studio import style_samples as S
    from tests.conftest import FakeTelegramSession

    monkeypatch.setattr(S, "motion_sample", lambda dst, seconds=14.0: (dst.write_bytes(b"mp4"), dst)[1])
    res = S.make(tmp_path / "samples")
    assert len(res["frames"]) == 3 and len(res["thumbs"]) == 3 and res["reference"].exists()
    assert {p.name for p in res["frames"]} == {"frame_1.png", "frame_2.png", "frame_3.png"}
    s = replace(settings, telegram_bot_token="T", telegram_approver_chat_id="42",
                doodle_ref_path=str(tmp_path / "ref.png"))
    tg = FakeTelegramSession()
    client = TelegramClient("T", session=tg)
    S.send(s, res, client)
    methods = [m for m, _ in tg.calls]
    assert methods.count("sendMediaGroup") == 2 and "sendVideo" in methods and "sendPhoto" in methods
    buttons = tg.calls[-1][1]["reply_markup"]
    assert "style:doodle-v1" in str(buttons) and "styleedit" in str(buttons)
    env = tmp_path / ".env"
    env.write_text("GLIVARAO_THEME=editorial\n")
    monkeypatch.setenv("ENV_FILE", str(env))
    assert not S.approved(store)
    tg.updates = [{"update_id": 1, "callback_query": {"id": "c", "from": {"id": 42}, "data": "style:doodle-v1",
                                                      "message": {"chat": {"id": 42}}}}]
    poll_decisions(store, s, client)
    assert S.approved(store) and "GLIVARAO_THEME=doodle" in env.read_text()
    assert Path(s.doodle_ref_path).exists() and any("still PAUSED" in json.dumps(c[1]) for c in tg.calls)


def test_doodle_ai_prompts_use_the_doodle_max_and_style(settings, tmp_path):
    from glivarao.art import ai_visuals as V

    sc = Scene(heading="Bank failures", narration="What happens when a bank fails.")
    p = V.scene_prompt(sc, True, "doodle")
    assert "doodle" in p and "#1f8a4c" in p and "round glasses" in p and "no real people" in p
    s = replace(settings, theme="doodle", doodle_ref_path=str(tmp_path / "ref.png"))
    assert V.reference_sheet(s)[:8] == b"\x89PNG\r\n\x1a\n" and (tmp_path / "ref.png").exists()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_render_animated_in_doodle_theme(settings, tmp_path):
    from glivarao.render.animated import render_animated
    from glivarao.render.video import probe

    data = json.loads(Path("config/samples/sample_60s.json").read_text())
    data["scenes"] = data["scenes"][2:4]
    script = Script.model_validate(data)
    res = render_animated(script, tmp_path / "dd", replace(settings, theme="doodle"), workers=2)
    info = probe(res.video)
    assert (info["width"], info["height"]) == (1920, 1080) and abs(info["duration"] - res.duration) < 0.3
