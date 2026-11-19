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
    style: str = ""
    note: str = ""            # why nothing was produced (pace, waiting for your input)


def _used_topics(store: JobStore, today: date) -> set[str]:
    hist = json.loads(store.kv_get("used_topics", "[]"))
    cutoff = (today - timedelta(days=REPEAT_WINDOW_DAYS)).isoformat()
    return {h[1] for h in hist if h[0] >= cutoff}  # entries: [date, topic_key] or [date, topic_key, category]


def _recent_categories(store: JobStore, today: date, days: int = 7) -> list[str]:
    hist = json.loads(store.kv_get("used_topics", "[]"))
    cutoff = (today - timedelta(days=days)).isoformat()
    return [h[2] for h in hist if len(h) > 2 and h[0] > cutoff]


def _mark_used(store: JobStore, today: date, topic_key: str, category: str = "", family: str = "", angle: str = "",
               key: str = "used_topics") -> None:
    hist = json.loads(store.kv_get(key, "[]"))
    if any(h[1] == topic_key and h[0] == today.isoformat() for h in hist):
        return
    hist.append([today.isoformat(), topic_key, category, family, angle])
    store.kv_set(key, json.dumps(hist[-500:]))


def finance_only_check(script: Script) -> tuple[bool, str]:
    """Gate 2: the finished script must itself pass the finance-only filter (no politics/news/etc.)."""
    text = " ".join([script.title] + [s.narration for s in script.scenes])
    return gate(text)


def pace_check(store: JobStore, today: date, settings: Settings) -> tuple[bool, str]:
    """Quality over quantity: LONG_VIDEOS_PER_MONTH long videos, spread evenly through the month (never more than
    the month's share so far), at least MIN_DAYS_BETWEEN_LONG days apart."""
    import calendar
    import math

    dates = [date.fromisoformat(d) for d in json.loads(store.kv_get("long_dates", "[]"))]
    month = [d for d in dates if (d.year, d.month) == (today.year, today.month)]
    target = settings.long_videos_per_month
    days = calendar.monthrange(today.year, today.month)[1]
    due = min(target, math.ceil(target * today.day / days))
    if len(month) >= target:
        return False, f"monthly pace reached ({len(month)}/{target} long videos this month)"
    if len(month) >= due:
        return False, f"on pace: {len(month)} of {target} long videos so far this month (next one is due later)"
    if dates and (today - max(dates)).days < settings.min_days_between_long:
        return False, f"last long video was {(today - max(dates)).days} day(s) ago (minimum gap " \
                      f"{settings.min_days_between_long})"
    return True, ""


def _remind(settings: Settings, store: JobStore, send: bool) -> str:
    from .studio.queue import TopicQueue

    q = TopicQueue(store)
    waiting, proposed = q.awaiting_input(), [i for i in q.items() if i.status == "proposed"]
    if waiting:
        note = "Waiting for your take on: " + "; ".join(f"\"{i.topic}\"" for i in waiting[:5]) + \
               ". Reply to my question in Telegram (text or voice note) and I'll make it on the next run."
    elif proposed:
        note = f"{len(proposed)} topic ideas are waiting for you to pick. Tap ✅ on the ones you want."
    else:
        note = "Your topic queue is empty. New ideas arrive on Sunday (or run: python -m glivarao propose-topics)."
    if send:
        _notify(settings, "GLIVARAO: nothing to produce today. " + note)
    return note


def _write_long(brief, style, creator, used, paid, settings, variant=0):
    from .content.format_writer import write_long_format

    if paid:
        return write_with_claude(brief, "long", settings, style=style, creator_text=creator, avoid_lines=used)
    return write_long_format(brief, style, creator, used, variant=variant)


def _write_shorts(brief, style, n, used, paid, settings):
    from .content.format_writer import write_shorts_format

    if not paid:
        return write_shorts_format(brief, style, n=n, used_lines=used)
    angles = ("ONE surprising number from the fact sheet, with its own hook in the first two seconds",
              "ONE common myth and the fact that corrects it, with its own hook",
              "ONE mistake people make and what to do instead, with its own hook")
    return [write_with_claude(brief, "short", settings, angle=a + ". Not a cut-down of the long video.",
                              avoid_lines=used).model_copy(update={"style": f"short_{i}"})
            for i, a in enumerate(angles[:n])]


