"""End-to-end dry run of tonight's videos with the REAL pipeline: real launch-list fact sheets (+ fact library),
real fact check / compliance / sponsor / evergreen checks, real Shorts length rules (voiced and measured with
ffprobe before rendering), real thumbnails and metadata. Simulated: Claude (writes like a real script that follows
the fact-sheet rules), the Gemini voice (speech at ~165 spoken words/min), the frame renderer and Telegram.

Videos: launch #1 Short, launch #1 long, launch #2 (ACA) long + 3 Shorts (the 4 rejected ones)."""
import base64
import json
import random
import re
import shutil
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from glivarao import daily_v2
from glivarao.studio import launch_plan
from glivarao.tts.gemini_tts import spoken_words

REAL_VOICE_SECONDS = daily_v2._voice_seconds          # conftest replaces it with an estimate; we want the real one
pytestmark = pytest.mark.skipif(not shutil.which("ffprobe"), reason="needs ffmpeg/ffprobe")

A = ["You", "Maybe you", "Most likely you", "If you're busy, you", "Like most people, you", "Some months you",
     "On a tight month you", "Without a plan you", "Once in a while you", "When money's tight you", "Sometimes you",
     "Honestly, you", "Right after payday you", "Like a lot of us, you", "Late at night you", "On autopilot you",
     "Without noticing, you", "In a rush you", "When you're tired, you", "Every so often you"]
B = ["look at the monthly number first", "skip the fine print on the statement", "assume the bank will warn them",
     "treat the balance as a fixed bill", "pay whatever feels comfortable that month", "forget how fees stack up",
     "compare offers only by the headline", "put off the hard decision", "follow what friends do",
     "trust the default option", "focus on the next paycheck", "ignore the yearly total",
     "react after a surprise bill arrives", "never read the renewal notice", "underestimate small recurring costs",
     "keep the oldest account open", "split payments across several apps", "set one reminder and hope",
     "avoid opening the mail", "try to fix everything at once"]
C = ["and that habit quietly costs you over time", "which is exactly how the gap keeps growing",
     "so the real cost stays hidden", "and the plan falls apart by spring", "which makes the next step harder",
     "so a simple checklist helps", "and that is the part we can change", "which is why a written plan matters",
     "so it pays to slow down for ten minutes", "and a calm routine beats a burst of effort",
     "which turns a small problem into a big one", "so the fix starts with one clear number",
     "and the good news is it is easy to reverse", "which is where a little structure goes a long way",
     "so the first move is just to look", "and that is why we keep it practical", "so it helps to write it down",
     "and the habit is easy to build", "which is the whole point of a plan", "so let's make it concrete"]


LOOPS = ["But here's the part most people miss.", "Stick with me, because this is where it gets expensive.",
         "So what does that cost you?", "Wait, it gets worse.", "Here's the catch.", "You might think that's fine.",
         "Now here's the twist.", "Keep that in mind for a minute."]


def _filler(rng, n_words, used, loop_every=60):
    """Short spoken sentences to 'you', with an open loop / pattern interrupt about every 40 seconds."""
    out, since = [], 0
    while sum(len(s.split()) for s in out) < n_words:
        s = f"{rng.choice(A)} {rng.choice(B)}, {rng.choice(C)}."
        if s not in used:
            used.add(s)
            out.append(s)
            since += len(s.split())
            if since >= loop_every:
                out.append(rng.choice(LOOPS))
                since = 0
    return " ".join(out)


def _facts(prompt):
    return [ln for ln in prompt.splitlines() if ln.startswith("- [DATA]") or ln.startswith("- [CALCULATION]")]


