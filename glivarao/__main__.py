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
import logging
import sys

from .config import get_settings
from .models import JobStatus
from .storage import JobStore


def _store(settings):
    return JobStore(settings.db_path)


def cmd_doctor(args, s):
    import shutil

    print(f"mode: {s.mode} ({'DRY RUN — no network calls, placeholder voice' if s.dry_run else 'PRODUCTION'})")
    print(f"ffmpeg: {'ok' if shutil.which('ffmpeg') else 'MISSING'}   espeak-ng: "
          f"{'ok' if shutil.which('espeak-ng') else 'missing (optional, dev only)'}")
    for name, (ok, hint) in s.readiness().items():
        print(f"  [{'x' if ok else ' '}] {name:32s} {'' if ok else '-> ' + hint}")
    print("\nconfig (secrets redacted):")
    print(json.dumps(s.redacted(), indent=2))


def cmd_produce(args, s):
    from .pipeline import produce

    res = produce(s, _store(s), args.format, topic=args.topic, minutes=args.minutes, angle=args.angle or "",
                  tts_provider=args.tts, send_for_approval=not args.no_approval)
    _print_result(res)


def cmd_daily(args, s):
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

    from datetime import timedelta

    from .daily_v2 import pace_check

    day = date.fromisoformat(args.date) if args.date else None
    store = _store(s)
    tomorrow = (day or date.today()) + timedelta(days=1)
    ok, why = pace_check(store, tomorrow, s)
    if not ok and not args.force:
        print(f"no long video due tomorrow ({why}); tomorrow is a Shorts day")
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

    decisions = poll_decisions(_store(s), s)
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
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    pr = sub.add_parser("produce")
    pr.add_argument("--format", choices=["long", "short"], default="short")
    pr.add_argument("--topic")
    pr.add_argument("--minutes", type=float, help="override target length (dry runs default to 2 min)")
    pr.add_argument("--angle")
    pr.add_argument("--tts", choices=["elevenlabs", "google", "espeak", "silent"])
    pr.add_argument("--no-approval", action="store_true", help="do not send to Telegram")
    pr.set_defaults(fn=cmd_produce)
    d = sub.add_parser("daily")
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
    d2.add_argument("--shorts", type=int, default=2)
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
    try:
        args.fn(args, get_settings())
    except Exception as exc:  # concise operator-facing errors
        if args.verbose:
            raise
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