def _originality_gate(script, brief, today, history, settings, paid, used, regen):
    """Check against earlier scripts; rewrite up to twice; returns (script, Similarity)."""
    from .studio import originality

    sim = originality.check(script, brief.topic_key, history, today, settings.similarity_max_phrase,
                            settings.similarity_max_structure)
    for attempt in range(2):
        if sim.ok:
            break
        log.info("originality: %s; rewriting (attempt %d)", "; ".join(sim.reasons), attempt + 1)
        if paid:
            from .scriptgen.claude import rewrite_for_originality

            script = rewrite_for_originality(script, sim.reasons, sim.repeated_phrases, settings)
        else:
            script = regen(attempt + 1)
        sim = originality.check(script, brief.topic_key, history, today, settings.similarity_max_phrase,
                                settings.similarity_max_structure)
    return script, sim


def run_daily_v2(settings: Settings, store: JobStore, today: date | None = None, research_dir: Path | None = None,
                 send: bool = True, workers: int | None = None, shorts: int | None = None) -> DailyResult:
    from .render.animated import render_animated
    from .render.thumbnail_editorial import make_thumbnail
    from .research.run import run_research
    from .studio import disclosure, factcheck, originality
    from .studio.bot import format_history, push_format
    from .studio.formats import FORMATS, choose_format
    from .studio.queue import TopicQueue

    today = today or date.today()
    shorts = settings.shorts_per_day if shorts is None else shorts
    research_dir = research_dir or Path("reports/research")
    cached = research_dir / f"{today.isoformat()}.json"
    paid = paid_writer_allowed(settings)
    item, creator, style = None, "", None
    shorts_only, pace_note, short_why = False, "", []
    if settings.topic_mode == "queue":  # manual mode: only topics YOU picked from the weekly ideas
        ok, why = pace_check(store, today, settings)
        if not ok:
            return DailyResult("", "skipped", note=why)
        ready = [i for i in TopicQueue(store).ready()
                 if i.creator_input.strip() or not settings.require_creator_input]
        if not ready:
            return DailyResult("", "waiting", note=_remind(settings, store, send))
        item = ready[0]
    else:  # automatic (default): research picks the topic; your take is optional within a time window
        from .studio.planner import input_window_over, plan_next

        ok, why = pace_check(store, today, settings)
        if ok:
            item = plan_next(settings, store, today, research_dir, send)
            if item is None:
                ok, why = False, "no long-video topic passed today's checks (no repeats, rotation)"
            elif item.status == "awaiting_input" and not input_window_over(item, settings):
                ok, why = False, (f"waiting up to {settings.creator_input_wait_hours:g} h for your take on "
                                  f"\"{item.topic}\" (announced in Telegram)")
        if not ok:  # no long video today: today's Shorts get their own topic
            item = None
            if settings.shorts_per_day <= 0:
                return DailyResult("", "skipped", note=why)
            shorts_only = True
            pace_note = why
    if not shorts_only:
        card, creator, style = item.card, item.creator_input, item.format
        report = json.loads(cached.read_text()) if cached.exists() else {"ranked": []}
    else:
        from .studio.autopick import pick_topic

        report = json.loads(cached.read_text()) if cached.exists() else run_research(today, research_dir, store)
        from .studio.planner import active_item

        planned = active_item(store)  # never collide with the long video that is waiting for your take
        recent_long = {h[1] for h in json.loads(store.kv_get("used_topics", "[]"))[-3:]}
        card, short_why, _ = pick_topic(report, store, free_writer=not paid, history_key="used_short_topics",
                                        recent_videos=10, family_gap=0,
                                        exclude=recent_long | ({planned.key} if planned else set()), today=today)
        if card is None:
            return DailyResult("", "skipped", note=f"{pace_note}; no Shorts topic passed today's checks")
        style = "explainer"
    brief = build_brief(card, today)
    if not style:
        style = choose_format(brief, format_history(store))
        push_format(store, style)
    used = originality.used_lines(store)
    writer = "claude" if paid else "free (format templates + research data + exact math)"
    history = originality.load_history(store)
    if shorts_only:
        long_script, drafts = None, []
    else:
        long_script, long_sim = _originality_gate(
            _write_long(brief, style, creator, used, paid, settings), brief, today, history, settings, paid, used,
            lambda k: _write_long(brief, style if k < 2 else choose_format(brief, [style]), creator, used, paid,
                                  settings, variant=k))
        drafts = [(long_script, long_sim)]
    lead_style = long_script.style if long_script is not None else style
    lead_hook = long_script.hook if long_script is not None else ""
    # Shorts are checked against past videos and each other. Sharing a line with their own companion long video
    # is normal (they point to it); their own hook and point are enforced below and by the writer.
    session = list(history)
    for sh in _write_shorts(brief, lead_style, shorts, used + [lead_hook], paid, settings):
        alternates: list = []

        def regen(k, sh=sh, alternates=alternates):  # free writer only (paid drafts are rewritten by Claude)
            if not alternates:
                taken = {d[0].style for d in drafts}
                alternates += [x for x in _write_shorts(brief, lead_style, 5, used + [sh.hook],
                                                        False, settings) if x.style not in taken]
            return alternates.pop(0) if alternates else sh

        sh, sim = _originality_gate(sh, brief, today, session, settings, paid, used, regen)
        if sh.hook and lead_hook and sh.hook.strip().lower() == lead_hook.strip().lower():
            sim.ok = False
            sim.reasons.append("the Short reuses the long video's opening line")
        drafts.append((sh, sim))
        session.append(originality.entry(sh, brief.topic_key, today))
    result = DailyResult(brief.topic, writer, style=("Shorts only" if shorts_only else
                                                     FORMATS.get(lead_style or "", FORMATS["explainer"]).label),
                         note=pace_note)
    from .studio.autopick import angle_text

    if shorts_only:
        _mark_used(store, today, brief.topic_key, brief.category, brief.family, angle_text(card),
                   key="used_short_topics")
    else:
        _mark_used(store, today, brief.topic_key, brief.category, brief.family, angle_text(card))

    for script, sim in drafts:
        job = store.create(script.format, brief.topic)
        out = settings.output_dir / job.id
        out.mkdir(parents=True, exist_ok=True)
        (out / "brief.json").write_text(brief.to_json())
        (out / "fact_sheet.md").write_text(brief.fact_sheet_md())
        claims = factcheck.check_claims(script, brief, creator)
        missing = factcheck.needs_source(claims)
        if missing and paid:  # every claim needs a source URL: ask Claude to source or remove the rest
            from .scriptgen.claude import rewrite_for_sources

            script = rewrite_for_sources(script, [c.text for c in missing], settings)
            claims = factcheck.check_claims(script, brief, creator)
            missing = factcheck.needs_source(claims)
        (out / "fact_check.md").write_text("# " + factcheck.report(claims, limit=500).replace("\n", "\n\n") + "\n")
        job.script_path = str(out / "script.json")
        Path(job.script_path).write_text(script.model_dump_json(indent=2))
        store.transition(job, JobStatus.SCRIPTED, f"{writer}; {script.style}; {script.word_count} words")

        ok, why = finance_only_check(script)
        report_c = check_script(script, enforce_length=paid)
        if not ok:
            report_c.errors.append(f"Finance-only gate failed: {why}")
        if not sim.ok:
            report_c.errors.append("Too similar to earlier videos even after rewriting: " + "; ".join(sim.reasons))
        if missing:
            report_c.errors.append(f"{len(missing)} claim(s) without a source URL: "
                                   + " | ".join(c.text[:80] for c in missing[:3]))
        (out / "compliance.txt").write_text(report_c.summary() + "\n\n" + sim.summary())
        if not report_c.ok:
            store.transition(job, JobStatus.REJECTED_COMPLIANCE, report_c.summary()[:500])
            result.jobs.append((job.id, script.format, "rejected_compliance", None, report_c.errors[0]))
            continue
        try:
            res = _render_with_retry(render_animated, script, out, settings, workers)
            disc = disclosure.disclosure_for(res.voice)
            desc = factcheck.add_sources_to_description(script.description, claims)
            desc = disclosure.add_note(desc, disc)
            from .content.packaging import add_affiliate_disclosure, title_options
            from .studio.pillars import pillar_of, series_for

            desc = add_affiliate_disclosure(desc, settings.affiliate_disclosure)
            script = script.model_copy(update={"description": finalize_description(
                desc, [s.heading for s in script.scenes], res.scene_starts or [], script.format == "long")})
            Path(job.script_path).write_text(script.model_dump_json(indent=2))
            thumb = make_thumbnail(script, out / "thumbnail.jpg", portrait=script.format == "short",
                                   theme=getattr(settings, "theme", "editorial"))
            (out / "metadata.json").write_text(json.dumps(
                {"title": script.title, "title_options": title_options(brief, script),
                 "description": script.description, "tags": script.tags,
                 "topic_key": brief.topic_key, "category": brief.category, "market": brief.market,
                 "pillar": getattr(pillar_of(brief.topic_key), "key", None),
                 "series": series_for(brief.topic_key, today),
                 "format": script.style, "creator_input": creator, "picked_by_you": item is not None,
                 "research_score": brief.score, "confidence": brief.confidence, "writer": writer,
                 "voice": res.voice, "render_seconds": round(res.render_seconds, 1),
                 "youtube_altered_content": disc.youtube_altered_content, "disclosure": disc.reasons,
                 "fact_check": {s: sum(c.status == s for c in claims)
                                for s in ("source", "calculation", "reference", "creator", "UNSOURCED")},
                 "originality": {"phrase_overlap": round(sim.phrase_overlap, 3),
                                 "structure_similarity": round(sim.structure_ratio, 3)},
                 "pronunciation_misses": res.unknown_words}, indent=2))
            job.video_path, job.subtitles_path = str(res.video), str(res.srt)
            job.thumbnail_path, job.duration_sec = str(thumb), round(res.duration, 2)
            store.transition(job, JobStatus.RENDERED, f"{res.duration:.1f}s in {res.render_seconds:.0f}s")
            originality.record(store, script, brief.topic_key, today)
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
            why_md.write_text(_why_card(brief, report, item))
            preview = None
            if script.format == "long":
                from .render.video import preview_clip

                preview = preview_clip(res.video, out / "preview.mp4")
            checks = "\n\n".join([_topic_block(brief, item, script, store, today), report_c.summary(), sim.summary(),
                                   factcheck.report(claims), disc.review_text()])
            request_approval(job, store, settings, script, checks, preview=preview,
                             attachments=[(why_md, "Why this topic (research evidence)"),
                                          (out / "fact_check.md", "Fact check: every number and its source"),
                                          (out / "fact_sheet.md", "Fact sheet (sources and calculations)")])
            note = "sent to Telegram"
        elif send:
            note = "Telegram not configured: review files in the output folder"
        job = store.get(job.id)
        result.jobs.append((job.id, script.format, job.status.value, job.video_path, note))

    produced = [j for j in result.jobs if j[2] in ("rendered", "pending_approval")]
    if any(j[1] == "long" for j in produced):
        dates = json.loads(store.kv_get("long_dates", "[]")) + [today.isoformat()]
        store.kv_set("long_dates", json.dumps(dates[-200:]))
    if item is not None and produced:
        TopicQueue(store).update(item.id, status="produced", produced_on=today.isoformat(),
                                 jobs=[j[0] for j in result.jobs])
    return result


