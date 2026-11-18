"""Human-in-the-loop production: topic picks, creator input, formats, anti-repetition, fact check, pace,
Shorts, AI disclosure. Telegram is simulated; nothing is uploaded; no paid API is called."""
import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from glivarao.content.brief import build_brief
from glivarao.content.format_writer import write_long_format, write_shorts_format
from glivarao.studio import bot, disclosure, factcheck, originality
from glivarao.studio.formats import FORMATS, choose_format, eligible
from glivarao.studio.queue import TopicQueue
from tests.test_content_audio_daily import card

DAY = date(2026, 11, 18)   # a Wednesday
TAKE = "I paid only the minimum for two years in my twenties. It felt fine until I saw how little the balance moved."


class FakeTG:
    """Records Bot API calls; returns message ids."""

    def __init__(self):
        self.calls, self.n = [], 100

    def call(self, method, files=None, **params):
        self.calls.append((method, params))
        if method == "getFile":
            return {"file_path": "voice/file_1.oga"}
        self.n += 1
        return {"message_id": self.n}

    def download(self, file_path, dst):
        Path(dst).write_bytes(b"OggS")
        return Path(dst)

    def texts(self):
        return [p.get("text", "") for m, p in self.calls if m == "sendMessage"]


def tg_settings(settings, **kw):
    return replace(settings, telegram_bot_token="T", telegram_approver_chat_id="42", **kw)


def brief():
    return build_brief(card(), DAY)


# ---------------------------------------------------------------- 1 + 2: topics by you, your input
def test_ideas_pick_input_flow(settings, store):
    s = tg_settings(settings)
    q = TopicQueue(store)
    items = q.add_proposals([card(), card("mortgage", "Mortgages", "Credit and Debt")], DAY)
    tg = FakeTG()
    bot.send_proposals(items, s, tg, store)
    buttons = [p["reply_markup"]["inline_keyboard"][0] for m, p in tg.calls if p.get("reply_markup")]
    assert len(buttons) == 2 and buttons[0][0]["callback_data"] == f"pick:{items[0].id}"
    # tap "Make this"
    assert bot.handle_callback({"id": "c1", "data": f"pick:{items[0].id}"}, store, s, tg, DAY) == "picked"
    it = q.get(items[0].id)
    assert it.status == "awaiting_input" and it.format in FORMATS and it.input_msg_id
    assert "YOUR take" in tg.texts()[-1]
    # reply with text -> ready
    assert bot.handle_message({"text": TAKE, "reply_to_message": {"message_id": it.input_msg_id}}, store, s, tg) == "saved"
    assert q.get(it.id).status == "ready" and q.get(it.id).creator_input == TAKE
    # skip the second idea
    bot.handle_callback({"id": "c2", "data": f"drop:{items[1].id}"}, store, s, tg, DAY)
    assert q.get(items[1].id).status == "dropped"
    assert "Ready" in q.status_text()


def test_voice_note_is_transcribed(settings, store, tmp_path):
    s = tg_settings(settings)
    q = TopicQueue(store)
    it = q.add_proposals([card()], DAY)[0]
    q.pick(it.id, "explainer")
    tg = FakeTG()
    heard = lambda path, settings: ("When I was in college I carried a balance for years.", "test")  # noqa: E731
    r = bot.handle_message({"message_id": 7, "voice": {"file_id": "abc"}}, store, s, tg, workdir=tmp_path,
                           transcriber=heard)
    assert r == "saved" and q.get(it.id).input_kind == "voice" and "I heard" in tg.texts()[-1]
    none = lambda path, settings: (None, "none")  # noqa: E731
    q.update(it.id, status="awaiting_input", creator_input="")
    assert bot.handle_message({"message_id": 8, "voice": {"file_id": "x"}}, store, s, tg, workdir=tmp_path,
                              transcriber=none) == "voice_untranscribed"


