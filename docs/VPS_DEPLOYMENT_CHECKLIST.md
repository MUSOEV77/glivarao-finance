# Contabo Cloud VPS 6: deployment checklist

**Target:**
- 6 vCPU and 12 GB RAM.
- Storage is listed as 100 GB NVMe or 200 GB SSD depending on the page; either is enough.
- Ubuntu 24.04.

**Expected load:**
- The installer picks the number of render workers automatically: min(6 CPUs, free RAM ÷ 1 GB) = 6.
- Estimated peak RAM is about 6–7 GB.
- A daily set should take under about 1 hour. This is an estimate: benchmark it on the server.
- About 0.5 GB of output a day, pruned after 30 days.

## A. Before you start (on your phone or PC)

- [ ] Order Cloud VPS 6 with Ubuntu 24.04 and an SSH key (don't use a password). Note the server's IP.
- [ ] Create the Telegram bot with @BotFather and keep the token private. Send the bot one message.
- [ ] Get the project code onto the server. GitHub push is blocked for Claude right now, so use either:
  - the `glivarao-finance-mvp.bundle` file: `scp glivarao-finance-mvp.bundle root@SERVER:/root/`; or
  - GitHub, once access is fixed and the branch is pushed.

## B. Server basics (SSH as root)

```bash
apt-get update && apt-get -y upgrade
timedatectl set-timezone America/New_York
ufw allow OpenSSH && ufw --force enable            # no inbound ports are needed
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab     # safety net only
```

## C. Install

```bash
git clone -b claude/glivarao-finance-mvp-n153rg /root/glivarao-finance-mvp.bundle /root/glivarao-src
cd /root/glivarao-src && sudo bash deploy/install.sh
```

**What the installer does:**
- installs system packages;
- creates the `glivarao` service user;
- sets up the Python venv and the Kokoro voice model (~350 MB from GitHub);
- creates `.env` with permissions 600 and `secrets/` with 700;
- installs the systemd timers;
- runs a self-test.

## D. Configure `/opt/glivarao/app/.env`

Edit it with `sudo -u glivarao nano /opt/glivarao/app/.env`. Never paste keys into chats or Git.

| Variable | Needed for | Required now? |
|---|---|---|
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_APPROVER_CHAT_ID` | Review package and approve/reject | **Yes** |
| `ANTHROPIC_API_KEY` + `ALLOW_PAID_APIS=true` | **15–18 min long scripts** (Claude writer; capped by `CLAUDE_MONTHLY_BUDGET_USD=30`) | Yes, for full-length videos. Without it, the long video is ~3.6 min |
| `GEMINI_API_KEY` + `TTS_PROVIDER=gemini_tts` | Premium Charon voice (capped at `TTS_MONTHLY_BUDGET_USD=20`) | Optional (Kokoro is used otherwise) |
| `YOUTUBE_CLIENT_SECRETS_FILE` (file in `secrets/`) | Manual private upload and analytics only | Optional |
| `YOUTUBE_PUBLISH_ENABLED` | Leave **false** | — |

## E. Verify (about 30 min)

```bash
sudo -u glivarao /opt/glivarao/app/.venv/bin/python -m glivarao doctor     # secrets show as "set", never their values
cd /opt/glivarao/app && sudo -u glivarao .venv/bin/python -m glivarao -v daily-v2   # first real run
systemctl list-timers 'glivarao-*'          # daily 04:17 ET, poll every 5 min, backup 03:40
tail -f /opt/glivarao/app/logs/daily.log
```

- [ ] Telegram receives the thumbnail, metadata, preview, video, captions, research card and fact sheet for
  **1 long video and 2 Shorts**.
- [ ] Approve and reject buttons work. Nothing appears on YouTube.
- [ ] Record the render time and peak RAM (`free -h` during the run). If the run takes over 3 h or swap is in heavy
  use, set `RENDER_WORKERS=4`.
- [ ] `sudo bash /opt/glivarao/app/deploy/backup.sh` creates `backups/glivarao-DATE.tar.gz`.

## F. Outbound hosts the server must reach

| Purpose | Hosts |
|---|---|
| Telegram | `api.telegram.org` |
| Research | `api.stackexchange.com`, `www.consumerfinance.gov`, `wikimedia.org`, `api.stlouisfed.org`, `www.ftc.gov`, `www.canada.ca` |
| Claude | `api.anthropic.com` |
| Gemini (optional) | `generativelanguage.googleapis.com` |
| YouTube (optional, manual) | `www.googleapis.com` |
| Install only | `github.com`, `pypi.org` |

## G. Daily operation from Android

**What runs automatically:**
- Telegram: review, approve or reject, and failure alerts.
- Approval never uploads.

**Manual upload, when you want it:** SSH (for example with Termius), then:

```bash
sudo -u glivarao /opt/glivarao/app/.venv/bin/python -m glivarao publish JOB_ID
```

This needs an interactive terminal and you retyping the job ID. Uploads are always private.

**Rollback tags:**
- `backup/pre-production-hardening-2026-11-18`
- `backup/pre-integration-2026-11-18`
