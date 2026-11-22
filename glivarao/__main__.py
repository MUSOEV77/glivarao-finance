"""GLIVARAO Finance command line.

  python -m glivarao doctor                     # what is configured / missing
  python -m glivarao produce --format short     # one video, end to end (dry-run by default)
  python -m glivarao daily                      # 1 long + 2 Shorts
  python -m glivarao list
  python -m glivarao poll-approvals             # read Telegram Approve/Reject presses
  python -m glivarao decide JOB --approve       # operator override (recorded in the audit log)
  python -m glivarao publish JOB                # MANUAL, interactive, private-only upload of an APPROVED job
  python -m glivarao youtube-auth               # one-time OAuth consent
  python -m glivarao analytics
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import logging
import sys

from .config import get_settings
from .models import JobStatus
from .storage import JobStore


def _store(settings):
    return JobStore(settings.db_path)


def cmd_doctor(args, s):
    """Every key and setting (ok / MISSING / INVALID / warn); --live tests each API with a tiny real call."""
    from .doctor import run

    run(s, _store(s), live=args.live, strict=args.strict)
    if args.verbose_config:
        print(json.dumps(s.redacted(), indent=2))


LEGACY_MSG = ("this is the old v1 command (no voice lock, no Shorts length rules, no Claude-only rule, no pause "
              "check). Production uses daily-v2 (timer), remake and shorts-check. For a local dry-run test only: "
              "GLIVARAO_MODE=dry-run python -m glivarao {cmd} --legacy")


def _legacy_allowed(args, s) -> None:
    """Item 6 of the audit: the v1 pipeline is locked. It runs only in dry-run mode with --legacy, never paid."""
    from .studio.pause import guard

    guard(s, f"legacy {args.cmd}")
    if not getattr(args, "legacy", False) or s.mode == "production" or s.allow_paid_apis:
        raise SystemExit(LEGACY_MSG.format(cmd=args.cmd))


def cmd_produce(args, s):
    _legacy_allowed(args, s)
    from .pipeline import produce

    res = produce(s, _store(s), args.format, topic=args.topic, minutes=args.minutes, angle=args.angle or "",
                  tts_provider=args.tts, send_for_approval=not args.no_approval)
    _print_result(res)


def cmd_daily(args, s):
    _legacy_allowed(args, s)
    from .pipeline import daily

    for res in daily(s, _store(s), long_minutes=args.long_minutes, tts_provider=args.tts):
        _print_result(res)


def _print_result(res):
    j = res.job
    print(f"\n{j.id}  [{j.status.value}]  {res.script.title}")
    print(f"  words={res.script.word_count} scenes={len(res.script.scenes)} duration={j.duration_sec}s")
    print(f"  video={j.video_path}\n  thumbnail={j.thumbnail_path}\n  captions={j.subtitles_path}")
    print("  " + res.report.summary().replace("\n", "\n  "))


def cmd_sample(args, s):
    """Render a hand-written sample script with the v2 animated renderer. Local only: never sent anywhere."""
    from datetime import datetime
    from pathlib import Path

    from .compliance import check_script
    from .models import Script
    from .render.animated import render_animated
    from .render.thumbnail import make_thumbnail
    from .render.video import probe

    script = Script.model_validate_json(Path(args.script).read_text())
    report = check_script(script, enforce_length=False)
    if not report.ok:
        raise RuntimeError(report.summary())
    out = s.output_dir / f"sample-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    res = render_animated(script, out, s, voice=args.voice or s.kokoro_voice)
    thumb = make_thumbnail(script, out / "thumbnail.jpg")
    (out / "script.json").write_text(script.model_dump_json(indent=2))
    info = probe(res.video)
    print(f"video={res.video}\nthumbnail={thumb}\ncaptions={res.srt}\nvoice=Kokoro {res.voice}")
    print(f"duration={info['duration']:.2f}s {info['width']}x{info['height']} render={res.render_seconds:.1f}s")
    print(f"pronunciation dictionary misses: {res.unknown_words or 'none'}")
    print(report.summary())


def cmd_research(args, s):
    """R1: research and rank finance topics. Report only: no video production, nothing uploaded."""
    from datetime import date
    from pathlib import Path

    from .research.run import TOP_N, run_research

    day = date.fromisoformat(args.date) if args.date else date.today()
    out = Path(args.out)
    rep = run_research(day, out, _store(s))
    for src in rep["sources"]:
        print(f"[{'ok' if src['ok'] else '--'}] {src['name']}: {src['detail']}")
    print(f"\n{'#':>2} {'score':>5}  {'conf':6} {'market':6} {'category':28} topic")
    for t in rep["ranked"][:TOP_N]:
        print(f"{t['rank']:>2} {t['score']:>5}  {t['confidence']:6} {t['market']:6} {t['category']:28} {t['topic']}")
    print(f"\nreport: {out / (day.isoformat() + '.md')}  (rejected off-topic: {len(rep['rejected_off_topic'])})")


def cmd_backtest(args, s):
    """Historical replay of the research for past dates (accelerated validation; not live observations)."""
    from datetime import date
    from pathlib import Path

    from .research.backtest import backtest

    dates = [date.fromisoformat(d) for d in args.dates.split(",")]
    res = backtest(dates, Path(args.out))
    print(res["kind"])
    for d in res["dates"]:
        r = res["runs"][d]
        print(f"{d}: recommended={r['recommended']} sources={len(r['sources_ok'])} rejected={r['rejected']}")
        print("   top: " + " | ".join(r["labels"][:6]))
    for p in res["consecutive_overlap"]:
        print(f"top-10 overlap {p['from']} -> {p['to']}: {p['top_overlap_jaccard']}")
    print("in top-10 every time:", res["in_top_every_time"])


def cmd_daily_v2(args, s):
    """Autonomous daily production (research -> topic -> scripts -> video -> Telegram review). Never uploads."""
    from datetime import date

    from .daily_v2 import AlreadyRunning, supervised_daily

    day = date.fromisoformat(args.date) if args.date else None
    try:
        res = supervised_daily(s, _store(s), today=day, send=not args.no_telegram, workers=args.workers,
                               shorts=args.shorts, force=args.force, retries=args.retries)
    except AlreadyRunning as exc:
        print(f"skipped: {exc}")
        return
    if res is None:
        print("skipped: today's daily set was already produced (use --force to produce again)")
        return
    if not res.jobs:
        print(f"nothing produced today: {res.note}")
        return
    print(f"topic: {res.topic}\nformat: {res.style}\nwriter: {res.writer}")
    for job_id, fmt, status, video, note in res.jobs:
        print(f"  {job_id:28s} {fmt:5s} {status:20s} {video or ''} {note}")


def cmd_propose(args, s):
    """Send this week's 5-7 topic ideas to Telegram (you pick which ones get made)."""
    from datetime import date

    from .studio.proposals import propose_topics

    day = date.fromisoformat(args.date) if args.date else None
    items = propose_topics(s, _store(s), today=day, send=not args.no_telegram)
    for it in items:
        print(f"  [{it.id}] {it.topic} ({it.category})")
    print(f"{len(items)} new ideas" + ("" if args.no_telegram else " sent to Telegram"))


