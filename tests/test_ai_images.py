"""Nano Banana 2.1 images (simulated API, no paid call): thumbnails x3 with our own bold words, 10-20 scene
illustrations with the character reference, $15 cap with 80% alert, code-drawn fallback, Telegram pick."""
import base64
import io
import json
from dataclasses import replace
from datetime import date

import pytest
from PIL import Image

from glivarao.art import ai_visuals as AV
from glivarao.art.gemini_image import GeminiImage, ImageLedger, ImageUnavailable
from glivarao.content.brief import build_brief
from glivarao.content.format_writer import write_long_format
from tests.test_content_audio_daily import card


def _png(color=(200, 80, 60), size=(64, 64)):
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "PNG")
    return base64.b64encode(b.getvalue()).decode()


class FakeImages:
    def __init__(self, status=200):
        self.calls, self.status = [], status

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        st = self.status[min(len(self.calls), len(self.status)) - 1] if isinstance(self.status, list) else self.status
        if st != 200:
            return type("R", (), {"status_code": st, "json": lambda s: {}})()
        body = {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": _png()}}]}}]}
        return type("R", (), {"status_code": 200, "json": lambda s: body})()


@pytest.fixture
def s(settings, tmp_path):
    return replace(settings, allow_paid_apis=True, gemini_api_key="GKEY", image_cache_dir=str(tmp_path / "ic"),
                   image_spend_ledger_path=str(tmp_path / "img.json"),
                   character_ref_path=str(tmp_path / "char" / "reference.png"), image_backoff_sec=0.0)


def long_script():
    b = build_brief(card(), date(2026, 11, 19))
    return write_long_format(b, "explainer")


def test_request_format_cache_and_budget(s, tmp_path):
    fake = FakeImages()
    gi = GeminiImage(s, session=fake, sleep=lambda x: None)
    gi.generate("a piggy bank", "2K", "16:9", [b"REFPNG"])
    c = fake.calls[0]
    assert c["url"].endswith("/models/gemini-nano-banana-2.1:generateContent") and "GKEY" not in c["url"]
    assert c["headers"] == {"x-goog-api-key": "GKEY"}
    cfg = c["json"]["generationConfig"]
    assert cfg["responseModalities"] == ["IMAGE"] and cfg["imageConfig"] == {"aspectRatio": "16:9", "imageSize": "2K"}
    assert c["json"]["contents"][0]["parts"][1]["inlineData"]["mimeType"] == "image/png"   # the reference image
    gi.generate("a piggy bank", "2K", "16:9", [b"REFPNG"])                                # cached: no 2nd charge
    assert len(fake.calls) == 1 and ImageLedger(tmp_path / "img.json").spent() == pytest.approx(0.0504)
    ImageLedger(tmp_path / "img.json").add(14.99, "1K")
    with pytest.raises(ImageUnavailable, match="monthly image budget"):
        gi.generate("another", "1K")


def test_retries_then_unavailable_and_unpinned_model_refused(s):
    ok = FakeImages(status=[503, 429, 200])
    GeminiImage(s, session=ok, sleep=lambda x: None).generate("x", "1K")
    assert len(ok.calls) == 3
    down = FakeImages(status=503)
    with pytest.raises(ImageUnavailable, match="after 4 attempts"):
        GeminiImage(s, session=down, sleep=lambda x: None).generate("y", "1K")
    with pytest.raises(ImageUnavailable, match="not a pinned"):
        GeminiImage(replace(s, image_model="gemini-flash-image-latest"))
    with pytest.raises(ImageUnavailable):
        GeminiImage(replace(s, allow_paid_apis=False))


def test_scene_illustrations_with_character_reference(s, store, tmp_path):
    sc = long_script()
    scenes = (sc.scenes * 4)[:24]
    sc = sc.model_copy(update={"scenes": scenes})
    fake = FakeImages()
    out, stats = AV.illustrate_scenes(sc, tmp_path / "job", s, store, GeminiImage(s, session=fake))
    assert stats["ai"] == 20 and len(fake.calls) <= 20                   # 10-20 per long video (max 20)
    assert sum(1 for x in out.scenes if x.art_path) == 20
    with_ref = [c for c in fake.calls if len(c["json"]["contents"][0]["parts"]) == 2]
    assert with_ref and all("Max" in c["json"]["contents"][0]["parts"][0]["text"] for c in with_ref)
    assert all("No numbers, no words" in c["json"]["contents"][0]["parts"][0]["text"] for c in fake.calls)
    assert store.kv_get("character_ref_sha")                              # one locked reference sheet
    short = sc.model_copy(update={"format": "short"})
    assert AV.illustrate_scenes(short, tmp_path / "j2", s, store)[1]["ai"] == 0       # Shorts: code-drawn


def test_budget_reached_midway_keeps_code_drawn_for_the_rest(s, store, tmp_path):
    ImageLedger(tmp_path / "img.json").add(15 - 0.0336 * 3 - 0.001, "1K")      # room for 3 images
    sc = long_script()
    out, stats = AV.illustrate_scenes(sc, tmp_path / "job", s, store, GeminiImage(s, session=FakeImages()))
    assert stats["ai"] == 3 and "budget" in stats["note"]


def test_three_thumbnail_options_with_our_own_words_and_fallback(s, store, tmp_path):
    sc = long_script()
    paths, how = AV.thumbnail_options(sc, tmp_path, s, store, GeminiImage(s, session=FakeImages()))
    assert len(paths) == 3 and all(p.exists() for p in paths) and all(h.startswith("AI (2K)") for h in how)
    assert Image.open(paths[0]).size == (1280, 720)
    words = AV.bold_words(sc, 3)
    assert len(set(words)) == 3 and all(1 <= len(w.split()) <= 3 for w in words)
    drawn = []
    off = replace(s, allow_paid_apis=False)
    paths, how = AV.thumbnail_options(sc, tmp_path / "f", off, store,
                                      fallback=lambda scr, dst: (drawn.append(scr.thumbnail_text), dst.parent.mkdir(
                                          parents=True, exist_ok=True), Image.new("RGB", (8, 8)).save(dst)))
    assert len(paths) == 3 and all("code-drawn" in h for h in how) and len(set(drawn)) == 3


def test_renderer_uses_ai_art_and_falls_back(s, tmp_path):
    from glivarao.anim.director import plan_scene
    from glivarao.render.editorial import EditorialFrames

    sc = long_script()
    art = tmp_path / "scene_art" / "scene_01.png"
    art.parent.mkdir(parents=True)
    Image.new("RGB", (300, 300), (10, 120, 200)).save(art)
    scenes = list(sc.scenes)
    scenes[1] = scenes[1].model_copy(update={"art_path": str(art)})
    sc = sc.model_copy(update={"scenes": scenes})
    sents = [(0.0, 3.0, scenes[1].narration.split(".")[0] + ".")]
    plan = plan_scene(scenes[1], [], 7.0, 1, [], first=False)
    fr = EditorialFrames(sc, 1, plan, None, sents)
    assert any(b.kind == "plate" for b in fr.beats)
    img = fr._plate_beat(1600, 900, 2.0, False)
    assert img.size == (1600, 900)


def test_telegram_thumbnail_pick(settings, store, tmp_path):
    from glivarao.publish import telegram
    from tests.test_uploadpack import RecTG, approved_job

    s2 = replace(settings, telegram_bot_token="T", telegram_approver_chat_id="42")
    job = approved_job(s2, store, tmp_path)
    out = tmp_path / job.id
    for k in (1, 2, 3):
        Image.new("RGB", (8, 8)).save(out / f"thumbnail_{k}.jpg")
    tg = RecTG()
    telegram.send_thumbnail_picker(job, s2, tg)
    assert sum(1 for m, _ in tg.calls if m == "sendPhoto") == 3
    updates = [{"update_id": 1, "callback_query": {"id": "a", "from": {"id": 42},
                                                   "message": {"message_id": 5, "chat": {"id": 42}},
                                                   "data": f"thumb:{job.id}:2"}}]

    class C(RecTG):
        def call(self, method, files=None, **params):
            return updates if method == "getUpdates" else super().call(method, files, **params)

    telegram.poll_decisions(store, s2, client=C())
    assert store.get(job.id).thumbnail_path.endswith("thumbnail_2.jpg")


def test_image_spend_in_health_alerts(s, store, tmp_path):
    from glivarao.studio import health

    ImageLedger(tmp_path / "img.json").add(12.5, "1K")
    a = health.spend_alerts(s, store)
    assert any("Images (Nano Banana): $12.50 of $15.00" in x for x in a)
