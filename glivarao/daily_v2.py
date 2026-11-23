"""Daily production v2: autonomous research -> topic selection -> brief + fact sheet -> scripts
(1 long + 2 Shorts) -> finance-only and compliance checks -> narration, music, SFX, animation, captions ->
thumbnails + metadata -> Telegram review package.

NEVER uploads, publishes or schedules anything on YouTube. Paid APIs are used only when ALLOW_PAID_APIS=true.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .compliance import check_script
from .config import Settings
from .content.brief import build_brief
from .content.packaging import finalize_description
from .content.writer import paid_writer_allowed, write_with_claude
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




def _mark_used(store: JobStore, today: date, topic_key: str, category: str = "", family: str = "", angle: str = "",
               key: str = "used_topics", news: bool = False) -> None:
    hist = json.loads(store.kv_get(key, "[]"))
    if any(h[1] == topic_key and h[0] == today.isoformat() for h in hist):
        return
    hist.append([today.isoformat(), topic_key, category, family, angle, bool(news)])
    store.kv_set(key, json.dumps(hist[-500:]))


def finance_only_check(script: Script) -> tuple[bool, str]:
    """Gate 2: the finished script must itself pass the finance-only filter (no politics/news/etc.)."""
    text = " ".join([script.title] + [s.narration for s in script.scenes])
    return gate(text)


def pace_check(store: JobStore, today: date, settings: Settings) -> tuple[bool, str]:
    """LONG_VIDEOS_PER_MONTH long videos, spread evenly through the month and produced PRODUCTION_LEAD_DAYS ahead
    (never more than the month's share so far), at least MIN_DAYS_BETWEEN_LONG days apart. When the buffer of
    approved long videos is low, the next one may be made early (still within the monthly total)."""
    from .studio import buffer

    dates = [date.fromisoformat(d) for d in json.loads(store.kv_get("long_dates", "[]"))]
    made, due = buffer.long_due(store, today, settings)
    target = settings.long_videos_per_month
    low = buffer.status(store, settings)
    behind = low["low_long"] and low["ready_long"] + low["review_long"] < settings.buffer_long
    if made >= target:
        return False, f"monthly pace reached ({made}/{target} long videos this month)"
    if made >= due and not behind:
        return False, f"on pace: {made} of {target} long videos so far this month (next one is due later)"
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
        from .studio import costs

        t = costs.new_draft("long")
        with costs.tag(t):
            s = write_with_claude(brief, "long", settings, style=style, creator_text=creator, avoid_lines=used)
        return s.model_copy(update={"cost_tag": t})
    return write_long_format(brief, style, creator, used, variant=variant)


def _write_shorts(brief, style, n, used, paid, settings):
    from .content.format_writer import write_shorts_format

    if not paid:
        return write_shorts_format(brief, style, n=n, used_lines=used)
    angles = ("ONE surprising number from the fact sheet, with its own hook in the first two seconds",
              "ONE common myth and the fact that corrects it, with its own hook",
              "ONE mistake people make and what to do instead, with its own hook")
    from .studio import costs

    out = []
    for i, a in enumerate(angles[:n]):
        t = costs.new_draft("short")
        with costs.tag(t):
            s = write_with_claude(brief, "short", settings, angle=a + ". Not a cut-down of the long video.",
                                  avoid_lines=used)
        out.append(s.model_copy(update={"style": f"short_{i}", "cost_tag": t}))
    return out


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

            from .studio import costs

            t = script.cost_tag
            with costs.tag(t):
                script = rewrite_for_originality(script, sim.reasons, sim.repeated_phrases, settings)
            script = script.model_copy(update={"cost_tag": t})
        else:
            script = regen(attempt + 1)
        sim = originality.check(script, brief.topic_key, history, today, settings.similarity_max_phrase,
                                settings.similarity_max_structure)
    return script, sim


def run_daily_v2(settings: Settings, store: JobStore, today: date | None = None, research_dir: Path | None = None,
                 send: bool = True, workers: int | None = None, shorts: int | None = None,
                 ignore_input_wait: bool = False, deliver_day: date | None = None) -> DailyResult:
    from .research.run import run_research
    from .studio import originality
    from .studio.bot import format_history, push_format
    from .studio.formats import FORMATS, choose_format
    from .studio.queue import TopicQueue

    from .studio.pause import guard

    guard(settings, "daily production")
    import time as _time

    _t0 = _time.monotonic()
    today = today or date.today()
    if held_videos(store):  # videos held for the voice go first (they are already scripted and approved by checks)
        retry_held_videos(settings, store, send=send, workers=workers)
    from .studio import buffer as _buffer

    if shorts is None:
        shorts = _buffer.shorts_quota(store, today, settings, _buffer.status(store, settings))
    research_dir = research_dir or Path("reports/research")
    cached = research_dir / f"{today.isoformat()}.json"
    paid = paid_writer_allowed(settings)
    if settings.writer != "free" and not paid and not settings.dry_run:
        # Claude only: never the template writer in production (Shorts included)
        return _hold_for_writer(settings, store, today, "today's videos",
                                "paid APIs are switched off (ALLOW_PAID_APIS=false)", send)
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
            elif item.status == "awaiting_input" and not input_window_over(item, settings) and not ignore_input_wait:
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
    if not settings.dry_run:   # the topic's library facts (e.g. HHS poverty guidelines) re-checked on official pages
        from .studio.fact_library import verify_brief

        for note in verify_brief(brief):
            log.warning("fact: %s", note)
    if not style:
        style = choose_format(brief, format_history(store))
        push_format(store, style)
    used = originality.used_lines(store)
    writer = "claude" if paid else "free (format templates + research data + exact math)"
    history = originality.load_history(store)
    from .scriptgen.claude import ClaudeUnavailable

    try:
        if shorts_only:
            long_script, drafts = None, []
        else:
            long_script, long_sim = _originality_gate(
                _write_long(brief, style, creator, used, paid, settings), brief, today, history, settings, paid, used,
                lambda k: _write_long(brief, style if k < 2 else choose_format(brief, [style]), creator, used, paid,
                                      settings, variant=k))
            drafts = [(long_script, long_sim)]
            if paid:  # which backend actually wrote it (Claude on Vertex / Anthropic API, or the Gemini fallback)
                from .scriptgen.claude import LAST_WRITER

                if LAST_WRITER.get("name"):
                    writer = LAST_WRITER["name"] + (f" — Claude failed: {LAST_WRITER['note'][:120]}"
                                                    if LAST_WRITER.get("note") else "")
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
    except ClaudeUnavailable as exc:  # Claude only: hold today's production, alert once, retry hourly
        return _hold_for_writer(settings, store, today, brief.topic, str(exc), send)
    _release_writer_hold(settings, store, send)
    from .studio.delivery import record_duration

    record_duration(store, "script", _time.monotonic() - _t0)
    result = DailyResult(brief.topic, writer, style=("Shorts only" if shorts_only else
                                                     FORMATS.get(lead_style or "", FORMATS["explainer"]).label),
                         note=pace_note)
    from .studio.autopick import angle_text

    if shorts_only:
        _mark_used(store, today, brief.topic_key, brief.category, brief.family, angle_text(card),
                   key="used_short_topics")
    else:
        from .studio.pillars import is_news

        _mark_used(store, today, brief.topic_key, brief.category, brief.family, angle_text(card), news=is_news(card))

    _produce_drafts(drafts, brief, creator, writer, paid, card, item, report, today, settings, store, send, workers,
                    result, deliver_day=deliver_day)

    produced = [j for j in result.jobs if j[2] in ("rendered", "pending_approval", "held")]  # held = made later
    made_shorts = sum(j[1] == "short" for j in produced)
    if made_shorts:
        _buffer.record_shorts(store, today, made_shorts)
    if any(j[1] == "long" for j in produced):
        dates = json.loads(store.kv_get("long_dates", "[]")) + [today.isoformat()]
        store.kv_set("long_dates", json.dumps(dates[-200:]))
    if item is not None and produced:
        TopicQueue(store).update(item.id, status="produced", produced_on=today.isoformat(),
                                 jobs=[j[0] for j in result.jobs])
    return result


def _produce_drafts(drafts, brief, creator, writer, paid, card, item, report, today, settings, store, send, workers,
                    result, retry: bool = True, deliver_day: date | None = None) -> None:
    """Fact-check, sponsor/evergreen rewrite, compliance, then render + Telegram review for every draft (shared by the
    daily run, make-now and retry-rejected). Charts that aren't built from fact-sheet data are removed. A draft
    rejected by compliance is fixed ONCE by Claude with the exact reasons and the fact sheet, and checked again."""
    import time as _time

    from .studio import delivery

    def _done(r, t0):
        if r[2] in ("rendered", "pending_approval"):
            spent = _time.monotonic() - t0
            delivery.record_duration(store, r[1], spent)
            if deliver_day is not None and send:
                delivery.delivered(settings, store, deliver_day, r, spent, _notify)

    for script, sim in drafts:
        t0 = _time.monotonic()
        r = _produce_one(script, sim, brief, creator, writer, paid, card, item, report, today, settings, store, send,
                         workers)
        result.jobs.append(r)
        _done(r, t0)
        if r[2] == "rejected_compliance" and retry and paid:
            fixed = _fix_rejected(r[0], brief, settings, store)
            if fixed is not None:
                result.note = (result.note + "; " if result.note else "") + f"{r[0]} fixed by Claude, checked again"
                r2 = _produce_one(fixed, sim, brief, creator, writer, paid, card, item, report, today, settings, store,
                                  send, workers)
                result.jobs.append(r2)
                _done(r2, t0)
                chain = json.loads(store.kv_get("fixed_from", "{}"))
                chain[r2[0]] = r[0]
                store.kv_set("fixed_from", json.dumps(chain))


def _fix_rejected(job_id: str, brief, settings: Settings, store: JobStore):
    """Claude rewrites a rejected script with the exact rejection reasons + the fact sheet (None if unavailable)."""
    from .models import Script as _Script
    from .scriptgen.claude import ClaudeUnavailable, rewrite_for_compliance

    cfile = settings.output_dir / job_id / "compliance.txt"
    errs = [ln[7:] for ln in (cfile.read_text().splitlines() if cfile.exists() else []) if ln.startswith("ERROR: ")]
    facts = [f"{f.text} [{f.source or f.kind}{' ' + f.url if f.url else ''}]" for f in brief.facts]
    log.warning("%s rejected (%s); asking Claude to fix it once", job_id, "; ".join(errs)[:200])
    try:
        from .studio import costs

        old = _Script.model_validate_json(Path(store.get(job_id).script_path).read_text())
        with costs.tag(job_id):   # the fix's cost belongs to the video that replaces this one
            fixed = rewrite_for_compliance(old, errs or ["failed the automatic checks"], facts, settings)
        return fixed.model_copy(update={"cost_tag": job_id})
    except ClaudeUnavailable as exc:
        log.warning("fix of %s skipped: Claude unavailable (%s)", job_id, exc)
        return None


def _produce_one(script, sim, brief, creator, writer, paid, card, item, report, today, settings, store, send,
                 workers) -> tuple:
    from .studio import factcheck

    script, dropped = factcheck.sanitize_charts(script, brief)   # charts only from fact-sheet data
    if dropped:
        log.warning("charts removed (values not on the fact sheet): %s", "; ".join(dropped))
    job = store.create(script.format, brief.topic)
    from .studio import costs

    costs.link(script.cost_tag, job.id, cost_dir(settings))   # the draft's writing cost belongs to this video
    with costs.tag(job.id):
        return _produce_job(job, script, sim, brief, creator, writer, paid, card, item, report, today, settings,
                            store, send, workers)


def _produce_job(job, script, sim, brief, creator, writer, paid, card, item, report, today, settings, store, send,
                 workers) -> tuple:
    from .studio import factcheck

    out = settings.output_dir / job.id
    out.mkdir(parents=True, exist_ok=True)
    (out / "brief.json").write_text(brief.to_json())
    (out / "fact_sheet.md").write_text(brief.fact_sheet_md())
    claims = factcheck.check_claims(script, brief, creator)
    missing = factcheck.needs_source(claims)
    if missing and paid:  # every claim needs a source URL: ask Claude to source or remove the rest
        from .scriptgen.claude import ClaudeUnavailable, rewrite_for_sources

        try:
            script = rewrite_for_sources(script, [c.text for c in missing], settings)
            claims = factcheck.check_claims(script, brief, creator)
            missing = factcheck.needs_source(claims)
        except ClaudeUnavailable as exc:  # keep the draft; it is rejected below for the unsourced claims
            log.warning("source rewrite skipped for %s: Claude unavailable (%s)", job.id, exc)
    from .compliance import evergreen_issues, has_what_to_do, retention_issues, sponsor_issues

    issues = sponsor_issues(script)
    ever = [] if brief.timely else evergreen_issues(script)
    hold = retention_issues(script)
    if (issues or ever or hold or not has_what_to_do(script)) and paid:  # sponsor, evergreen, retention, "What to do"
        from .scriptgen.claude import ClaudeUnavailable, rewrite_for_sponsor

        try:
            script = rewrite_for_sponsor(script, issues, not has_what_to_do(script), settings,
                                         evergreen_issues=ever, retention_issues=hold)
            claims = factcheck.check_claims(script, brief, creator)
            missing = factcheck.needs_source(claims)
        except ClaudeUnavailable as exc:  # keep the draft; the compliance check below rejects it
            log.warning("sponsor rewrite skipped for %s: Claude unavailable (%s)", job.id, exc)
    (out / "fact_check.md").write_text("# " + factcheck.report(claims, limit=500).replace("\n", "\n\n") + "\n")
    job.script_path = str(out / "script.json")
    Path(job.script_path).write_text(script.model_dump_json(indent=2))
    store.transition(job, JobStatus.SCRIPTED, f"{writer}; {script.style}; {script.word_count} words")

    ok, why = finance_only_check(script)
    report_c = check_script(script, enforce_length=paid, evergreen=not brief.timely, retention=True)
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
        return (job.id, script.format, "rejected_compliance", None, report_c.errors[0])
    ctx = {"writer": writer, "creator": creator, "item_id": item.id if item is not None else None, "card": card,
           "date": today.isoformat(), "compliance": report_c.summary(),
           "sim": {"summary": sim.summary(), "phrase_overlap": sim.phrase_overlap,
                   "structure_ratio": sim.structure_ratio}}
    return render_and_review(job, script, brief, claims, ctx, settings, store, send, workers, report=report,
                             item=item)


class Busy(RuntimeError):
    pass


def make_now(settings: Settings, store: JobStore, n: int, short: bool = False, send: bool = True,
             workers: int | None = None) -> DailyResult:
    """Make launch-list video #n NOW (long, or one Short with --short), outside the schedule: official facts
    re-checked, Claude writes it (OpenRouter), same checks as every video, rendered and sent for review in
    Telegram. Respects the pause and never runs at the same time as the daily run. Never publishes."""
    import fcntl
    from dataclasses import replace as _replace

    from .studio import launch_plan, originality
    from .studio.formats import choose_format
    from .studio.bot import format_history
    from .studio.pause import guard

    guard(settings, f"make-now {n}")
    if not 1 <= n <= len(launch_plan.LAUNCH):
        raise ValueError(f"launch list has videos 1-{len(launch_plan.LAUNCH)}")
    if not paid_writer_allowed(settings):
        raise ValueError("Claude can't be used (ALLOW_PAID_APIS=false or WRITER=free): Claude only, so nothing is made")
    lock = open(Path(settings.db_path).with_name("daily.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise Busy("the daily run (or another make-now) is running right now; try again when it finishes") from None
    try:
        v = launch_plan.LAUNCH[n - 1]
        kept, notes = launch_plan.verify_facts(v)
        for f, note in notes:
            log.warning("launch #%d fact: %s (%s)", n, f.text[:80], note)
        card = _replace(v, facts=kept).card()
        today = date.today()
        brief = build_brief(card, today)
        if not settings.dry_run:
            from .studio.fact_library import verify_brief

            for note in verify_brief(brief):
                log.warning("fact: %s", note)
        style = v.format or choose_format(brief, format_history(store))
        used, history = originality.used_lines(store), originality.load_history(store)
        from .scriptgen.claude import LAST_WRITER, ClaudeUnavailable

        try:
            if short:
                sh = _write_shorts(brief, style, 1, used, True, settings)[0]
                drafts = [_originality_gate(sh, brief, today, history, settings, True, used, lambda k: sh)]
            else:
                drafts = [_originality_gate(_write_long(brief, style, "", used, True, settings), brief, today, history,
                                            settings, True, used,
                                            lambda k: _write_long(brief, style, "", used, True, settings, variant=k))]
        except ClaudeUnavailable as exc:
            return _hold_for_writer(settings, store, today, brief.topic, str(exc), send)
        _release_writer_hold(settings, store, send)
        writer = LAST_WRITER.get("name") or "claude"
        result = DailyResult(brief.topic, writer, style=style, note=f"make-now launch #{n}" +
                             (f"; {len(notes)} fact(s) dropped or unconfirmed" if notes else ""))
        _produce_drafts(drafts, brief, "", writer, True, card, None, {"ranked": []}, today, settings, store, send,
                        workers, result)
        made = [j for j in result.jobs if j[2] in ("rendered", "pending_approval", "held")]
        if made and short:
            from .studio import buffer as _buffer

            _buffer.record_shorts(store, today, len(made))
            _mark_used(store, today, brief.topic_key, brief.category, brief.family, key="used_short_topics")
        elif made:
            launch_plan.mark_done(store, n)
            dates = json.loads(store.kv_get("long_dates", "[]")) + [today.isoformat()]
            store.kv_set("long_dates", json.dumps(dates[-200:]))
            from .studio.pillars import is_news

            _mark_used(store, today, brief.topic_key, brief.category, brief.family, news=is_news(card))
        return result
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def retry_rejected(settings: Settings, store: JobStore, day: date | None = None, send: bool = True,
                   workers: int | None = None) -> list:
    """Make the videos rejected by compliance on `day` again: the fact sheet gets the topic's reviewed library facts
    (re-checked on their official pages), charts not built from fact-sheet data are removed, Claude fixes the script
    with the exact rejection reasons, then every check runs again and it is rendered and sent for review. Each
    rejected video is retried only once. Returns the new job tuples."""
    import fcntl

    from .content.brief import load_brief
    from .studio import buffer as _buffer
    from .studio import fact_library
    from .studio.pause import guard

    guard(settings, "retry of rejected videos")
    if not paid_writer_allowed(settings):
        raise ValueError("Claude can't be used (ALLOW_PAID_APIS=false or WRITER=free)")
    from datetime import timedelta

    days = [day] if day else [date.today(), date.today() - timedelta(days=1)]   # default: today and yesterday
    stamps = tuple(d.strftime("%Y%m%d") for d in days)
    day = days[0]
    done = set(json.loads(store.kv_get("rejected_retried", "[]")))
    fixed_from = json.loads(store.kv_get("fixed_from", "{}"))
    superseded = set(fixed_from.values())        # first drafts that already had an automatic fix attempt
    todo = [j for j in store.list(limit=500) if j.status == JobStatus.REJECTED_COMPLIANCE
            and j.id.startswith(stamps) and j.id not in done and j.id not in superseded]
    lock = open(Path(settings.db_path).with_name("daily.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise Busy("the daily run (or make-now) is running right now; try again when it finishes") from None
    out_jobs = []
    try:
        for job in todo:
            src = settings.output_dir / job.id
            if not (src / "brief.json").exists() or not job.script_path:
                continue
            brief = load_brief(src / "brief.json")
            fact_library.add_to_brief(brief)
            if not settings.dry_run:
                for note in fact_library.verify_brief(brief):
                    log.warning("%s fact: %s", job.id, note)
            fixed = _fix_rejected(job.id, brief, settings, store)
            done.add(job.id)
            store.kv_set("rejected_retried", json.dumps(sorted(done)[-500:]))
            if fixed is None:
                out_jobs.append((job.id, job.format, "rejected_compliance", None, "Claude unavailable: not retried"))
                continue
            # originality was checked when this video was first written; comparing it with its own earlier
            # attempts would only find itself
            sim = _Sim({"summary": f"Originality: checked when {job.id} was first written (same video, fixed)",
                        "phrase_overlap": 0.0, "structure_ratio": 0.0})
            r = _produce_one(fixed, sim, brief, "", "claude (fixed after a compliance rejection)", True, None, None,
                             {"ranked": []}, day, settings, store, send, workers)
            out_jobs.append(r)
            if r[2] in ("rendered", "pending_approval", "held"):
                if r[1] == "short":
                    _buffer.record_shorts(store, day, 1)
                else:
                    dates = json.loads(store.kv_get("long_dates", "[]")) + [day.isoformat()]
                    store.kv_set("long_dates", json.dumps(dates[-200:]))
        return out_jobs
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def clear_writer_hold(store: JobStore) -> dict:
    """Clear a stale 'Claude unavailable' hold (e.g. from the old Vertex writer). Returns what was cleared."""
    held = writer_held(store)
    store.kv_set("writer_held", "{}")
    return held


class _Sim:  # originality summary as saved for a held (voice-delayed) video
    def __init__(self, d: dict):
        self._s, self.phrase_overlap, self.structure_ratio = d["summary"], d["phrase_overlap"], d["structure_ratio"]
        self.ok, self.reasons = True, []

    def summary(self) -> str:
        return self._s


def render_and_review(job, script, brief, claims, ctx: dict, settings: Settings, store: JobStore, send: bool,
                      workers: int | None, report: dict | None = None, item=None) -> tuple:
    """Render + review package + Telegram; voice and image spend is logged against this video (cost-report)."""
    from .studio import costs

    with costs.tag(job.id):
        return _render_and_review(job, script, brief, claims, ctx, settings, store, send, workers, report, item)


def _render_and_review(job, script, brief, claims, ctx: dict, settings: Settings, store: JobStore, send: bool,
                       workers: int | None, report: dict | None = None, item=None) -> tuple:
    """Render one scripted video and send it for review. If the locked voice is unavailable (Gemini error after
    retries, budget cap, paid voice off), the video is HELD: it stays scripted, is re-rendered later by
    retry_held_videos(), and you get a Telegram alert. Never falls back to another voice."""
    from .render.animated import render_animated
    from .studio import disclosure, factcheck, originality
    from .tts.voice_lock import VoiceUnavailable

    out = settings.output_dir / job.id
    today = date.fromisoformat(ctx["date"])
    creator, writer, sim = ctx["creator"], ctx["writer"], _Sim(ctx["sim"])
    try:
        art_stats, rs = {}, settings          # rs: the settings this video is rendered with
        from .content.short_fit import ShortTooLong

        tempo = 1.0
        from .content.short_fit import merge_tiny_scenes

        script = merge_tiny_scenes(script)   # no clip is voiced alone with only a few words
        if script.format == "short":  # voice + measure BEFORE rendering; held (not rendered) if it can't fit
            script, tempo, voiced = fit_short_voice(script, settings, out, job.id)
        if getattr(settings, "theme", "") == "doodle":  # full pictures: key scenes + library places + Max
            from dataclasses import replace as _replace

            from .art.doodle_prep import DoodleUnavailable, prepare

            try:
                script, art_stats = prepare(script, out, settings, store)
            except DoodleUnavailable as exc:   # never a half-empty doodle video: this one uses the editorial style
                log.warning("doodle style unavailable for %s: %s", job.id, exc)
                rs = _replace(settings, theme="editorial")
                art_stats = {"note": f"doodle style unavailable ({exc}); made in the editorial style"}
        if script.format == "long" and getattr(rs, "theme", "") != "doodle":  # AI illustrations (editorial)
            from .art.ai_visuals import illustrate_scenes

            script, more = illustrate_scenes(script, out, rs, store)
            art_stats = {**more, **({"note": art_stats["note"]} if art_stats.get("note") else {})}
        res = _render_with_retry(render_animated, script, out, rs, workers, tempo)
        if script.format == "short":  # the FINISHED file is measured too; never sent over the limit
            res.duration = max(res.duration, _video_seconds(res.video))
            if res.duration > settings.short_max_seconds:
                raise ShortTooLong(f"the finished Short is {_mss(res.duration)} (limit {_mss(settings.short_max_seconds)}"
                                   f", voice measured {_mss(voiced)}, tempo x{tempo:.2f}); rendered but NOT sent",
                                   seconds=res.duration, rendered=True)
        if script.format == "short":
            claims = factcheck.check_claims(script, brief, creator)  # the fact check matches the final words
        disc = disclosure.disclosure_for(res.voice)
        desc = factcheck.add_sources_to_description(script.description, claims)
        desc = disclosure.add_note(desc, disc)
        from .content.packaging import add_affiliate_disclosure, title_options
        from .studio.pillars import pillar_of, series_for

        from .studio.affiliates import add_placeholder, category_for

        aff_cat = category_for(brief.topic_key, ctx.get("card"))
        desc = add_placeholder(desc, aff_cat)  # "[AFFILIATE: category]": no real links yet
        desc = add_affiliate_disclosure(desc, settings.affiliate_disclosure)
        script = script.model_copy(update={"description": finalize_description(
            desc, [s.heading for s in script.scenes], res.scene_starts or [], script.format == "long")})
        Path(job.script_path).write_text(script.model_dump_json(indent=2))
        theme = getattr(rs, "theme", "editorial")
        thumb, thumb_how = make_thumbnails(script, brief, out, rs, store, today, theme)
        from .research.competitors import load_latest, too_similar

        comp = load_latest()
        opts = title_options(brief, script)
        own = [t for t in opts if not too_similar(t, comp)] or opts  # never close to a competitor's title
        (out / "metadata.json").write_text(json.dumps(
            {"title": own[0], "title_options": own,
             "titles_dropped_as_too_close_to_competitors": [t for t in opts if t not in own],
             "description": script.description, "tags": script.tags,
             "topic_key": brief.topic_key, "category": brief.category, "market": brief.market,
             "pillar": getattr(pillar_of(brief.topic_key), "key", None),
             "series": series_for(brief.topic_key, today),
             "format": script.style, "creator_input": creator, "affiliate_category": aff_cat, "picked_by_you": item is not None,
             "research_score": brief.score, "confidence": brief.confidence, "writer": writer,
             "voice": res.voice, "render_seconds": round(res.render_seconds, 1),
             "youtube_altered_content": disc.youtube_altered_content, "disclosure": disc.reasons,
             "fact_check": {s: sum(c.status == s for c in claims)
                            for s in ("source", "calculation", "reference", "creator", "UNSOURCED")},
             "originality": {"phrase_overlap": round(sim.phrase_overlap, 3),
                             "structure_similarity": round(sim.structure_ratio, 3)},
             "pronunciation_misses": res.unknown_words,
             "thumbnail_options": thumb_how, "scene_art": art_stats, "tts": _tts_record(settings)}, indent=2))
        job.video_path, job.subtitles_path = str(res.video), str(res.srt)
        job.thumbnail_path, job.duration_sec = str(thumb), round(res.duration, 2)
        store.transition(job, JobStatus.RENDERED, f"{res.duration:.1f}s in {res.render_seconds:.0f}s")
        originality.record(store, script, brief.topic_key, today)
        _release_held(store, job.id)
    except VoiceUnavailable as exc:  # hold the video; no other voice is ever used
        log.warning("voice unavailable for %s: %s", job.id, exc)
        (out / "held_render.json").write_text(json.dumps(ctx, indent=2))
        first = _hold(store, job.id, str(exc))
        if first and send:
            _notify(settings, f"⏸ GLIVARAO: video {job.id} ({script.format}, \"{brief.topic}\") is ON HOLD: "
                              f"{exc}\nNo other voice is used. I'll retry every hour and send the review as soon "
                              "as the Charon voice works again. Your buffer of approved videos covers the schedule.")
        return (job.id, script.format, "held", None, str(exc)[:200])
    except ShortTooLong as exc:  # HELD: stays scripted, never sent; you get one alert
        log.warning("%s: %s", job.id, exc)
        held = json.loads(store.kv_get("length_held", "{}"))
        held[job.id] = {"since": date.today().isoformat(), "seconds": round(exc.seconds, 1),
                        "rendered": exc.rendered, "reason": str(exc)[:300]}
        store.kv_set("length_held", json.dumps(held))
        if send:
            _notify(settings, f"✂️ GLIVARAO: Short {job.id} (\"{brief.topic}\") is ON HOLD, NOT sent: {exc}. "
                              f"Limit {_mss(settings.short_max_seconds)}. Nothing else was done. To make it again "
                              f"(shorter script, re-voiced): python -m glivarao remake {job.id}")
        return (job.id, script.format, "held", None, str(exc)[:200])
    except Exception as exc:  # one failed render must not stop the other videos
        log.exception("render failed for %s", job.id)
        job = store.get(job.id)
        if JobStatus.FAILED in ALLOWED[job.status]:
            store.transition(job, JobStatus.FAILED, f"{type(exc).__name__}: {exc}"[:500])
        return (job.id, script.format, "failed", None, str(exc)[:200])
    finally:
        _budget_alert(settings, store, send)

    note = ""
    if send and settings.telegram_bot_token and settings.telegram_approver_chat_id:
        from .publish.telegram import request_approval

        why_md = out / "why_this_topic.md"
        why_md.write_text(_why_card(brief, report or {"ranked": []}, item))
        preview = None
        if script.format == "long":
            from .render.video import preview_clip

            preview = preview_clip(res.video, out / "preview.mp4")
        checks = "\n\n".join([_topic_block(brief, item, script, store, today, writer, res.duration),
                               ctx["compliance"], sim.summary(),
                               factcheck.report(claims), disc.review_text()])
        attachments = [(why_md, "Why this topic (research evidence)"),
                       (out / "fact_check.md", "Fact check: every number and its source"),
                       (out / "fact_sheet.md", "Fact sheet (sources and calculations)")]
        from .studio import quiet

        if quiet.is_quiet(settings):  # no messages at night: the review is delivered when quiet hours end
            (out / "review_checks.txt").write_text(checks)
            quiet.queue_review(store, job.id, {"checks": str(out / "review_checks.txt"),
                                               "preview": str(preview) if preview else "",
                                               "attachments": [[str(p), cap] for p, cap in attachments]})
            note = f"review queued until {settings.quiet_end} ({settings.local_tz})"
        else:
            try:
                request_approval(job, store, settings, script, checks, preview=preview, attachments=attachments)
                note = "sent to Telegram"
            except Exception as exc:  # noqa: BLE001  never re-produce a finished video because Telegram hiccuped
                log.warning("review for %s not sent (%s); queued for the next poll", job.id, exc)
                (out / "review_checks.txt").write_text(checks)
                quiet.queue_review(store, job.id, {"checks": str(out / "review_checks.txt"),
                                                   "preview": str(preview) if preview else "",
                                                   "attachments": [[str(p), cap] for p, cap in attachments]})
                note = "review queued (Telegram error); the 5-minute poll will deliver it"
    elif send:
        note = "Telegram not configured: review files in the output folder"
    job = store.get(job.id)
    return (job.id, script.format, job.status.value, job.video_path, note)


# ------------------------------------------------------------------------------------- held videos (voice)
def held_videos(store: JobStore) -> dict:
    return json.loads(store.kv_get("voice_held", "{}"))


def _hold(store: JobStore, job_id: str, reason: str) -> bool:
    """Returns True the first time a video is held (so you get one alert, not one per retry)."""
    held = held_videos(store)
    first = job_id not in held
    held[job_id] = {"since": held.get(job_id, {}).get("since") or date.today().isoformat(), "reason": reason[:300]}
    store.kv_set("voice_held", json.dumps(held))
    return first


def _release_held(store: JobStore, job_id: str) -> None:
    held = held_videos(store)
    if held.pop(job_id, None) is not None:
        store.kv_set("voice_held", json.dumps(held))


def remake_video(settings: Settings, store: JobStore, job_id: str, send: bool = True,
                 workers: int | None = None) -> tuple:
    """Make a finished video again from its saved script and facts, with the CURRENT voice and length rules
    (e.g. a Short that came out too long). The old job is retired (rejected/failed) so it can't be uploaded."""
    import shutil

    from .studio.pause import guard

    guard(settings, f"remake of {job_id}")
    from .content.brief import load_brief
    from .models import Script
    from .studio import factcheck

    old = store.get(job_id)
    if old.status == JobStatus.SCRIPTED and job_id in held_videos(store):
        raise ValueError(f"{job_id} is on hold: it is re-made by the hourly retry (python -m glivarao retry-held)")
    if old.status in (JobStatus.APPROVED, JobStatus.PUBLISHED):
        raise ValueError(f"{job_id} is already {old.status.value}; nothing to remake")
    src = settings.output_dir / old.id
    script = Script.model_validate_json((src / "script.json").read_text())
    brief = load_brief(src / "brief.json")
    meta = json.loads((src / "metadata.json").read_text()) if (src / "metadata.json").exists() else {}
    ctx_file = src / "held_render.json"
    ctx = json.loads(ctx_file.read_text()) if ctx_file.exists() else {
        "writer": meta.get("writer", "remake"), "creator": meta.get("creator_input", ""), "item_id": None,
        "date": date.today().isoformat(), "compliance": f"Remade from {old.id} (same script, current voice).",
        "sim": {"summary": f"Originality: same script as {old.id} (already checked).",
                "phrase_overlap": 0.0, "structure_ratio": 0.0}}
    ctx["date"] = date.today().isoformat()
    lh = json.loads(store.kv_get("length_held", "{}"))
    if script.format == "short" and old.id in lh:  # held for length: start from a proportionally shorter script
        from .content.short_fit import trim_to_words, words_for

        script = trim_to_words(script, words_for(lh[old.id]["seconds"], script.word_count,
                                                 settings.short_target_seconds))
        lh.pop(old.id)
        store.kv_set("length_held", json.dumps(lh))
    new = store.create(script.format, old.topic)
    from .studio import costs

    costs.link(old.id, new.id, cost_dir(settings))   # what the first version cost counts toward the remake
    out = settings.output_dir / new.id
    out.mkdir(parents=True, exist_ok=True)
    for name in ("brief.json", "fact_sheet.md", "fact_check.md"):
        if (src / name).exists():
            shutil.copy(src / name, out / name)
    new.script_path = str(out / "script.json")
    Path(new.script_path).write_text(script.model_dump_json(indent=2))
    store.transition(new, JobStatus.SCRIPTED, f"remake of {old.id}")
    retire = JobStatus.REJECTED if old.status == JobStatus.PENDING_APPROVAL else JobStatus.FAILED
    if retire in ALLOWED[old.status]:
        store.transition(old, retire, f"remade as {new.id}")
    claims = factcheck.check_claims(script, brief, ctx.get("creator", ""))
    return render_and_review(store.get(new.id), script, brief, claims, ctx, settings, store, send, workers)


def retry_held_videos(settings: Settings, store: JobStore, send: bool = True, workers: int | None = None) -> list:
    """Re-render videos held because the voice was unavailable (systemd: hourly, and before every daily run)."""
    from .studio.pause import guard

    guard(settings, "retry of held videos")
    from .content.brief import build_brief
    from .models import Script
    from .studio import factcheck
    from .studio.queue import TopicQueue

    done = []
    for job_id in list(held_videos(store)):
        try:
            job = store.get(job_id)
        except KeyError:
            _release_held(store, job_id)
            continue
        if job.status != JobStatus.SCRIPTED:
            _release_held(store, job_id)
            continue
        out = settings.output_dir / job.id
        ctx = json.loads((out / "held_render.json").read_text())
        brief = build_brief(ctx["card"], date.fromisoformat(ctx["date"]))  # same inputs -> the same brief
        script = Script.model_validate_json(Path(job.script_path).read_text())
        claims = factcheck.check_claims(script, brief, ctx["creator"])
        item = TopicQueue(store).get(ctx["item_id"]) if ctx.get("item_id") else None
        cached = Path("reports/research") / f"{ctx['date']}.json"
        report = json.loads(cached.read_text()) if cached.exists() else None
        r = render_and_review(job, script, brief, claims, ctx, settings, store, send, workers, report, item)
        done.append(r)
        if r[2] == "held":
            break  # the voice is still down: don't hammer the API with the rest
        if send:
            _notify(settings, f"▶️ GLIVARAO: held video {job.id} (\"{brief.topic}\") rendered with the Charon voice; "
                              "the review is in Telegram.")
    return done


def _budget_alert(settings: Settings, store: JobStore, send: bool) -> None:
    """One Telegram alert per month at 80% of each budget (voice, Claude), and one when a cap is reached."""
    from .studio.health import spend_alerts

    for text in spend_alerts(settings, store):
        if send:
            _notify(settings, text)

# ------------------------------------------------------------------------------------- held for the writer
def _hold_for_writer(settings: Settings, store: JobStore, today: date, topic: str, why: str, send: bool) -> DailyResult:
    """Claude couldn't write (quota, outage...): nothing is produced, the topic stays planned, the hourly retry
    runs production again, and you get one alert per day."""
    held = json.loads(store.kv_get("writer_held", "{}"))
    first_today = held.get("alerted") != today.isoformat()
    held.update(since=held.get("since") or today.isoformat(), reason=why[:300], topic=topic,
                alerted=today.isoformat())
    store.kv_set("writer_held", json.dumps(held))
    if first_today and send:
        _notify(settings, f"⏸ GLIVARAO: Claude can't write right now ({why[:200]}). Today's videos are on hold "
                          f"(\"{topic}\"); no other writer is used. I retry every hour and tell you when it works. "
                          "Check: python -m glivarao doctor --live")
    return DailyResult(topic, "claude (held)", note=f"held: waiting for Claude ({why[:120]})")


def make_thumbnails(script, brief, out: Path, settings: Settings, store: JobStore, today: date,
                    theme: str) -> tuple[Path, list[str]]:
    """The video's thumbnail(s): long = 3 options (you pick in Telegram), Short = 1. Returns (first, how).
    Doodle theme: a complete 2-4 word headline + ONE number badge, or a line chart only with >= 3 real data
    points from the fact sheet (art.doodle.thumb_data)."""
    from .render.thumbnail_editorial import make_thumbnail

    if theme == "doodle":
        from .art.ai_visuals import bold_words
        from .art.doodle import thumb_data
        from .art.doodle import thumbnail as doodle_thumb
        from .art.max_assets import load_pose

        data = thumb_data([(f.text, f.url) for f in brief.facts if f.kind == "DATA" and f.url], today.year)
        words_list = bold_words(script, 3 if script.format == "long" else 1)
        paths = []
        for k, (words, emo) in enumerate(zip(words_list, ("shocked", "worried", "pointing"))):
            dst = out / (f"thumbnail_{k + 1}.jpg" if script.format == "long" else "thumbnail.jpg")
            doodle_thumb(words, emo, dst, seed=k + 1, max_img=load_pose(settings, emo), value=data["value"],
                         points=data["points"])
            paths.append(dst)
        panel = (f"line chart of {len(data['points'])} real data points" if data["points"] else
                 f"number badge {data['value']}" if data["value"] else "no number")
        return paths[0], [f"doodle (code-drawn) \"{w}\", {panel}" for w in words_list[:len(paths)]]
    if script.format == "long":  # 3 options (AI + our own bold words); you pick one in Telegram
        from .art.ai_visuals import thumbnail_options

        opts_paths, how = thumbnail_options(
            script, out, settings, store,
            fallback=lambda sc, dst: make_thumbnail(sc, dst, portrait=False, theme=theme))
        thumb = opts_paths[0] if opts_paths else make_thumbnail(script, out / "thumbnail.jpg", theme=theme)
        return thumb, how
    return make_thumbnail(script, out / "thumbnail.jpg", portrait=True, theme=theme), []


def thumb_remake(settings: Settings, store: JobStore, job_id: str, send: bool = True, client=None) -> dict:
    """Make the video's thumbnail(s) again with the current rules (complete headline; number badge unless the
    fact sheet has >= 3 real data points) and send them to Telegram. The video itself is not touched."""
    from .content.brief import load_brief
    from .models import Script
    from .studio import costs

    job = store.get(job_id)
    out = settings.output_dir / job.id
    script = Script.model_validate_json((out / "script.json").read_text())
    brief = load_brief(out / "brief.json")
    meta_file = out / "metadata.json"
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    was_doodle = any(str(h).startswith("doodle") for h in meta.get("thumbnail_options", []))
    theme = "doodle" if was_doodle else getattr(settings, "theme", "editorial")
    day = date.fromisoformat(brief.date) if getattr(brief, "date", "") else date.today()
    with costs.tag(job.id):
        thumb, how = make_thumbnails(script, brief, out, settings, store, day, theme)
    old = Path(job.thumbnail_path).name if job.thumbnail_path else ""
    keep = out / old if old and (out / old).exists() and script.format == "long" else thumb
    job.thumbnail_path = str(keep)        # a long video keeps the option you picked (same number, new image)
    store.save(job)
    if meta:
        meta["thumbnail_options"] = how
        meta_file.write_text(json.dumps(meta, indent=2))
    if send:
        from .publish.telegram import _client, send_thumbnail_picker

        c = _client(settings, client)
        chat = settings.telegram_approver_chat_id
        c.call("sendMessage", chat_id=chat, text=f"🖼 New thumbnail for {job.id} (\"{job.topic}\"): "
                                                 + "; ".join(how)[:600])
        if script.format == "long":
            send_thumbnail_picker(job, settings, c)
        else:
            with open(thumb, "rb") as fh:
                c.call("sendPhoto", files={"photo": fh}, chat_id=chat, caption=f"{job.id}: new thumbnail")
    return {"job": job.id, "thumbnail": str(job.thumbnail_path), "how": how, "theme": theme}


def _tts_record(settings: Settings) -> dict:
    """The exact voice settings used for this video (so it can be found and locked again later)."""
    if settings.tts_provider != "gemini_tts":
        return {"provider": settings.tts_provider}
    from .tts.voice_lock import style_prompt

    from .tts.gemini_tts import PROMPT_VERSION

    return {"provider": "gemini_tts", "model": settings.gemini_tts_model, "voice": settings.gemini_tts_voice,
            "pace": settings.gemini_tts_pace, "style": settings.gemini_tts_style, "style_sent": style_prompt(settings),
            "direction_sent": settings.gemini_tts_direction, "prompt": PROMPT_VERSION,
            "pace_wpm": settings.tts_pace_wpm,
            "speed": settings.gemini_tts_speed}


def _mss(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"


def _voice_seconds(script, settings: Settings, out: Path, tempo: float = 1.0) -> float:
    """Voice the Short with the locked voice (clips are cached, so the render reuses them at no extra cost),
    write the narration exactly as the render will build it, and measure the REAL length with ffprobe."""
    import numpy as np
    import soundfile as sf

    from .tts.kokoro import KOKORO_SR
    from .tts.narrator import get_narrator, narrate_all

    texts = [s.narration for s in script.scenes]
    choice = get_narrator(settings, "\n\n".join(texts))
    if tempo != 1.0 and hasattr(choice.narrator, "speed"):
        if hasattr(choice.narrator, "boost"):
            choice.narrator.boost = choice.narrator.boost * tempo
        else:
            choice.narrator.speed = choice.narrator.speed * tempo
    narrations, _ = narrate_all(choice, texts, settings)
    audio = np.concatenate([n.audio for n in narrations])
    out.mkdir(parents=True, exist_ok=True)
    wav = out / "short_voice_check.wav"
    sf.write(wav, audio, KOKORO_SR, subtype="PCM_16")
    return _video_seconds(wav) or len(audio) / KOKORO_SR


def fit_short_voice(script, settings: Settings, out: Path, job_id: str = "") -> tuple:
    """Shorts rule (before any rendering): <=SHORT_MAX_WORDS words; voiced length over SHORT_REDO_SECONDS (55 s)
    -> trim and re-voice (max 2 tries); over SHORT_TEMPO_SECONDS (58 s) -> atempo up to SHORT_MAX_TEMPO (1.15x);
    over SHORT_MAX_SECONDS (59 s) -> ShortTooLong (held, not rendered). Returns (script, tempo, seconds)."""
    from .content.short_fit import ShortTooLong, trim_to_words, words_for

    script = trim_to_words(script, settings.short_max_words)
    secs = _voice_seconds(script, settings, out)
    tries = 0
    while secs > settings.short_redo_seconds and tries < 2:
        tries += 1
        log.warning("Short %s voiced at %.1f s (> %.0f s); trimming and re-voicing (try %d)", job_id, secs,
                    settings.short_redo_seconds, tries)
        script = trim_to_words(script, words_for(secs, script.word_count, settings.short_target_seconds))
        secs = _voice_seconds(script, settings, out)
    tempo = 1.0
    if secs > settings.short_tempo_seconds:
        tempo = min(settings.short_max_tempo, secs / settings.short_redo_seconds)
        log.warning("Short %s still %.1f s; speeding up x%.2f", job_id, secs, tempo)
        secs = _voice_seconds(script, settings, out, tempo)
    if secs > settings.short_max_seconds:
        raise ShortTooLong(f"the voiced Short is {_mss(secs)} after {tries} shortening tries and tempo x{tempo:.2f} "
                           f"(limit {_mss(settings.short_max_seconds)}); not rendered", seconds=secs)
    return script, tempo, secs


def _video_seconds(path) -> float:
    """Real length of the finished file (ffprobe); 0 if it can't be read."""
    import subprocess

    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip() or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _release_writer_hold(settings: Settings, store: JobStore, send: bool) -> None:
    held = json.loads(store.kv_get("writer_held", "{}"))
    if held:
        store.kv_set("writer_held", "{}")
        if send:
            _notify(settings, f"▶️ GLIVARAO: Claude is writing again (held since {held.get('since')}); production "
                              "continues.")


def writer_held(store: JobStore) -> dict:
    return json.loads(store.kv_get("writer_held", "{}"))


def _render_with_retry(render_animated, script, out, settings, workers, tempo: float = 1.0):
    """One retry with a single worker: the usual cause of a failed render is memory pressure or a crashed worker.
    A voice outage is not retried here (the voice client already retried with backoff); the video is held."""
    from .tts.voice_lock import VoiceUnavailable

    kw = {"tempo_boost": tempo} if tempo != 1.0 else {}
    try:
        return render_animated(script, out, settings, workers=workers, **kw)
    except VoiceUnavailable:
        raise
    except Exception as exc:
        log.warning("render failed (%s: %s); retrying once with 1 worker", type(exc).__name__, exc)
        return render_animated(script, out, settings, workers=1, **kw)


class AlreadyRunning(RuntimeError):
    pass


def supervised_daily(settings: Settings, store: JobStore, today: date | None = None, send: bool = True,
                     workers: int | None = None, shorts: int | None = None, force: bool = False, retries: int = 1,
                     retry_delay: float = 120.0, lock_path: Path | None = None, notifier=None,
                     scheduled: bool = False) -> DailyResult | None:
    """Production entry point used by the systemd timer.

    - single instance (file lock), so a slow run and the next timer tick never overlap;
    - idempotent: a day that already completed is skipped (use force=True to produce again);
    - checks free disk first; retries a failed run once; on final failure sends a Telegram alert;
    - also alerts when the day finished but any video failed or was rejected by compliance.
    Never uploads, publishes or schedules anything on YouTube."""
    import fcntl

    from .studio.pause import guard

    guard(settings, "daily production")
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
        from .studio import delivery

        plan_ = None
        if scheduled and not force:   # the timer checks every 15 min; start when the delivery plan says so
            ok, plan_ = delivery.due(settings, store)
            if not ok:
                log.info("not yet: planned start %s (%s)", f"{plan_['start']:%H:%M}", plan_["why"])
                return None
            delivery.start_run(settings, store, today, plan_)
        check_disk(Path(settings.output_dir))
        last = None
        for attempt in range(retries + 1):
            try:
                res = run_daily_v2(settings, store, today=today, send=send, workers=workers, shorts=shorts,
                                   ignore_input_wait=bool(plan_) and delivery.input_wait_overridden(settings, plan_),
                                   deliver_day=today if plan_ else None)
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
        elif scheduled:   # nothing produced: the 15-minute timer tries again in 2 hours, not every tick
            store.kv_set(f"daily_retry_after:{today.isoformat()}", str(delivery.now_local(settings).timestamp() + 2 * 3600))
        if plan_:
            delivery.close_day(settings, store, today, notifier)
        bad = [j for j in res.jobs if j[2] in ("failed", "rejected_compliance")]
        if bad:
            notifier(settings, f"GLIVARAO {today}: {len(bad)} of {len(res.jobs)} videos need attention:\n" +
                     "\n".join(f"- {j[0]} ({j[1]}): {j[2]}: {j[4]}" for j in bad))
        try:  # buffer low / disk / spend alerts after every run
            from .studio.health import alerts

            for text in alerts(settings, store):
                notifier(settings, text)
        except Exception:  # noqa: BLE001
            log.exception("health alerts failed")
        return res
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def cost_dir(settings: Settings) -> Path:
    return Path(settings.claude_spend_ledger_path).parent


def _notify(settings: Settings, text: str) -> None:
    try:
        from .publish.telegram import notify

        notify(settings, text)
    except Exception:  # an alert failure must never mask the original error
        log.exception("could not send Telegram alert")


def _topic_block(brief, item, script, store=None, today: date | None = None, writer: str = "",
                 duration: float | None = None) -> str:
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
    if duration:
        m, sec = divmod(int(round(duration)), 60)
        lines.append(f"LENGTH: {m}:{sec:02d} ({script.word_count} words, "
                     f"{script.word_count / max(duration, 1) * 60:.0f} words/min)"
                     + (" — Short, limit 0:59" if script.format == "short" else ""))
    if writer:
        lines.append(f"WRITER: {writer}")
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