def fake_claude(prompt, fmt, seed):
    """A script the way Claude writes it under the rules: fact-sheet numbers, labeled examples, charts only from
    fact-sheet data, closing 'What to do', disclaimer."""
    rng = random.Random(seed)
    used: set = set()
    aca = "15,960" in prompt
    card = "22.36%" in prompt
    m = re.search(r"HOOK TYPE for this video: (\w+)", prompt)
    kinds = ("number", "mistake", "question", "myth", "story", "comparison", "warning")
    hk = m.group(1) if m else kinds[seed % 7]
    prev_hooks = {a or b for a, b in re.findall(r"previous video used '(\w+)'|previous video \((\w+)\)", prompt)}
    while hk in prev_hooks:                              # like Claude: never the previous video's hook type
        hk = kinds[(kinds.index(hk) + 1) % 7] if hk in kinds else kinds[0]
    avoid = set(re.findall(r'ended with: \\?"([^"\\]+)', prompt)) | \
        set(re.findall(r'same ending line as the previous video: \\?"([^"\\]+)', prompt))

    def pick(options):                                   # like Claude: never the previous video's ending line
        ok = [o for o in options if not any(o.startswith(a.rstrip(".")[:30]) for a in avoid)] or list(options)
        return ok[seed % len(ok)]
    special, charts = [], {}
    if aca:
        special = [{"question": "Miss December 15 and you start January without coverage?",
                    "warning": "Don't miss December 15, or you start January without coverage.",
                    "story": "You miss December 15 and you start January without coverage.",
                    "myth": "You think January is fine, but miss December 15 and you lose coverage.",
                    "comparison": "December 15 versus January 1: miss it and you go without coverage.",
                    "mistake": "Miss December 15 and you start January without coverage, a costly mistake.",
                    }.get(hk, "Miss December 15 and you start January without coverage.") if fmt == "short" else
                   {"question": "Miss December 15, and will your Marketplace plan start on January 1?",
                    "warning": "Don't miss December 15, or your Marketplace plan won't start on January 1.",
                    "mistake": "Missing December 15 is a costly mistake: your plan won't start on January 1.",
                    "myth": "You think January is fine, but miss December 15 and your plan won't start.",
                    "story": "You open the Marketplace on December 16, and your plan won't start January 1.",
                    "comparison": "December 15 versus January 1: miss it and your plan won't start on time.",
                    }.get(hk, "Miss December 15, and your Marketplace plan won't start on January 1."),
                   "With income between 100% and 400% of the federal poverty level you qualify for the premium tax "
                   "credit.",
                   "The 2026 poverty guideline is $15,960 for one person and $33,000 for a family of four.",
                   "Say, with made-up numbers, two plans differ by $50 a month. Over a year, that's $600."]
        charts = {1: {"kind": "bar_compare", "title": "2026 federal poverty guideline", "labels": ["1", "2", "3", "4"],
                      "values": [15960, 21640, 27320, 33000], "unit": "$", "source": "HHS poverty guidelines (ASPE)"},
                  2: {"kind": "bar_compare", "title": "Income line for premium tax credits",
                      "labels": ["1 person", "family of 4"], "values": [63840, 132000], "unit": "$",
                      "source": "HealthCare.gov"}}
    elif card:
        calc = [float(x.replace(",", "")) for x in re.findall(r"total interest \$([\d,]+(?:\.\d+)?)", prompt)]
        special = [{"number": "Your card could be charging you 22.36% a year.",
                    "mistake": "Your card mistake costs you 22.36% a year.",
                    "question": "Is your card really charging you 22.36%?",
                    "myth": "You think your card rate is low, but it is 22.36%.",
                    "story": "You open your card statement and see 22.36%.",
                    "comparison": "Your card costs 22.36%, far more than savings pay you.",
                    "warning": "Don't ignore your card rate: it costs you 22.36%."}[hk] if fmt == "short" else
                   {"number": "As of November 2026, your card balance probably costs you 22.36% a year.",
                    "mistake": "Your card mistake costs you 22.36% a year, as of November 2026.",
                    "question": "Is your card balance really costing you 22.36% a year?",
                    "myth": "You think your card rate is fine, but as of November 2026 it averaged 22.36%.",
                    "story": "You open your card statement and the rate says 22.36% a year.",
                    "comparison": "Your card costs you 22.36% a year, far more than your savings earn.",
                    "warning": "Don't ignore your card rate: it averaged 22.36% a year."}[hk]]
        if len(calc) >= 2:
            special.append(f"For example, if you owe $5,000 at 22.36% and pay only the minimum, you'd pay about "
                           f"${round(calc[0]):,} in interest.")
            charts = {1: {"kind": "bar_compare", "title": "Total interest on $5,000 (example)",
                          "labels": ["Minimum only", "$200 a month"], "values": [round(calc[0]), round(calc[1])],
                          "unit": "$", "source": "Calculated example"}}
    n_sc, per = (26, 108) if fmt == "long" else (5, 14)
    scenes = []
    for i in range(n_sc):
        head = "What to do" if i == n_sc - 2 else ("The hook" if i == 0 else f"Part {i}")
        text = (special[i % len(special)] + " " if i < len(special) + 1 and special and i > 0 else "")
        if i == 0:
            text = special[0] + " " if special else ""
        body = _filler(rng, per, used) if fmt == "long" or i not in (0,) else ""
        narr = (text + body).strip() or _filler(rng, per, used)
        if i == 0 and fmt == "long":   # 0-5 s hook, 5-15 s what it costs you, 15-30 s promise + open loop
            narr = ((special[0] if special else "You're making a costly money mistake every single month.") +
                    " That costs you real money in interest, every single month, for years." +
                    " Most people never check the one statement line that shows it, so it keeps growing quietly." +
                    " By the end, you'll know the one move that stops it, and here's the part most people miss. " +
                    _filler(rng, per - 60, used))
        if i == n_sc - 1:
            narr = (pick(["Today, set one automatic payment above the minimum.",
                                "Today, open your statement and find your rate.",
                                "This week, move one payment date to right after payday.",
                                "Tonight, write down every balance and its rate.",
                                "Today, call your card company and ask for a lower rate.",
                                "This weekend, list your bills from the highest rate down.",
                                "Today, turn on alerts for every payment due date."]) +
                    " This video is for education only and isn't financial advice.")
        ch = charts.get(i, {"kind": "none", "title": "", "labels": [], "values": [], "unit": "",
                            "source": "Illustrative example"})
        scenes.append({"heading": head, "narration": narr, "character": "max", "pose": "talk",
                       "illustration": "credit_card", "chart": {**{"params": {"principal": 0, "rate": 0, "years": 0,
                                                                              "monthly": 0}}, **ch},
                       "key_points": [], "set": "auto", "entrance": "auto", "transition": "auto", "money_fx": "auto",
                       "beat": "none"})
    if fmt == "short":   # Shorts: hook with a fact, the labeled example, chart, what to do, sign-off
        scenes[0]["narration"] = (special[0] if special else "You're making a costly money mistake.") + \
            " Here's what that means for your budget."
        scenes[1]["narration"] = (special[-1] if len(special) > 1 else _filler(rng, 14, used))
        scenes[2]["narration"] = ("That gap adds up fast, so it pays to check the numbers once a year and keep a "
                                  "short note of what you pay.")
        scenes[3]["narration"] = ("Check your plan, set one reminder, and compare two options side by side before you "
                                  "decide anything.")
        scenes[4]["narration"] = (pick(["Do one thing today: check your number.", "Check that rate tonight.",
                                              "Write your number down today.", "Look at your statement today.",
                                              "Set one reminder today.", "Ask about your rate this week.",
                                              "Compare your number with this one today."]) +
                                  " This video is for education only and isn't financial advice. " +
                                  pick(["Now look at that first number again.", "So, back to that first number.",
                                              "Which brings us back to the start.", "Now hear that number again.",
                                              "Remember the very first thing I said?", "So look again at the top.",
                                              "And that's why it starts the way it does."]))      # loop line last
    title, thumb = (("Credit Card Interest: What 22.36% Costs You", "Your Card Rate") if card else
                    ("ACA Deadline: Miss December 15, Pay More", "Miss December 15") if aca else
                    ("Your Money Mistake: The Plain Truth", "Money Mistake"))
    return {"title": title, "description": "A clear guide.", "tags": ["money"],
            "thumbnail_text": thumb, "hook": scenes[0]["narration"][:80], "scenes": scenes}