def test_telegram_routing_and_unauthorized(settings, store):
    from glivarao.publish import telegram

    s = tg_settings(settings)
    q = TopicQueue(store)
    it = q.add_proposals([card()], DAY)[0]
    updates = [{"update_id": 1, "callback_query": {"id": "a", "from": {"id": 42}, "message": {"chat": {"id": 42}},
                                                   "data": f"pick:{it.id}"}},
               {"update_id": 2, "message": {"from": {"id": 666}, "chat": {"id": 666}, "text": "hijack"}},
               {"update_id": 3, "message": {"from": {"id": 42}, "chat": {"id": 42}, "text": TAKE}}]

    class C(FakeTG):
        def call(self, method, files=None, **params):
            if method == "getUpdates":
                return updates
            return super().call(method, files, **params)

    telegram.poll_decisions(store, s, client=C())
    got = q.get(it.id)
    assert got.status == "ready" and got.creator_input == TAKE  # the stranger's text was ignored


# ---------------------------------------------------------------- 3: formats
def test_every_format_has_its_own_structure_and_opening():
    b = brief()
    assert set(eligible(b)) == set(FORMATS)
    scripts = {k: write_long_format(b, k, TAKE) for k in FORMATS}
    structures = {k: tuple(originality.structure_of(s)) for k, s in scripts.items()}
    assert len(set(structures.values())) == len(FORMATS)          # all different structures
    assert len({s.hook for s in scripts.values()}) == len(FORMATS)  # all different openings
    assert len({s.scenes[-1].narration for s in scripts.values()}) == len(FORMATS)  # different closings
    for s in scripts.values():
        assert sum(x.beat == "creator" for x in s.scenes) == 1 and "two years in my twenties" in \
            next(x.narration for x in s.scenes if x.beat == "creator")


def test_rotation_never_repeats_last_and_prefers_least_recent():
    b = brief()
    assert choose_format(b, ["explainer"]) != "explainer"
    hist = ["myth_vs_fact", "case_study", "viewer_question", "comparison", "news_breakdown"]
    assert choose_format(b, hist) == "explainer"
    seq, h = [], []
    for _ in range(12):
        f = choose_format(b, h)
        h.append(f)
        seq.append(f)
    assert all(a != b2 for a, b2 in zip(seq, seq[1:])) and len(set(seq)) >= 5


def test_openings_rotate_away_from_recent_lines():
    b = brief()
    first = write_long_format(b, "explainer")
    again = write_long_format(b, "explainer", used_lines=[first.hook, first.scenes[-1].narration])
    assert again.hook != first.hook


# ---------------------------------------------------------------- 4: anti-repetition
def test_similarity_detects_repeats_and_accepts_new_work(store):
    b = brief()
    a = write_long_format(b, "explainer", TAKE)
    originality.record(store, a, b.topic_key, DAY - timedelta(days=7))
    hist = originality.load_history(store)
    same = originality.check(a, b.topic_key, hist, DAY)
    assert not same.ok and same.phrase_overlap > 0.9 and any("same topic" in r for r in same.reasons)
    other = build_brief(card("mortgage", "Mortgages"), DAY)
    fresh = originality.check(write_long_format(other, "myth_vs_fact", "My own mortgage story."), other.topic_key,
                              hist, DAY)
    assert fresh.ok, fresh.reasons


def test_creator_words_and_disclaimer_do_not_count_as_repetition():
    b = brief()
    s = write_long_format(b, "explainer", TAKE)
    assert "two years in my twenties" not in originality.narration_for_check(s)


# ---------------------------------------------------------------- 5: fact check
def test_fact_check_lists_every_number_with_source():
    b = brief()
    s = write_long_format(b, "news_breakdown", "I once paid 18% on a store card.")
    claims = factcheck.check_claims(s, b, "I once paid 18% on a store card.")
    assert any(c.status == "source" and c.url == "https://www.consumerfinance.gov/x" for c in claims)
    assert any(c.status == "calculation" for c in claims) and any(c.status == "creator" for c in claims)
    assert not [c for c in claims if c.status == "UNSOURCED"]
    desc = factcheck.add_sources_to_description("Intro.", claims)
    assert "https://www.consumerfinance.gov/x" in desc