def cmd_plan(args, s):
    """Pick the next topic automatically and announce it in Telegram (with why + sources)."""
    from datetime import date

    from .studio.planner import plan_next


    from .daily_v2 import pace_check

    day = date.fromisoformat(args.date) if args.date else None
    store = _store(s)
    today = day or date.today()  # announced 09:00 Tashkent, produced 13:17 the same day
    ok, why = pace_check(store, today, s)
    if not ok and not args.force:
        print(f"no long video due today ({why}); today is a Shorts day")
        return
    it = plan_next(s, store, today=day, send=not args.no_telegram)
    if it is None:
        print("no topic passed today's checks")
        return
    print(f"next video: {it.topic} [{it.format}] status={it.status}")
    for w in it.why:
        print(f"  - {w}")


def cmd_pack(args, s):
    """(Re)send the upload pack of an approved video to Telegram: full-quality file, titles, description, tags,
    thumbnail and suggested publish time. Uploads nothing."""
    from .studio.uploadpack import send_pack

    store = _store(s)
    job = store.get(args.job_id)
    if job.status not in (JobStatus.APPROVED, JobStatus.PUBLISHED):
        raise SystemExit(f"{job.id} is {job.status.value}: approve it in Telegram first")
    print(send_pack(job, s, store))


def cmd_voice_audition(args, s):
    """Voice the same 30 s script with several voices and send them to Telegram with pick buttons."""
    from .studio import voice_audition

    store = _store(s)
    cands = [(v, 1.15 if v == "Charon" else None) for v in args.voices] if args.voices else voice_audition.CANDIDATES
    results = voice_audition.make_samples(s, store, Path(s.output_dir) / "voice_audition", candidates=cands)
    for r in results:
        print(f"{r['voice']:10s} " + (f"{r['wpm']} wpm (raw {r['wpm_raw']}, speed x{r['speed']}) {r['path']}"
                                      if "path" in r else f"FAILED: {r['error']}"))
    if not args.no_telegram:
        print(f"sent {voice_audition.send_samples(s, results)} samples to Telegram")


def cmd_voice_pick(args, s):
    """Lock a voice from the last audition (same as tapping its button in Telegram)."""
    from .studio import voice_audition

    print(voice_audition.pick(s, _store(s), args.voice))
    print("Held videos are re-voiced by the hourly retry, or now with: python -m glivarao retry-held")


