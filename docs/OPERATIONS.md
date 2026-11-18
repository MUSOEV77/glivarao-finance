# Operations runbook

## Daily flow
1. `python -m glivarao daily` produces 1 long video and 2 Shorts. Each one is sent to Telegram as a card
   with the thumbnail, title, automated check results, fact-check items and a preview clip.
2. The approver presses **✅ Approve** or **❌ Reject**. Only the chat set in `TELEGRAM_APPROVER_CHAT_ID`
   is accepted. Presses from anyone else are ignored and logged.
3. `python -m glivarao poll-approvals` records the decisions. With `--auto-publish`, approved jobs are
   uploaded right away, as private unless configured otherwise.
4. `python -m glivarao analytics` pulls per-video metrics for the last 28 days.

## Useful commands
```bash
python -m glivarao doctor                       # what's configured / missing
python -m glivarao list --status pending_approval
python -m glivarao events <job_id>              # audit trail
python -m glivarao decide <job_id> --approve --reason "reviewed locally"   # operator override
python -m glivarao publish <job_id> --privacy unlisted
```

## Scheduling (example crontab, America/New_York)
```cron
CRON_TZ=America/New_York
17 4 * * *   cd /srv/glivarao && .venv/bin/python -m glivarao daily >> logs/daily.log 2>&1
*/5 6-23 * * * cd /srv/glivarao && .venv/bin/python -m glivarao poll-approvals --auto-publish >> logs/poll.log 2>&1
43 9 * * *   cd /srv/glivarao && .venv/bin/python -m glivarao analytics >> logs/analytics.log 2>&1
```
Production starts early in the day, so there is time to review before an afternoon publish. Nothing
publishes unless a human approves it **and** `YOUTUBE_PUBLISH_ENABLED=true`.

## Output layout
```
output/<job_id>/
  script.json  compliance.txt  metadata.json
  audio/scene_###.wav  narration.wav
  captions.srt  captions.ass  video.mp4  preview.mp4  thumbnail.jpg
data/glivarao.sqlite3     # jobs, events (audit), analytics, telegram offset
```
