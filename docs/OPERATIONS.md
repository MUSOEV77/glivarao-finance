# Operations runbook

## Publishing policy (enforced in code)

- **Nothing is ever uploaded, published or scheduled automatically.** This holds even after you approve a
  video in Telegram.
- An approval only marks the job `approved`.
- Uploading is a separate manual command, `python -m glivarao publish <job_id>`. It:
  - refuses to run without an interactive terminal, so it cannot run from cron or scripts;
  - asks you to retype the job ID;
  - requires `YOUTUBE_PUBLISH_ENABLED=true`;
  - always uploads as **private**, with no `publishAt`, so YouTube cannot show or schedule the video.
- Making a video public is done by you in YouTube Studio.

## Daily flow

1. `python -m glivarao daily` renders 1 long video and 2 Shorts. For each one, Telegram receives:
   - the thumbnail, with job, title, topic and duration
   - the full title, description and tags
   - a preview clip (first 60 s, 480p)
   - the **finished MP4**: the master if it is under `TELEGRAM_MAX_UPLOAD_MB`, otherwise a full-length
     720p review copy compressed to fit, plus the master's path on the server
   - captions (SRT)
   - the automated check report and fact-check list, followed by the **✅ Approve / ❌ Reject** buttons
2. Press Approve or Reject. Only the chat set in `TELEGRAM_APPROVER_CHAT_ID` is accepted. Presses from
   anyone else are ignored and logged.
3. `python -m glivarao poll-approvals` records the decisions. It never uploads.
4. If you want a video on YouTube, upload it by hand (private), then publish it yourself in YouTube Studio.
5. `python -m glivarao analytics` pulls per-video metrics for the last 28 days.

## Useful commands

```bash
python -m glivarao doctor                       # what's configured / missing
python -m glivarao list --status pending_approval
python -m glivarao events <job_id>              # audit trail
python -m glivarao decide <job_id> --approve --reason "reviewed locally"   # record a decision without Telegram
python -m glivarao publish <job_id>             # MANUAL, interactive, private-only upload
```

## Optional production schedule (renders and Telegram only, never uploads)

These lines are not installed anywhere. Add them yourself only if you want daily rendering.

```cron
CRON_TZ=America/New_York
17 4 * * *     cd /opt/glivarao && .venv/bin/python -m glivarao daily >> logs/daily.log 2>&1
*/5 6-23 * * * cd /opt/glivarao && .venv/bin/python -m glivarao poll-approvals >> logs/poll.log 2>&1
43 9 * * *     cd /opt/glivarao && .venv/bin/python -m glivarao analytics >> logs/analytics.log 2>&1
```

There is deliberately no cron line for `publish`. It would refuse to run anyway, because it requires an
interactive terminal.

## Output layout

```
output/<job_id>/
  script.json  compliance.txt  metadata.json
  audio/scene_###.wav  narration.wav
  captions.srt  captions.ass  video.mp4  preview.mp4  review_copy.mp4 (if needed)  thumbnail.jpg
data/glivarao.sqlite3     # jobs, events (audit), analytics, telegram offset
```