def cmd_voice_lock(args, s):
    """Show the locked channel voice, voice budget and held videos; --reset accepts changed voice settings."""
    from datetime import date as _d

    from .daily_v2 import held_videos
    from .tts import voice_lock
    from .tts.gemini_tts import SpendLedger

    store = _store(s)
    if args.reset:
        print("voice lock reset to:", json.dumps(voice_lock.reset(s, store)))
        return
    saved = store.kv_get("voice_lock")
    print(f"provider: {s.tts_provider}   model: {s.gemini_tts_model}   voice: {s.gemini_tts_voice}   "
          f"pace: {s.gemini_tts_pace}   speed: x{s.gemini_tts_speed} (target {s.tts_target_wpm} wpm)")
    print(f"style: {s.gemini_tts_style}")
    print("lock:", saved or "not recorded yet (recorded on the first narration)")
    try:
        voice_lock.check_model(s.gemini_tts_model)
        cur = voice_lock.fingerprint(s)
        print("matches lock:", "yes" if not saved or json.loads(saved) == cur else "NO (videos are held; use --reset "
                                                                                     "if the change is intentional)")
    except voice_lock.VoiceUnavailable as exc:
        print("PROBLEM:", exc)
    spent = SpendLedger(Path(s.tts_spend_ledger_path)).spent(_d.today().strftime("%Y-%m"))
    print(f"voice budget this month: ${spent:.2f} of ${s.tts_monthly_budget_usd:.2f} "
          f"(alert at {s.tts_alert_ratio:.0%})")
    held = held_videos(store)
    print(f"held videos: {len(held)}" + "".join(f"\n  {k}: since {v['since']}: {v['reason']}" for k, v in held.items()))


def cmd_retry_held(args, s):
    """Hourly (glivarao-voice-retry.timer): re-render videos held for the voice, and re-run today's production if
    it was held because Claude couldn't write. Never crash-loops; the next hour tries again."""
    import fcntl
    from datetime import date as _d

    from .daily_v2 import AlreadyRunning, held_videos, retry_held_videos, supervised_daily, writer_held

    from .studio.pause import status as pause_status

    if pause_status(s):
        print("production is PAUSED: nothing retried (resume with: python -m glivarao resume)")
        return
    store = _store(s)
    send = not args.no_telegram
    if not held_videos(store) and not writer_held(store):
        print("nothing on hold")
        return
    if held_videos(store):
        lock = Path(s.db_path).with_name("daily.lock")  # the same lock as the daily run: never render twice at once
        with open(lock, "w") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("the daily run is busy; it retries held videos itself")
                return
            try:
                for r in retry_held_videos(s, store, send=send):
                    print(r[0], r[2], r[4] or "")
            except Exception as exc:  # noqa: BLE001
                logging.getLogger("glivarao").exception("retry of held videos failed")
                print(f"retry failed ({type(exc).__name__}); trying again next hour")
    if writer_held(store):  # production waited for Claude: try today's run again (it takes the lock itself)
        try:
            res = supervised_daily(s, store, today=_d.today(), send=send, retries=0)
            print("production:", (res.note or res.jobs) if res else "already done today")
        except AlreadyRunning:
            print("the daily run is busy")
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("glivarao").exception("held production retry failed")
            print(f"production retry failed ({type(exc).__name__}); trying again next hour")


def cmd_voice_of(args, s):
    """Print the exact voice, style prompt and speed a video was made with."""
    from datetime import date as _d

    from .tts.voice_of import find_jobs, identify

    store = _store(s)
    if args.job_id:
        jobs = [store.get(args.job_id)]
    else:
        jobs = find_jobs(store, args.find or "", "short" if args.short else ("long" if args.long else None),
                         _d.fromisoformat(args.date) if args.date else _d.today())
    if not jobs:
        print("no matching job (try --date YYYY-MM-DD, or give the job id)")
        return
    for job in jobs:
        info = identify(s, job)
        dur = f"{int(job.duration_sec or 0) // 60}:{int(job.duration_sec or 0) % 60:02d}"
        when = ""
        try:
            from datetime import datetime as _dt
            from zoneinfo import ZoneInfo

            ev = [e for e in store.events(job.id) if e["to_status"] == "pending_approval"]
            stamp = ev[-1]["at"] if ev else job.updated_at
            when = _dt.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(ZoneInfo(s.local_tz)).strftime(
                "sent %H:%M Tashkent")
        except Exception:  # noqa: BLE001
            pass
        title = ""
        mp = Path(job.video_path).parent / "metadata.json" if job.video_path else None
        if mp and mp.exists():
            title = json.loads(mp.read_text()).get("title", "")
        print(f"\n{job.id}  [{job.format}, {dur}, {job.status.value}, {when}]  {job.topic}\n  title           {title}")
        for k in ("voice", "model", "pace", "speed", "style", "how", "scenes_matched", "voice_label"):
            if k in info:
                v = info[k]
                if k == "speed" and not info.get("speed_measured", True):
                    v = f"{v} (from .env; not measured)"
                print(f"  {k:15s} {v}")
    print(f"\nTo lock one: python -m glivarao voice-lock-from {jobs[0].id}")


def cmd_voice_lock_from(args, s):
    """Lock exactly the voice (model, voice, style, pace, speed) used by a job, for every video."""
    from .tts.voice_of import lock_from

    for k, v in lock_from(s, _store(s), args.job_id).items():
        print(f"{k}={v}")
    print("locked. Held videos are re-voiced by the hourly retry (or now: python -m glivarao retry-held)")


