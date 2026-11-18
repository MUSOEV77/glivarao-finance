"""Daily production v2: autonomous research -> topic selection -> brief + fact sheet -> scripts
(1 long + 2 Shorts) -> finance-only and compliance checks -> narration, music, SFX, animation, captions ->
thumbnails + metadata -> Telegram review package.

NEVER uploads, publishes or schedules anything on YouTube. Paid APIs are used only when ALLOW_PAID_APIS=true.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .compliance import check_script
from .config import Settings
from .content.brief import build_brief, pick_card
from .content.packaging import finalize_description
from .content.writer import paid_writer_allowed, write_long_free, write_shorts_free, write_with_claude
from .models import JobStatus, Script
from .research.finance_filter import gate
from .storage import ALLOWED, JobStore

log = logging.getLogger(__name__)
REPEAT_WINDOW_DAYS = 90


@dataclass
class DailyResult:
    topic: str
    writer: str
    jobs: list = field(default_factory=list)  # (job_id, format, status, video_path, note)


def _used_topics(store: JobStore, today: date) -> set[str]:
    hist = json.loads(store.kv_get("used_topics", "[]"))
    cutoff = (today - timedelta(days=REPEAT_WINDOW_DAYS)).isoformat()
    return {h[1] for h in hist if h[0] >= cutoff}  # entries: [date, topic_key] or [date, topic_key, category]


def _recent_categories(store: JobStore, today: date, days: int = 7) -> list[str]:
    hist = json.loads(store.kv_get("used_topics", "[]"))
    cutoff = (today - timedelta(days=days)).isoformat()
    return [h[2] for h in hist if len(h) > 2 and h[0] > cutoff]


def _mark_used(store: JobStore, today: date, key: str, category: str = "") -> None:
    hist = json.loads(store.kv_get("used_topics", "[]"))
    hist.append([today.isoformat(), key, category])
    store.kv_set("used_topics", json.dumps(hist[-500:]))


def finance_only_check(script: Script) -> tuple[bool, str]:
    """Gate 2: the finished script must itself pass the finance-only filter (no politics/news/etc.)."""
    text = " ".join([script.title] + [s.narration for s in script.scenes])
    return gate(text)


def run_daily_v2(settings: Settings, store: JobStore, today: date | None = None, research_dir: Path | None = None,
                 send: bool = True, workers: int | None = None, shorts: int = 2) -> DailyResult:
    from .render.animated import render_animated
    from .render.thumbnail_v3 import make_thumbnail_v3
    from .research.run import run_research

    today = today or date.today()
    research_dir = research_dir or Path("reports/research")
    cached = research_dir / f"{today.isoformat()}.json"
    report = json.loads(cached.read_text()) if cached.exists() else run_research(today, research_dir, store)

    paid = paid_writer_allowed(settings)
    card = pick_card(report, _used_topics(store, today), free_writer=not paid,
                     recent_categories=_recent_categories(store, today))
    if card is None:
        raise RuntimeError("No eligible finance topic found in today's research")
    brief = build_brief(card, today)
    if paid:
        scripts = [write_with_claude(brief, "long", settings)] + \
                  [write_with_claude(brief, "short", settings, angle=a) for a in
                   ("one surprising number from the fact sheet", "the most common mistake")][:shorts]
        writer = "claude"
    else:
        scripts = [write_long_free(brief)] + write_shorts_free(brief)[:shorts]
        writer = "free (template + research data + exact math)"
    result = DailyResult(brief.topic, writer)
    _mark_used(store, today, brief.topic_key, brief.category)

    for script in scripts:
        job = store.create(script.format, brief.topic)
        out = settings.output_dir / job.id
        out.mkdir(parents=True, exist_ok=True)
        (out / "brief.json").write_text(brief.to_json())
        (out / "fact_sheet.md").write_text(brief.fact_sheet_md())
        job.script_path = str(out / "script.json")
        Path(job.script_path).write_text(script.model_dump_json(indent=2))
        store.transition(job, JobStatus.SCRIPTED, f"{writer}; {script.word_count} words")

        ok, why = finance_only_check(script)
        report_c = check_script(script, enforce_length=paid)
        if not ok:
            report_c.errors.append(f"Finance-only gate failed: {why}")
        (out / "compliance.txt").write_text(report_c.summary())
        if not report_c.ok:
            store.transition(job, JobStatus.REJECTED_COMPLIANCE, report_c.summary()[:500])
            result.jobs.append((job.id, script.format, "rejected_compliance", None, report_c.errors[0]))
            continue
        try:
            res = render_animated(script, out, settings, workers=workers)
            starts = res.scene_starts or []
            script = script.model_copy(update={"description": finalize_description(
                script.description, [s.heading for s in script.scenes], starts, script.format == "long")})
            Path(job.script_path).write_text(script.model_dump_json(indent=2))
            thumb = make_thumbnail_v3(script, out / "thumbnail.jpg", portrait=script.format == "short")
            (out / "metadata.json").write_text(json.dumps(
                {"title": script.title, "description": script.description, "tags": script.tags,
                 "topic_key": brief.topic_key, "category": brief.category, "market": brief.market,
                 "research_score": brief.score, "confidence": brief.confidence, "writer": writer,
                 "voice": res.voice, "render_seconds": round(res.render_seconds, 1),
                 "pronunciation_misses": res.unknown_words}, indent=2))
            job.video_path, job.subtitles_path = str(res.video), str(res.srt)
            job.thumbnail_path, job.duration_sec = str(thumb), round(res.duration, 2)
            store.transition(job, JobStatus.RENDERED, f"{res.duration:.1f}s in {res.render_seconds:.0f}s")
        except Exception as exc:  # one failed render must not stop the other videos
            log.exception("render failed for %s", job.id)
            job = store.get(job.id)
            if JobStatus.FAILED in ALLOWED[job.status]:
                store.transition(job, JobStatus.FAILED, f"{type(exc).__name__}: {exc}"[:500])
            result.jobs.append((job.id, script.format, "failed", None, str(exc)[:200]))
            continue

        note = ""
        if send and settings.telegram_bot_token and settings.telegram_approver_chat_id:
            from .publish.telegram import request_approval

            why_md = out / "why_this_topic.md"
            why_md.write_text(_why_card(brief, report))
            preview = None
            if script.format == "long":
                from .render.video import preview_clip

                preview = preview_clip(res.video, out / "preview.mp4")
            request_approval(job, store, settings, script, report_c.summary(), preview=preview,
                             attachments=[(why_md, "Why this topic (research evidence)"),
                                          (out / "fact_sheet.md", "Fact sheet (sources and calculations)")])
            note = "sent to Telegram"
        elif send:
            note = "Telegram not configured: review files in the output folder"
        job = store.get(job.id)
        result.jobs.append((job.id, script.format, job.status.value, job.video_path, note))
    return result


def _why_card(brief, report: dict) -> str:
    runners = [t for t in report["ranked"][:4] if t["key"] != brief.topic_key][:2]
    lines = [f"# Why \"{brief.topic}\" was chosen ({brief.date})", "",
             f"Research score {brief.score}/100 · {brief.confidence} confidence · {brief.category} · {brief.market}",
             "", "## Evidence"] + [f"- {w}" for w in brief.why]
    lines += ["", f"**Angle:** {brief.angle}", "", "## Runner-up topics"]
    lines += [f"- {t['topic']} ({t['score']}, {t['confidence']})" for t in runners]
    lines += ["", "Scores are opportunity estimates, not predictions of views. Full report: "
              f"reports/research/{brief.date}.md"]
    return "\n".join(lines) + "\n"
