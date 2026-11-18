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
    res = render_animated(script, out, s, voice=args.voice)
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
    sm.add_argument("--voice", default="am_michael")
    sm.set_defaults(fn=cmd_sample)
    rs = sub.add_parser("research", help="R1: research and rank finance topics (report only)")
    rs.add_argument("--date", help="YYYY-MM-DD (default today)")
    rs.add_argument("--out", default="reports/research")
    rs.set_defaults(fn=cmd_research)
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
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
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
