# VPS deployment (Ubuntu 22.04 / 24.04)

**Recommended server:** 4 vCPU, 8 GB RAM, 80 GB SSD.

Measured in this project's test container (4 vCPU):
- The daily run (a short "long" video plus 2 Shorts with the free writer) takes the times recorded in
  `docs/FINAL_REPORT.md`.
- Peak memory was about 1.1 GB for a 16-minute v1 render.

The system **never uploads, publishes or schedules anything on YouTube**. Uploading is a manual,
interactive, private-only command.

## 1. Install (one command)

```bash
sudo apt-get install -y git
git clone https://github.com/MUSOEV77/glivarao-finance.git /tmp/glivarao-src
cd /tmp/glivarao-src && git checkout claude/glivarao-finance-mvp-n153rg
sudo bash deploy/install.sh
```

The installer is idempotent and can be re-run safely. It:
- installs the system packages (Python, ffmpeg, sqlite3, fonts);
- creates the unprivileged `glivarao` user;
- copies the app to `/opt/glivarao/app`;
- builds the virtual environment and installs dependencies and the spaCy English model;
- downloads the Kokoro voice model (Apache-2.0, about 350 MB);
- creates `.env` (mode 600);
- runs `doctor`;
- enables three systemd timers:

| Timer | When | What |
|---|---|---|
| `glivarao-daily.timer` | 04:17 America/New_York | `daily-v2`: research → topic → 1 long + 2 Shorts → Telegram review |
| `glivarao-poll.timer` | every 5 min | records Approve/Reject presses (never uploads) |
| `glivarao-backup.timer` | 03:40 | SQLite backup (kept 30 days); prunes renders older than 30 days |

Logs are written to `/opt/glivarao/app/logs/` and rotated weekly.

## 2. Configure `/opt/glivarao/app/.env`

```bash
sudo -u glivarao nano /opt/glivarao/app/.env
```

| Setting | Value | Cost |
|---|---|---|
| `GLIVARAO_MODE` | `production` (the installer sets it) | — |
| `TTS_PROVIDER` / `KOKORO_VOICE` | `kokoro` / `am_michael` (the installer sets it) | free, local |
| `TELEGRAM_BOT_TOKEN` | from @BotFather → /newbot | free |
| `TELEGRAM_APPROVER_CHAT_ID` | message your bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `message.chat.id` | free |
| `TELEGRAM_API_BASE` / `TELEGRAM_MAX_UPLOAD_MB` | keep the defaults. The cloud Bot API is limited to 50 MB, so long videos arrive as a full-length 720p review copy | free |
| `ALLOW_PAID_APIS` | keep `false` unless you approve Claude API costs for full 15–18 minute original scripts | paid if `true` |
| `ANTHROPIC_API_KEY` | only if `ALLOW_PAID_APIS=true` | paid |
| `FRED_API_KEY` | optional, free (household-finance data series) | free |
| YouTube | `secrets/client_secret.json` plus `python -m glivarao youtube-auth`, only if you ever want manual private uploads or analytics | free (quota) |

## 3. Verify

```bash
cd /opt/glivarao/app
sudo -u glivarao .venv/bin/python -m pytest -q                       # full test suite
sudo -u glivarao .venv/bin/python -m glivarao doctor
sudo -u glivarao .venv/bin/python -m glivarao research                # ranked topic report
sudo systemctl start glivarao-daily.service && tail -f logs/daily.log # one full production run now
systemctl list-timers 'glivarao-*'
```

## 4. Daily operation

1. At about 04:17 ET the server researches topics, picks one, and produces 1 long video and 2 Shorts.
2. Telegram receives, for each video:
   - the thumbnail;
   - the full title, description and tags;
   - a preview;
   - the finished MP4;
   - the captions;
   - the "why this topic" research card;
   - the fact sheet;
   - the compliance report;
   - **Approve / Reject** buttons.
3. Approval only records your decision. To put an approved video on YouTube, upload it yourself:
   `sudo -u glivarao /opt/glivarao/app/.venv/bin/python -m glivarao publish <job_id>`. This is interactive
   and always private. You publish it in YouTube Studio.

### Reliability (what happens automatically)

- **One run per day, never overlapping.**
  - A file lock (`data/daily.lock`) prevents two runs at once.
  - A day that completed is skipped. Run with `daily-v2 --force` to produce it again.
- **Retries.**
  - A failed run is retried once, after 2 minutes.
  - A failed render is retried once with 1 worker, since memory pressure is the usual cause.
- **Alerts.** You get a Telegram alert:
  - if the run still fails after the retry;
  - if any video failed, or was rejected by the compliance check.
- **Disk.** The run refuses to start with less than 1.5 GB free, and says so.
- **Memory.**
  - Render workers are capped by free RAM (about 1 GB each). Override with `RENDER_WORKERS`.
  - The voice model is released before frames render.
  - Intermediate WAVs are deleted.
- **Logs.**
  - Timestamped logs go to `logs/daily.log` and `logs/poll.log`, rotated weekly by logrotate.
  - `journalctl -u glivarao-daily` has the exit status.
- **Backups** run daily at 03:40 into `backups/glivarao-YYYY-MM-DD.tar.gz`, kept for 30 days.
  - They contain the job database, which is integrity-checked, plus the spend ledgers.
  - They never contain `.env` or `secrets/`.
  - Restore: `sudo bash deploy/restore.sh backups/glivarao-YYYY-MM-DD.tar.gz`. It stops the timers, keeps the
    current files as `*.before-restore`, then restarts the timers.
- **Spending caps (enforced in code):**
  - Claude scripts: `CLAUDE_MONTHLY_BUDGET_USD` (default $30).
  - Gemini voice: `TTS_MONTHLY_BUDGET_USD` (default $20).
  - With the VPS (about $5), worst case is about $55 a month, well under $100. Paid APIs are only used when
    `ALLOW_PAID_APIS=true`.

## 5. Updating

```bash
cd /tmp/glivarao-src && git pull && sudo bash deploy/install.sh   # re-runs safely; keeps .env and data
```

## Notes

- Network access needed:
  - GitHub (model download, one time) and PyPI;
  - research sources: api.stackexchange.com, www.consumerfinance.gov, wikimedia.org;
  - api.telegram.org.
  - No inbound ports are needed (Telegram uses polling): `sudo ufw allow OpenSSH && sudo ufw enable`.
- To roll back to the code before today's integration: `git checkout backup/pre-integration-2026-11-18`.
  The code before the production hardening and editorial design is at
  `backup/pre-production-hardening-2026-11-18`. The previous cartoon look is still available with
  `GLIVARAO_THEME=cartoon`.
