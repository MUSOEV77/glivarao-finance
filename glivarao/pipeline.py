"""End-to-end orchestration: topic -> script -> checks -> narration -> animation -> thumbnail -> approval."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .compliance import ComplianceReport, check_script
from .config import Settings
from .models import Job, JobStatus, Script
from .render.thumbnail import make_thumbnail
from .render.video import preview_clip, render_video
from .scriptgen import generate_script
from .storage import ALLOWED, JobStore
from .topics import pick_topic

log = logging.getLogger(__name__)

SHORT_ANGLES = [
    "one surprising number that makes the idea click",
    "the single most common mistake people make with it",
]


@dataclass
class ProduceResult:
    job: Job
    script: Script
    report: ComplianceReport


def job_dir(settings: Settings, job: Job) -> Path:
    return settings.output_dir / job.id


def load_script(job: Job) -> Script:
    return Script.model_validate_json(Path(job.script_path).read_text())


def _fill_real_data(script: Script, settings: Settings) -> list[str]:
    from .marketdata import fill_fred_charts

    wants = any(s.chart.source.upper().startswith("FRED:") for s in script.scenes)
    if not wants:
        return []
    if settings.dry_run or not settings.fred_api_key:
        # no data available: drop the chart rather than show invented numbers
        for s in script.scenes:
            if s.chart.source.upper().startswith("FRED:"):
                s.chart.kind = "none"
        return ["FRED charts removed (no FRED_API_KEY / dry run)"]
    return fill_fred_charts(script, settings.fred_api_key)


def produce(settings: Settings, store: JobStore, fmt: str, topic: str | None = None, minutes: float | None = None,
            angle: str = "", tts_provider: str | None = None, send_for_approval: bool = True) -> ProduceResult:
    topic = topic or pick_topic(store.recent_topics())
    job = store.create(fmt, topic)
    out = job_dir(settings, job)
    out.mkdir(parents=True, exist_ok=True)
    try:
        script = generate_script(topic, fmt, settings, minutes=minutes, angle=angle)
        data_notes = _fill_real_data(script, settings)
        job.script_path = str(out / "script.json")
        Path(job.script_path).write_text(script.model_dump_json(indent=2))
        store.transition(job, JobStatus.SCRIPTED, f"{script.word_count} words")

        previous = []
        for j in store.list(limit=60):
            if j.id != job.id and j.script_path and Path(j.script_path).exists() and j.format == fmt:
                previous.append(load_script(j).full_narration)
        # Length targets are enforced only for real production runs at default length.
        enforce = not settings.dry_run and minutes is None
        report = check_script(script, enforce_length=enforce, previous_scripts=previous if not settings.dry_run else [])
        report.fact_check += [f"FRED data: {n}" for n in data_notes]
        (out / "compliance.txt").write_text(report.summary())
        if not report.ok:
            store.transition(job, JobStatus.REJECTED_COMPLIANCE, report.summary()[:500])
            return ProduceResult(job, script, report)

        result = render_video(script, out, settings, tts_provider=tts_provider)
        job.video_path = str(result.video)
        job.subtitles_path = str(result.srt)
        job.duration_sec = round(result.duration, 2)
        job.thumbnail_path = str(make_thumbnail(script, out / "thumbnail.jpg", portrait=fmt == "short"))
        (out / "metadata.json").write_text(json.dumps(
            {"title": script.title, "description": script.description, "tags": script.tags,
             "render_seconds": round(result.render_seconds, 1)}, indent=2))
        store.transition(job, JobStatus.RENDERED, f"{result.duration:.1f}s in {result.render_seconds:.0f}s")

        if send_for_approval and settings.telegram_bot_token and settings.telegram_approver_chat_id:
            from .publish.telegram import request_approval

            preview = preview_clip(result.video, out / "preview.mp4") if fmt == "long" else result.video
            request_approval(job, store, settings, script, report.summary(), preview=preview)
        return ProduceResult(job, script, report)
    except Exception as exc:
        job = store.get(job.id)
        if JobStatus.FAILED in ALLOWED[job.status]:
            store.transition(job, JobStatus.FAILED, f"{type(exc).__name__}: {exc}"[:500])
        raise


def daily(settings: Settings, store: JobStore, long_minutes: float | None = None,
          tts_provider: str | None = None) -> list[ProduceResult]:
    """One long explainer + two Shorts on the same day's topic (different angles)."""
    topic = pick_topic(store.recent_topics())
    results = [produce(settings, store, "long", topic, minutes=long_minutes, tts_provider=tts_provider)]
    for angle in SHORT_ANGLES:
        results.append(produce(settings, store, "short", topic, angle=angle, tts_provider=tts_provider))
    return results