def test_fact_check_flags_unsourced_numbers():
    b = brief()
    s = write_long_format(b, "explainer")
    bad = s.scenes[1].model_copy(update={"narration": "About 73% of Americans have a credit card."})
    s = s.model_copy(update={"scenes": [s.scenes[0], bad] + s.scenes[2:]})
    claims = factcheck.check_claims(s, b)
    assert any(c.status == "UNSOURCED" and "73%" in c.text for c in claims)
    assert "NO SOURCE" in factcheck.report(claims)


# ---------------------------------------------------------------- 6: Shorts
def test_shorts_have_their_own_hook_and_point():
    b = brief()
    long = write_long_format(b, "myth_vs_fact")
    shorts = write_shorts_format(b, "myth_vs_fact", n=2)
    assert len(shorts) == 2 and len({s.style for s in shorts}) == 2
    assert all(s.style != "short_myth" for s in shorts)             # not the long video's device
    assert long.hook not in {s.hook for s in shorts} and shorts[0].hook != shorts[1].hook
    assert all(90 <= s.word_count <= 160 for s in shorts)


# ---------------------------------------------------------------- 7: pace + 1/2 in the daily run
def _stub_render(monkeypatch):
    import glivarao.render.animated as anim
    import glivarao.render.thumbnail_editorial as te

    def fake_render(script, out, s, voice=None, workers=None):
        out.mkdir(parents=True, exist_ok=True)
        (out / "video.mp4").write_bytes(b"0")
        (out / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n")
        return SimpleNamespace(video=out / "video.mp4", srt=out / "captions.srt", duration=60.0, render_seconds=1.0,
                               unknown_words=[], voice="Kokoro am_michael",
                               scene_starts=[i * 15.0 for i in range(len(script.scenes))])

    monkeypatch.setattr(anim, "render_animated", fake_render)
    monkeypatch.setattr(te, "make_thumbnail", lambda sc, dst, portrait=False, theme="": (dst.write_bytes(b"j"), dst)[1])


def test_daily_run_uses_only_your_picked_topics_with_your_input(settings, store, tmp_path, monkeypatch):
    from glivarao.daily_v2 import run_daily_v2

    _stub_render(monkeypatch)
    rdir = tmp_path / "r"
    rdir.mkdir()
    q = TopicQueue(store)
    it = q.add_proposals([card()], DAY)[0]
    q.pick(it.id, "case_study")
    res = run_daily_v2(settings, store, today=DAY, research_dir=rdir, send=False)
    assert res.jobs == [] and "Waiting for your take" in res.note       # no input -> nothing is made
    q.add_input(it.id, TAKE)
    res = run_daily_v2(settings, store, today=DAY, research_dir=rdir, send=False)
    assert [j[1] for j in res.jobs] == ["long", "short", "short"] and all(j[2] == "rendered" for j in res.jobs)
    out = settings.output_dir / res.jobs[0][0]
    meta = json.loads((out / "metadata.json").read_text())
    assert meta["format"] == "case_study" and meta["creator_input"] == TAKE and meta["picked_by_you"]
    assert meta["youtube_altered_content"] is False and meta["fact_check"]["UNSOURCED"] == 0
    assert "AI-generated voice" in meta["description"] and "consumerfinance.gov" in meta["description"]
    assert (out / "fact_check.md").exists()
    script = json.loads((out / "script.json").read_text())
    assert any(s.get("beat") == "creator" for s in script["scenes"])
    assert q.get(it.id).status == "produced"
    # pace: the next day is too soon (minimum gap 2 days)
    it2 = q.add_proposals([card("mortgage", "Mortgages")], DAY)[0]
    q.pick(it2.id, "explainer")
    q.add_input(it2.id, "My own mortgage story.")
    res = run_daily_v2(settings, store, today=DAY + timedelta(days=1), research_dir=rdir, send=False)
    assert res.jobs == [] and "day(s) ago" in res.note


def test_pace_weekly_quota(settings, store):
    from glivarao.daily_v2 import pace_check

    s = replace(settings, long_videos_per_week=3, min_days_between_long=0)
    monday = date(2026, 11, 16)
    store.kv_set("long_dates", json.dumps([str(monday), str(monday + timedelta(days=2)), str(monday + timedelta(days=4))]))
    ok, why = pace_check(store, monday + timedelta(days=5), s)
    assert not ok and "3/3" in why
    assert pace_check(store, monday + timedelta(days=7), s)[0]  # new week


def test_supervised_run_does_not_mark_day_done_when_nothing_was_made(settings, store, monkeypatch):
    import glivarao.daily_v2 as d

    monkeypatch.setattr(d, "run_daily_v2", lambda *a, **k: d.DailyResult("", "waiting", note="waiting"))
    d.supervised_daily(settings, store, today=DAY, notifier=lambda *a: None)
    assert not store.kv_get(f"daily_done:{DAY}")


# ---------------------------------------------------------------- 8: AI disclosure
def test_disclosure_rules():
    d = disclosure.disclosure_for("Kokoro am_michael")
    assert d.youtube_altered_content is False and any("TikTok" in n for n in d.platform_notes)
    assert "AI-generated voice" in d.description_note
    assert disclosure.disclosure_for("x", realistic_ai_visuals=True).youtube_altered_content is True
    assert disclosure.disclosure_for("x", real_person_voice=True).youtube_altered_content is True


def test_upload_body_uses_saved_disclosure_and_stays_private(settings, tmp_path):
    from glivarao.models import Job
    from glivarao.publish import youtube

    out = tmp_path / "job"
    out.mkdir()
    (out / "metadata.json").write_text(json.dumps({"youtube_altered_content": False}))
    job = Job(id="j1", format="long", topic="t", created_at="x", updated_at="x", video_path=str(out / "video.mp4"))
    assert youtube._altered_flag(job) is False
    s = write_long_format(brief(), "explainer")
    body = youtube.build_metadata(s, settings, altered_content=False)
    assert body["status"]["containsSyntheticMedia"] is False and body["status"]["privacyStatus"] == "private"
    assert "publishAt" not in body["status"]
    (out / "metadata.json").unlink()
    assert youtube._altered_flag(job) is True  # unknown -> disclose


def test_claude_prompt_carries_format_your_take_and_banned_openings(settings, tmp_path, monkeypatch):
    import glivarao.scriptgen.claude as cl
    from glivarao.content.writer import write_with_claude
    from tests.test_production_hardening import FakeClaude, script_json

    s = replace(settings, allow_paid_apis=True, anthropic_api_key="x",
                claude_spend_ledger_path=str(tmp_path / "c.json"))
    fake = FakeClaude([script_json(25, 100), script_json(25, 100)])
    monkeypatch.setattr(cl.anthropic, "Anthropic", lambda api_key=None: fake)
    out = write_with_claude(brief(), "long", s, style="myth_vs_fact", creator_text=TAKE,
                            avoid_lines=["Old opening line."])
    prompt = fake.calls[0]["messages"][0]["content"]
    assert "Myth vs Fact" in prompt and "two years in my twenties" in prompt and "Old opening line." in prompt
    assert out.style == "myth_vs_fact"
    rewritten = cl.rewrite_for_originality(out, ["too similar"], ["a repeated phrase here"], s)
    assert "a repeated phrase here" in fake.calls[1]["messages"][0]["content"] and rewritten.style == "myth_vs_fact"


def test_numbered_labels_are_not_claims():
    assert factcheck.numbers_in("Myth number 2: carrying a balance helps your score.") == []
    assert factcheck.numbers_in("Step 3 costs $8,887.") == [8887.0]
    s = write_long_format(brief(), "myth_vs_fact")
    assert "Myth number two" in " ".join(x.narration for x in s.scenes)