def cmd_pause(args, s):
    """Pause all production (survives updates and reboots), show the pause, or resume (explicit only)."""
    from .studio import pause

    if args.status:
        st = pause.status(s)
        print(f"PAUSED since {st['since']} ({st['reason']})" if st else "running (not paused)")
        return
    info = pause.pause(s, args.reason)
    print(f"PAUSED since {info['since']}: no production, no retries, no remakes, no paid calls. "
          "Telegram, health report and backups stay on. Resume only with: python -m glivarao resume")


def cmd_resume(args, s):
    from .studio import pause

    print("resumed: production runs at the next scheduled time" if pause.resume(s) else "was not paused")


def cmd_claude_quota(args, s):
    """Is the Claude writer usable? One tiny real call (+ Vertex quota limits when WRITER=claude_vertex)."""
    from .daily_v2 import writer_held
    from .scriptgen.vertex_quota import live_test, quota_status

    from .studio.pause import status as pause_status

    if pause_status(s):
        print("PAUSED: no test call made (it would cost a fraction of a cent). Quota status only:")
    else:
        ok, msg = live_test(s)
        print(("OK   " if ok else "WAIT ") + msg)
    for line in (quota_status(s) if s.writer == "claude_vertex" else []):
        print(line)
    held = writer_held(_store(s))
    if held:
        print(f"Production on hold since {held.get('since')}; it retries every hour and starts by itself.")


def cmd_remake(args, s):
    """Make a finished video again with the current voice and length rules (the old one is retired)."""
    from .daily_v2 import remake_video

    r = remake_video(s, _store(s), args.job_id, send=not args.no_telegram)
    print(r[0], r[2], r[4] or "")


def cmd_shorts_check(args, s):
    """List Shorts waiting for review (or held) that are over the limit, measured on the real file (ffprobe).
    --remake makes each one again with the current length rules and rejects the old one (never approved ones)."""
    import json as _json

    from .daily_v2 import _video_seconds, remake_video
    from .models import JobStatus

    store = _store(s)
    held = _json.loads(store.kv_get("length_held", "{}"))
    bad = []
    for job in store.list(limit=500):
        if job.format != "short" or job.status not in (JobStatus.RENDERED, JobStatus.PENDING_APPROVAL,
                                                        JobStatus.SCRIPTED):
            continue
        secs = _video_seconds(job.video_path) if job.video_path else 0.0
        if secs > s.short_max_seconds or job.id in held:
            bad.append((job, secs or held.get(job.id, {}).get("seconds", 0.0)))
    if not bad:
        print(f"OK: no Short in the queue is over {s.short_max_seconds:.0f} s")
        return
    for job, secs in bad:
        m, sec = divmod(int(round(secs)), 60)
        print(f"TOO LONG  {job.id}  {m}:{sec:02d}  {job.status.value}  {job.topic}")
    if not args.remake:
        print(f"{len(bad)} Short(s) over the limit. Remake them (old ones rejected): python -m glivarao shorts-check "
              "--remake")
        return
    for job, _ in bad:
        r = remake_video(s, store, job.id, send=not args.no_telegram)
        print(f"remade {job.id} -> {r[0]}: {r[2]} {r[4] or ''}")


def cmd_launch_list(args, s):
    """Show the US-only launch list (and its approval state); --send puts it in Telegram with an approve button."""
    from .studio import launch_plan

    store = _store(s)
    print(launch_plan.approval_text())
    print(f"\nstatus: {'APPROVED' if launch_plan.approved(store) else 'waiting for your approval'} "
          f"(version {launch_plan.VERSION}); {launch_plan.remaining(store)} of {len(launch_plan.LAUNCH)} still to make")
    if args.verify:
        for v in launch_plan.LAUNCH:
            kept, notes = launch_plan.verify_facts(v)
            print(f"{v.n:2d}. {len(kept)}/{len(v.facts)} facts confirmed" + "".join(f"\n    ⚠ {n}" for _, n in notes))
    if args.send:
        launch_plan.send_for_approval(s, store)
        print("sent to Telegram (no production is started)")


def cmd_style_samples(args, s):
    """Doodle style samples (Max reference sheet, 3 frames, 3 thumbnails, a motion clip); --send to Telegram."""
    from pathlib import Path

    from .studio import style_samples

    out = Path(args.out) if args.out else s.output_dir / "style_samples" / style_samples.VERSION
    res = style_samples.make(out)
    print(f"made in {out} (code-drawn, nothing spent):")
    for k in ("reference", "frames", "thumbs", "motion"):
        for p in (res[k] if isinstance(res[k], list) else [res[k]]):
            print("  ", p)
    if args.send:
        style_samples.send(s, res)
        print("sent to Telegram with Approve / Request changes buttons (production stays paused)")