def _render_with_retry(render_animated, script, out, settings, workers):
    """One retry with a single worker: the usual cause of a failed render is memory pressure or a crashed worker."""
    try:
        return render_animated(script, out, settings, workers=workers)
    except Exception as exc:
        log.warning("render failed (%s: %s); retrying once with 1 worker", type(exc).__name__, exc)
        return render_animated(script, out, settings, workers=1)


class AlreadyRunning(RuntimeError):
    pass


def supervised_daily(settings: Settings, store: JobStore, today: date | None = None, send: bool = True,
                     workers: int | None = None, shorts: int = 2, force: bool = False, retries: int = 1,
                     retry_delay: float = 120.0, lock_path: Path | None = None, notifier=None) -> DailyResult | None:
    """Production entry point used by the systemd timer.

    - single instance (file lock), so a slow run and the next timer tick never overlap;
    - idempotent: a day that already completed is skipped (use force=True to produce again);
    - checks free disk first; retries a failed run once; on final failure sends a Telegram alert;
    - also alerts when the day finished but any video failed or was rejected by compliance.
    Never uploads, publishes or schedules anything on YouTube."""
    import fcntl
    import time

    from .sysres import check_disk

    today = today or date.today()
    notifier = notifier or _notify
    lock_path = lock_path or Path(settings.db_path).with_name("daily.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        raise AlreadyRunning("another daily run holds the lock")
    try:
        done_key = f"daily_done:{today.isoformat()}"
        if store.kv_get(done_key) and not force:
            log.info("daily set for %s already produced; skipping (use --force to redo)", today)
            return None
        check_disk(Path(settings.output_dir))
        last = None
        for attempt in range(retries + 1):
            try:
                res = run_daily_v2(settings, store, today=today, send=send, workers=workers, shorts=shorts)
                break
            except Exception as exc:  # research outage, disk, etc.
                last = exc
                log.exception("daily run attempt %d failed", attempt + 1)
                if attempt < retries:
                    time.sleep(retry_delay)
        else:
            notifier(settings, f"GLIVARAO daily run FAILED for {today} after {retries + 1} attempts: "
                               f"{type(last).__name__}: {str(last)[:300]}\nSee logs/daily.log on the server.")
            raise last
        if res.jobs:  # nothing produced (pace / waiting for your input) -> a later run today may still produce
            store.kv_set(done_key, json.dumps([j[0] for j in res.jobs]))
        bad = [j for j in res.jobs if j[2] in ("failed", "rejected_compliance")]
        if bad:
            notifier(settings, f"GLIVARAO {today}: {len(bad)} of {len(res.jobs)} videos need attention:\n" +
                     "\n".join(f"- {j[0]} ({j[1]}): {j[2]}: {j[4]}" for j in bad))
        return res
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def _notify(settings: Settings, text: str) -> None:
    try:
        from .publish.telegram import notify

        notify(settings, text)
    except Exception:  # an alert failure must never mask the original error
        log.exception("could not send Telegram alert")


def _topic_block(brief, item, script, store=None, today: date | None = None) -> str:
    """First thing in the review message: what the topic is and why it was picked."""
    from .studio.formats import FORMATS
    from .studio.pillars import pillar_of, series_for
    from .studio.series import next_episode_number

    how = "picked automatically by research" if (item is None or item.auto) else "picked by you"
    p = pillar_of(brief.topic_key)
    s = series_for(brief.topic_key, today or date.fromisoformat(brief.date))
    lines = [f"TOPIC: {brief.topic} ({how})",
             f"PILLAR: {p.name if p else 'outside the 5 pillars'}"
             + (f" · SERIES: {s}" + (f" (episode {next_episode_number(store, s, script.format)} if approved)"
                                     if store is not None else "") if s else ""),
             f"FORMAT: {FORMATS.get(script.style or '', FORMATS['explainer']).label if script.format == 'long' else script.style}",
             "WHY THIS TOPIC:"]
    lines += [f"• {w}" for w in ((item.why if item is not None and item.why else brief.why)[:8])]
    take = (item.creator_input if item is not None else "") or ""
    lines.append(f"YOUR TAKE: \"{take[:300]}\"" if take else "YOUR TAKE: none received (made without \"My take\")")
    lines.append("Don't like the topic? Tap ❌ Reject: the whole video is discarded and nothing is uploaded.")
    return "\n".join(lines)


def _why_card(brief, report: dict, item=None) -> str:
    runners = [t for t in report.get("ranked", [])[:4] if t["key"] != brief.topic_key][:2]
    if item is not None and item.auto:
        picked = "Picked automatically by research.\n\n" + "\n".join(f"- {w}" for w in item.why)
    elif item is not None:
        picked = f"Picked by you on {item.picked_at[:10]} from the weekly ideas."
    else:
        picked = "Picked automatically."
    if item is not None and item.creator_input:
        picked += f"\n\nYour take: \"{item.creator_input}\""
    lines = [f"# Why \"{brief.topic}\" was chosen ({brief.date})", "", picked, "",
             f"Research score {brief.score}/100 · {brief.confidence} confidence · {brief.category} · {brief.market}",
             "", "## Evidence"] + [f"- {w}" for w in brief.why]
    lines += ["", f"**Angle:** {brief.angle}", "", "## Runner-up topics"]
    lines += [f"- {t['topic']} ({t['score']}, {t['confidence']})" for t in runners]
    lines += ["", "Scores are opportunity estimates, not predictions of views. Full report: "
              f"reports/research/{brief.date}.md"]
    return "\n".join(lines) + "\n"