class FakeGeminiVoice:
    """~165 spoken words/min with short pauses, like the real Charon voice."""

    def post(self, url, headers=None, json=None, timeout=None):
        prompt = json["contents"][0]["parts"][0]["text"]
        text = prompt.split("TRANSCRIPT:\n")[-1] if "TRANSCRIPT:" in prompt else prompt.split("\n\n", 1)[-1]
        sec = max(0.8, spoken_words(text) / 165 * 60)
        sr = 24000
        a = (0.3 * np.sin(np.linspace(0, 2 * np.pi * 140 * sec, int(sec * sr)))).astype(np.float32)
        pcm = (a * 32767).astype("<i2")
        body = {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "audio/L16;rate=24000", "data": base64.b64encode(pcm.tobytes()).decode()}}]}}],
                "usageMetadata": {"candidatesTokenCount": int(sec * 25)}}
        return type("R", (), {"status_code": 200, "json": lambda s: body})()


@pytest.fixture
def world(settings, store, monkeypatch, tmp_path):
    from glivarao.scriptgen import claude as C
    import glivarao.render.animated as anim

    s = replace(settings, mode="production", allow_paid_apis=True, writer="claude_openrouter", tts_provider="gemini_tts",
                gemini_api_key="K", tts_cache_dir=str(tmp_path / "tts"), tts_spend_ledger_path=str(tmp_path / "t.json"),
                claude_spend_ledger_path=str(tmp_path / "c.json"), image_provider="none")
    calls = []

    def ask(settings_, prompt, fmt, client=None, ledger=None):
        calls.append((fmt, prompt[:60]))
        return fake_claude(prompt, fmt, len(calls))

    monkeypatch.setattr(C, "_ask", ask)
    monkeypatch.setattr("glivarao.tts.gemini_tts.requests.Session", lambda: FakeGeminiVoice())
    monkeypatch.setattr(daily_v2, "_voice_seconds", REAL_VOICE_SECONDS)
    monkeypatch.setattr(launch_plan, "verify_facts", lambda v, session=None: (v.facts, []))   # offline in CI
    monkeypatch.setattr("glivarao.studio.fact_library.verify_brief", lambda b, session=None: [])

    def fake_render(script, out, st, voice=None, workers=None, tempo_boost=1.0):
        out.mkdir(parents=True, exist_ok=True)
        secs = REAL_VOICE_SECONDS(script, st, out, tempo_boost) + 0.6 * len(script.scenes)
        (out / "video.mp4").write_bytes(b"0")
        (out / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n")
        return SimpleNamespace(video=out / "video.mp4", srt=out / "captions.srt", duration=secs, render_seconds=1.0,
                               unknown_words=[], voice="Gemini TTS Charon", scene_starts=[0.0] * len(script.scenes))

    monkeypatch.setattr(anim, "render_animated", fake_render)
    monkeypatch.setattr(daily_v2, "_notify", lambda st, t: None)
    store.kv_set("launch_done", "[]")
    return s, store, calls


def _report(r, s):
    out = []
    for j in r.jobs:
        d = s.output_dir / j[0]
        comp = (d / "compliance.txt").read_text() if (d / "compliance.txt").exists() else ""
        out.append((j[0], j[1], j[2], j[4], [ln for ln in comp.splitlines() if ln.startswith("ERROR")]))
    return out


def test_tonight_launch_1_short_and_long(world):
    s, store, calls = world
    for short in (True, False):
        r = daily_v2.make_now(s, store, 1, short=short, send=False)
        rep = _report(r, s)
        assert rep and rep[-1][2] == "rendered", json.dumps(rep, indent=1)
        if short:
            meta = json.loads((s.output_dir / rep[-1][0] / "metadata.json").read_text())
            job = store.get(rep[-1][0])
            assert 30 <= job.duration_sec <= 59, job.duration_sec              # Shorts length rules
            assert "[AFFILIATE:" in json.loads((s.output_dir / rep[-1][0] / "script.json").read_text())["description"]
            assert meta["affiliate_category"] == "debt payoff"
    assert launch_plan.done(store) == [1]


def _old_rejected(s, store, fmt, n_short=0):
    """A video as the OLD code left it on the server: old fact sheet (no fact library), Claude's own numbers,
    rejected by compliance."""
    from datetime import date

    from glivarao.content.brief import build_brief
    from glivarao.models import JobStatus, Script

    v = launch_plan.LAUNCH[1]
    b = build_brief(v.card(), date.today())
    b.facts = [f for f in b.facts if "15,960" not in f.text and "5,680" not in f.text]     # old sheet
    d = fake_claude("no facts", fmt, 100 + n_short)
    if fmt == "short":
        d["scenes"][1]["narration"] = "Say, with made-up numbers, two plans differ by $50 a month. Over a year, that's $600."
        d["scenes"][2]["chart"] = {"kind": "bar_compare", "title": "Income line by household size",
                                   "labels": ["1", "2", "3"], "values": [58000, 79000, 99800], "unit": "$",
                                   "source": "Claude", "params": {}}
    from glivarao.scriptgen.prompts import normalize_direction

    d["scenes"] = [normalize_direction(sc) for sc in d["scenes"]]
    script = Script.model_validate({**d, "format": fmt, "topic": v.topic})
    job = store.create(fmt, v.topic)
    out = s.output_dir / job.id
    out.mkdir(parents=True)
    (out / "brief.json").write_text(b.to_json())
    job.script_path = str(out / "script.json")
    (out / "script.json").write_text(script.model_dump_json())
    (out / "compliance.txt").write_text("ERROR: 2 claim(s) without a source URL: Chart: Income line by household size")
    store.transition(job, JobStatus.SCRIPTED, "old")
    store.transition(store.get(job.id), JobStatus.REJECTED_COMPLIANCE, "old")
    return job.id


def test_tonight_aca_long_and_three_shorts(world):
    """launch #2 (ACA) made fresh, and the 4 ACA videos the old code rejected, retried with retry-rejected."""
    s, store, calls = world
    r = daily_v2.make_now(s, store, 2, send=False)
    rep = _report(r, s)
    assert rep and rep[-1][2] == "rendered", json.dumps(rep, indent=1)
    fc = (s.output_dir / rep[-1][0] / "fact_check.md").read_text()
    assert "aspe.hhs.gov" in fc and "NO SOURCE" not in fc
    old = [_old_rejected(s, store, "long")] + [_old_rejected(s, store, "short", k) for k in range(3)]
    jobs = daily_v2.retry_rejected(s, store, send=False)
    assert len(jobs) == 4 and all(j[2] == "rendered" for j in jobs), json.dumps(jobs, indent=1)
    shorts = [store.get(j[0]) for j in jobs if j[1] == "short"]
    assert len(shorts) == 3 and all(30 <= j.duration_sec <= 59 for j in shorts), [j.duration_sec for j in shorts]
    assert all(store.get(o).status.value == "rejected_compliance" for o in old)      # old drafts never sent