def cmd_competitors(args, s):
    """Competitor research: patterns from similar channels' last 90 days (YouTube Data API, read-only)."""
    from .research.competitors import YouTubeAPIError, render_markdown, run

    try:
        rep = run(s, _store(s))
    except YouTubeAPIError as exc:
        raise SystemExit(f"competitor research failed: {exc}")
    print(render_markdown(rep))
    if not args.no_telegram and s.telegram_bot_token and s.telegram_approver_chat_id:
        from .publish.telegram import notify

        t, ln = rep["titles"], rep["length"]
        top = ", ".join(f"{k} ({v['score']})" for k, v in list(rep["topics"].items())[:6])
        notify(s, f"🔎 Competitor patterns ({rep['date']}): {rep['long_videos']} long videos from "
                  f"{len(rep['channels'])} channels. Median length {ln['median_minutes']} min; titles: numbers "
                  f"{t['with_number']:.0%}, $ {t['with_dollar']:.0%}, questions {t['question']:.0%}. Topics: {top}. "
                  f"Full report: reports/competitors/{rep['date']}.md (patterns only, nothing copied).")


def cmd_verify_facts(args, s):
    """Re-check every launch-list fact on its official page (numbers must still be there)."""
    from .studio.launch_plan import LAUNCH, done, verify_facts

    finished = set(done(_store(s)))
    for v in LAUNCH:
        kept, notes = verify_facts(v)
        state = "done" if v.n in finished else "to do"
        print(f"#{v.n:2} [{state}] {v.topic}: {len(kept)} facts ok" + "".join(f"\n     ⚠ {n}: {f.text[:80]}"
                                                                            for f, n in notes))


def cmd_health(args, s):
    """Health report (buffer, pace, spend, disk, voice, failed services) + current alerts; sent to Telegram."""
    from .studio import health

    store = _store(s)
    alerts = health.alerts(s, store)
    text = ("\n\n".join(alerts) + "\n\n" if alerts else "") + health.report(s, store)
    print(text)
    if not args.no_telegram:
        from .publish.telegram import notify

        notify(s, text)


def cmd_alert(args, s):
    """Send one alert to Telegram (used by systemd OnFailure=). Queued during quiet hours."""
    from .publish.telegram import notify

    notify(s, ("ℹ️ GLIVARAO: " if args.info else "🔴 GLIVARAO: ") + " ".join(args.text)[:3500])


def cmd_queue(args, s):
    from .studio.queue import TopicQueue

    print(TopicQueue(_store(s)).status_text())


def cmd_add_input(args, s):
    """Add your take to a topic from the server (alternative to Telegram)."""
    from .studio.queue import TopicQueue

    q = TopicQueue(_store(s))
    if q.get(args.item_id) is None:
        raise SystemExit(f"unknown topic id {args.item_id}; see: python -m glivarao queue")
    it = q.add_input(args.item_id, args.text)
    print(f"saved your take for \"{it.topic}\"; status: {it.status}")


def cmd_voice_sample(args, s):
    """Narrate a script, add the music bed, and master to -14 LUFS (audio only).

    --provider kokoro (free, default) or google_chirp (paid: needs ALLOW_PAID_APIS=true + GOOGLE_TTS_API_KEY).
    Without approval the paid path only prints the plan and exact cost; it never calls the API."""
    import subprocess
    from dataclasses import replace
    from pathlib import Path

    import soundfile as sf

    from .anim.audio import master_to_lufs, mix
    from .tts.google_chirp import CANDIDATE_VOICES, billable_text
    from .tts.kokoro import KOKORO_SR, KokoroEngine
    from .tts.narrator import paid_choice

    text = Path(args.script).read_text()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.provider == "gemini_tts":
        from .tts.gemini_tts import estimate_usd
        from .tts.narrator import gemini_narrator

        hi = estimate_usd(" ".join(text.split()), s.gemini_tts_price, s.gemini_tts_tokens_per_sec)
        lo = estimate_usd(" ".join(text.split()), 9.0, 25)
        print(f"plan: Gemini TTS {s.gemini_tts_model}, voice {s.gemini_tts_voice}, "
              f"{len(' '.join(text.split())):,} characters -> about ${lo:.3f}-${hi:.3f}")
        if not (s.allow_paid_apis and s.gemini_api_key):
            print("NOT RUN: paid voice needs owner approval (ALLOW_PAID_APIS=true) and GEMINI_API_KEY.")
            return
        runs = [(s.gemini_tts_voice, gemini_narrator(s))]
    elif args.provider == "google_chirp":
        voices = list(CANDIDATE_VOICES) if args.compare else [args.voice or s.google_tts_voice]
        chars = sum(len(x) for x in billable_text(text))
        cost = chars * len(voices) * s.tts_price_per_million / 1e6
        print(f"plan: {len(voices)} voice(s) x {chars:,} characters = {chars * len(voices):,} characters, "
              f"about ${cost:.2f} at ${s.tts_price_per_million:g}/1M (or $0 inside a free monthly allowance)")
        for v in voices:
            print(f"  - {v} ({CANDIDATE_VOICES.get(v, 'custom')})")
        if not (s.allow_paid_apis and s.google_tts_api_key):
            print("NOT RUN: paid voice needs owner approval (ALLOW_PAID_APIS=true) and GOOGLE_TTS_API_KEY.")
            return
        runs = [(v, paid_choice(replace(s, google_tts_voice=v))) for v in voices]
    else:
        v = args.voice or s.kokoro_voice
        runs = [(v, KokoroEngine.get(v))]
    for voice, engine in runs:
        n = engine.narrate(text)
        stem = out / f"voice_sample_{voice}"
        raw = stem.with_suffix(".mix.wav")
        sf.write(raw, mix(n.audio, [(n.duration - 1.6, "chime")], seed=7), KOKORO_SR, subtype="PCM_16")
        rep = master_to_lufs(raw, stem.with_suffix(".wav"))
        raw.unlink()
        for ext, codec in ((".m4a", ["-c:a", "aac", "-b:a", "192k"]), (".mp3", ["-c:a", "libmp3lame", "-b:a", "192k"])):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(stem.with_suffix(".wav")), *codec,
                            str(stem.with_suffix(ext))], check=True)
        words = len(text.replace("*", "").split())
        billed = getattr(engine, "billed_chars", 0) or round(getattr(engine, "spent_usd", 0.0), 4)
        print(f"voice={voice} duration={n.duration:.1f}s pace={words / n.duration * 60:.0f} wpm "
              f"loudness={rep['after']['lufs']} LUFS true_peak={rep['after']['true_peak']} dBTP "
              f"billed={billed}")
        print(f"  files: {stem}.wav / .m4a / .mp3")


def cmd_list(args, s):
    for j in _store(s).list(JobStatus(args.status) if args.status else None, limit=args.limit):
        print(f"{j.id:28s} {j.status.value:20s} {j.format:5s} {j.duration_sec or 0:7.1f}s  {j.topic}")


def cmd_poll(args, s):
    from .publish.telegram import poll_decisions
    from .studio import quiet

    import time as _t

    store = _store(s)
    if not (s.telegram_bot_token and s.telegram_approver_chat_id):
        print("Telegram is not configured yet; nothing to poll")
        return
    # Tolerant by design (runs every 5 minutes): a network or Telegram error never makes the service fail.
    # After a failure the next polls back off (5, 10, 20, ... up to 60 min); one alert after 6 failures in a row.
    state = json.loads(store.kv_get("poll_backoff", '{"fails": 0, "next": 0}'))
    if _t.time() < state["next"]:
        print(f"backing off after {state['fails']} failure(s); next try in {int(state['next'] - _t.time())} s")
        return
    try:
        delivered = quiet.flush(s, store)  # alerts and reviews held during quiet hours
        if delivered:
            print(f"delivered {delivered} queued message(s)")
    except Exception as exc:  # noqa: BLE001  never block approvals
        print(f"could not flush queued messages: {type(exc).__name__}")
    try:
        decisions = poll_decisions(store, s)
    except Exception as exc:  # noqa: BLE001
        fails = state["fails"] + 1
        wait = min(3600, 300 * 2 ** (fails - 1))
        store.kv_set("poll_backoff", json.dumps({"fails": fails, "next": _t.time() + wait}))
        print(f"poll failed ({type(exc).__name__}: {str(exc)[:120]}); retry in {wait // 60} min")
        if fails == 6:
            try:
                from .publish.telegram import notify

                notify(s, f"🔴 GLIVARAO: Telegram polling failed 6 times in a row ({type(exc).__name__}). "
                          "It keeps retrying every hour.")
            except Exception:  # noqa: BLE001
                pass
        return
    if state["fails"]:
        store.kv_set("poll_backoff", json.dumps({"fails": 0, "next": 0}))
    print(decisions or "no new decisions")
    # Approval never triggers an upload. Uploading is a separate, manual, interactive step.


def cmd_decide(args, s):
    store = _store(s)
    job = store.get(args.job_id)
    to = JobStatus.APPROVED if args.approve else JobStatus.REJECTED
    if job.status == JobStatus.RENDERED:  # never sent to Telegram; record that too
        store.transition(job, JobStatus.PENDING_APPROVAL, "manual review (cli)")
    store.transition(job, to, f"cli operator override: {args.reason}")
    print(f"{job.id}: {to.value}")


def cmd_publish(args, s):
    """Manual upload only: requires a human at an interactive terminal to retype the job id."""
    from .pipeline import load_script
    from .publish.telegram import notify
    from .publish.youtube import PublishBlocked, upload

    if not sys.stdin.isatty():
        raise PublishBlocked("publish must be run by a person in an interactive terminal (no cron/automation)")
    store = _store(s)
    job = store.get(args.job_id)
    print(f"About to upload {job.id} as PRIVATE to YouTube: {job.topic}")
    typed = input("Type the job id to confirm: ").strip()
    vid = upload(job, load_script(job), store, s, operator_confirmation=typed)
    notify(s, f"{job.id} uploaded to YouTube as PRIVATE (not published): https://youtu.be/{vid}")
    print(f"uploaded (private): https://youtu.be/{vid} — make it public yourself in YouTube Studio")


def cmd_auth(args, s):
    from .publish.youtube import authorize

    authorize(s)
    print(f"token saved to {s.youtube_token_file}")


def cmd_analytics(args, s):
    from .publish.youtube import fetch_analytics

    for row in fetch_analytics(_store(s), s, days=args.days):
        print(json.dumps(row))


def cmd_events(args, s):
    for e in _store(s).events(args.job_id):
        print(f"{e['at']}  {e['from_status']:>18s} -> {e['to_status']:<18s} {e['detail']}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="glivarao", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    dr = sub.add_parser("doctor", help="production checklist (keys shown as set/missing only)")
    dr.add_argument("--strict", action="store_true", help="exit 1 if the installation is broken")
    dr.add_argument("--live", action="store_true", help="test Telegram, YouTube, Gemini and Claude with tiny calls")
    dr.add_argument("--config", dest="verbose_config", action="store_true", help="also print the redacted config")
    dr.set_defaults(fn=cmd_doctor)
    pr = sub.add_parser("produce", help="LOCKED old v1 command (dry-run tests only, with --legacy)")
    pr.add_argument("--legacy", action="store_true")
    pr.set_defaults(cmd="produce")
    pr.add_argument("--format", choices=["long", "short"], default="short")
    pr.add_argument("--topic")
    pr.add_argument("--minutes", type=float, help="override target length (dry runs default to 2 min)")
    pr.add_argument("--angle")
    pr.add_argument("--tts", choices=["elevenlabs", "google", "espeak", "silent"])
    pr.add_argument("--no-approval", action="store_true", help="do not send to Telegram")
    pr.set_defaults(fn=cmd_produce)
    d = sub.add_parser("daily", help="LOCKED old v1 command (use daily-v2)")
    d.add_argument("--legacy", action="store_true")
    d.set_defaults(cmd="daily")
    d.add_argument("--long-minutes", type=float)
    d.add_argument("--tts", choices=["elevenlabs", "google", "espeak", "silent"])
    d.set_defaults(fn=cmd_daily)
    sm = sub.add_parser("sample", help="render the v2 animated sample (local only)")
    sm.add_argument("--script", default="config/samples/sample_60s.json")
    sm.add_argument("--voice", help="default: KOKORO_VOICE (am_michael)")
    sm.set_defaults(fn=cmd_sample)
    rs = sub.add_parser("research", help="R1: research and rank finance topics (report only)")
    rs.add_argument("--date", help="YYYY-MM-DD (default today)")
    rs.add_argument("--out", default="reports/research")
    rs.set_defaults(fn=cmd_research)
    bt = sub.add_parser("research-backtest", help="historical replay of research for past dates")
    bt.add_argument("--dates", required=True, help="comma-separated YYYY-MM-DD")
    bt.add_argument("--out", default="reports/research/backtest")
    bt.set_defaults(fn=cmd_backtest)
    d2 = sub.add_parser("daily-v2", help="autonomous daily production: 1 long + 2 Shorts (never uploads)")
    d2.add_argument("--date", help="YYYY-MM-DD (default today)")
    d2.add_argument("--no-telegram", action="store_true")
    d2.add_argument("--workers", type=int)
    d2.add_argument("--shorts", type=int, default=None, help="default: 3 a day (up to 6 when the buffer is low)")
    d2.add_argument("--force", action="store_true", help="produce again even if today already completed")
    d2.add_argument("--retries", type=int, default=1, help="whole-run retries before alerting (default 1)")
    d2.set_defaults(fn=cmd_daily_v2)
    pp = sub.add_parser("propose-topics", help="send this week's 5-7 topic ideas to Telegram for you to pick")
    pp.add_argument("--date", help="YYYY-MM-DD (default today)")
    pp.add_argument("--no-telegram", action="store_true")
    pp.set_defaults(fn=cmd_propose)
    pn = sub.add_parser("plan-next", help="pick the next topic automatically and announce it in Telegram")
    pn.add_argument("--date", help="YYYY-MM-DD (default today)")
    pn.add_argument("--no-telegram", action="store_true")
    pn.add_argument("--force", action="store_true", help="plan even if no long video is due tomorrow")
    pn.set_defaults(fn=cmd_plan)
    sub.add_parser("queue", help="show the topic queue").set_defaults(fn=cmd_queue)
    cp = sub.add_parser("competitors", help="competitor research: patterns from similar channels (YouTube API)")
    cp.add_argument("--no-telegram", action="store_true")
    cp.set_defaults(fn=cmd_competitors)
    hl = sub.add_parser("health", help="health report: buffer, pace, spend, disk, voice, failed services")
    hl.add_argument("--no-telegram", action="store_true")
    hl.set_defaults(fn=cmd_health)
    al = sub.add_parser("alert", help="send an alert to Telegram (systemd OnFailure)")
    al.add_argument("--info", action="store_true", help="informational (no red alert icon)")
    al.add_argument("text", nargs="+")
    al.set_defaults(fn=cmd_alert)
    sub.add_parser("verify-facts", help="re-check the launch list's facts on official pages").set_defaults(
        fn=cmd_verify_facts)
    vo = sub.add_parser("voice-of", help="print the exact voice, style and speed a video was made with")
    vo.add_argument("job_id", nargs="?")
    vo.add_argument("--find", help="text in the topic/title, e.g. 'credit report'")
    vo.add_argument("--short", action="store_true")
    vo.add_argument("--long", action="store_true")
    vo.add_argument("--date", help="YYYY-MM-DD (default: today)")
    vo.set_defaults(fn=cmd_voice_of)
    vf = sub.add_parser("voice-lock-from", help="lock exactly the voice a video was made with")
    vf.add_argument("job_id")
    vf.set_defaults(fn=cmd_voice_lock_from)
    pz = sub.add_parser("pause", help="pause ALL production (survives updates); --status to check")
    pz.add_argument("--reason", default="")
    pz.add_argument("--status", action="store_true")
    pz.set_defaults(fn=cmd_pause)
    sub.add_parser("resume", help="resume production (explicit approval only)").set_defaults(fn=cmd_resume)
    sub.add_parser("claude-quota", help="is the Claude writer usable? (tiny real call; Vertex quota status)").set_defaults(
        fn=cmd_claude_quota)
    rm = sub.add_parser("remake", help="make a video again with the current voice and length rules")
    rm.add_argument("job_id")
    rm.add_argument("--no-telegram", action="store_true")
    rm.set_defaults(fn=cmd_remake)
    ll = sub.add_parser("launch-list", help="show the US-only launch list; --send for approval in Telegram")
    ll.add_argument("--send", action="store_true")
    ll.add_argument("--verify", action="store_true", help="re-check every fact on its official page")
    ll.set_defaults(fn=cmd_launch_list)
    ss = sub.add_parser("style-samples", help="doodle style samples for approval; --send to Telegram")
    ss.add_argument("--send", action="store_true")
    ss.add_argument("--out", default="")
    ss.set_defaults(fn=cmd_style_samples)
    sc = sub.add_parser("shorts-check", help="list Shorts in the queue over 59 s; --remake to make them again")
    sc.add_argument("--remake", action="store_true")
    sc.add_argument("--no-telegram", action="store_true")
    sc.set_defaults(fn=cmd_shorts_check)
    va = sub.add_parser("voice-audition", help="send voice samples to Telegram with pick buttons")
    va.add_argument("voices", nargs="*", help="default: Puck Sadachbia Fenrir Achird Charon")
    va.add_argument("--no-telegram", action="store_true")
    va.set_defaults(fn=cmd_voice_audition)
    vp = sub.add_parser("voice-pick", help="lock a voice from the last audition")
    vp.add_argument("voice")
    vp.set_defaults(fn=cmd_voice_pick)
    vl = sub.add_parser("voice-lock", help="show the locked voice, budget and held videos")
    vl.add_argument("--reset", action="store_true", help="accept changed voice settings in .env as the new lock")
    vl.set_defaults(fn=cmd_voice_lock)
    rh = sub.add_parser("retry-held", help="re-render videos held because the voice was unavailable")
    rh.add_argument("--no-telegram", action="store_true")
    rh.set_defaults(fn=cmd_retry_held)
    pk = sub.add_parser("pack", help="send the upload pack of an approved video to Telegram (uploads nothing)")
    pk.add_argument("job_id")
    pk.set_defaults(fn=cmd_pack)
    ai = sub.add_parser("add-input", help="add your own take to a picked topic")
    ai.add_argument("item_id")
    ai.add_argument("text")
    ai.set_defaults(fn=cmd_add_input)
    vs = sub.add_parser("voice-sample", help="narrated + mixed + mastered audio sample (local only)")
    vs.add_argument("--script", default="config/samples/voice_sample_60s.txt")
    vs.add_argument("--voice", help="voice name (default: KOKORO_VOICE or GOOGLE_TTS_VOICE)")
    vs.add_argument("--provider", choices=["kokoro", "gemini_tts", "google_chirp"], default="kokoro")
    vs.add_argument("--compare", action="store_true", help="google_chirp: render every candidate voice")
    vs.add_argument("--out", default="output/voice_sample")
    vs.set_defaults(fn=cmd_voice_sample)
    ls = sub.add_parser("list")
    ls.add_argument("--status", choices=[x.value for x in JobStatus])
    ls.add_argument("--limit", type=int, default=30)
    ls.set_defaults(fn=cmd_list)
    po = sub.add_parser("poll-approvals")
    po.set_defaults(fn=cmd_poll)
    de = sub.add_parser("decide")
    de.add_argument("job_id")
    g = de.add_mutually_exclusive_group(required=True)
    g.add_argument("--approve", action="store_true")
    g.add_argument("--reject", action="store_true")
    de.add_argument("--reason", default="")
    de.set_defaults(fn=cmd_decide)
    pu = sub.add_parser("publish")
    pu.add_argument("job_id")
    pu.set_defaults(fn=cmd_publish)
    sub.add_parser("youtube-auth").set_defaults(fn=cmd_auth)
    an = sub.add_parser("analytics")
    an.add_argument("--days", type=int, default=28)
    an.set_defaults(fn=cmd_analytics)
    ev = sub.add_parser("events")
    ev.add_argument("job_id")
    ev.set_defaults(fn=cmd_events)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        force=True)
    from .studio.pause import Paused

    try:
        args.fn(args, get_settings())
    except Paused as exc:  # a pause is not an error: timers exit cleanly and never crash-loop
        print(exc)
        return
    except Exception as exc:  # concise operator-facing errors
        if args.verbose:
            raise
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
