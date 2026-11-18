# VPS deployment (Ubuntu 24.04 LTS)

Tested locally with Python 3.13 and ffmpeg 6 on a 4 vCPU Linux container. Recommended VPS: **4 vCPU,
8 GB RAM, 80 GB SSD**. A full 16.5-minute render peaks at about 1 GB RAM (see `docs/TEST_REPORT.md`), so
2 GB is the bare minimum.

Run every command as a sudo-capable user unless the step says otherwise.

## 1. System packages

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip ffmpeg git sqlite3 fonts-dejavu-core
# optional, development placeholder voice only (never publish with it):
sudo apt-get install -y espeak-ng
ffmpeg -hide_banner -filters | grep -E " ass | subtitles "   # must list libass filters
```

## 2. Service user and code

```bash
sudo adduser --system --group --home /opt/glivarao glivarao
sudo -u glivarao git clone https://github.com/MUSOEV77/glivarao-finance.git /opt/glivarao/app
cd /opt/glivarao/app
sudo -u glivarao git checkout claude/glivarao-finance-mvp-n153rg
sudo -u glivarao python3 -m venv /opt/glivarao/.venv
sudo -u glivarao /opt/glivarao/.venv/bin/pip install -r requirements.txt
```

## 2b. Voice model (Kokoro-82M, Apache-2.0, about 350 MB, not stored in git)

```bash
cd /opt/glivarao/app
sudo -u glivarao mkdir -p models/kokoro
B=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
sudo -u glivarao curl -fL -o models/kokoro/kokoro-v1.0.onnx $B/kokoro-v1.0.onnx
sudo -u glivarao curl -fL -o models/kokoro/voices-v1.0.bin  $B/voices-v1.0.bin
sudo -u glivarao /opt/glivarao/.venv/bin/pip install \
  https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
# render the 60-second v2 sample (local only, nothing is sent anywhere):
sudo -u glivarao /opt/glivarao/.venv/bin/python -m glivarao sample
```

Set `TTS_PROVIDER=kokoro` and `KOKORO_VOICE=am_michael` in `.env`. espeak and silent narration are
refused when `GLIVARAO_MODE=production`.

## 3. Secrets (never commit them)

```bash
sudo -u glivarao cp .env.example .env
sudo -u glivarao chmod 600 .env
sudo -u glivarao nano .env          # fill in values from docs/CREDENTIALS.md
sudo -u glivarao mkdir -m 700 -p secrets data output logs
# copy the Google OAuth Desktop client JSON from your own computer:
#   scp client_secret.json you@vps:/tmp/ && sudo mv /tmp/client_secret.json /opt/glivarao/app/secrets/
sudo chown glivarao:glivarao secrets/client_secret.json && sudo chmod 600 secrets/client_secret.json
```

Keep `GLIVARAO_MODE=dry-run` and `YOUTUBE_PUBLISH_ENABLED=false` for the first runs.

## 4. Smoke test

```bash
cd /opt/glivarao/app
sudo -u glivarao /opt/glivarao/.venv/bin/python -m pytest -q
sudo -u glivarao /opt/glivarao/.venv/bin/python -m glivarao doctor
sudo -u glivarao /opt/glivarao/.venv/bin/python -m glivarao produce --format short --no-approval
```

## 5. Production rendering with Telegram review

Set `GLIVARAO_MODE=production`, `TTS_PROVIDER=elevenlabs` (or `google`), and the Telegram variables. Then:

```bash
sudo -u glivarao /opt/glivarao/.venv/bin/python -m glivarao produce --format short
# check Telegram: thumbnail, title/description, preview, finished MP4, captions, buttons
sudo -u glivarao /opt/glivarao/.venv/bin/python -m glivarao poll-approvals
```

### Optional: send the full-quality master MP4 to Telegram

The cloud Bot API caps uploads at 50 MB. A 17-minute master is larger, so by default Telegram gets a
full-length compressed 720p review copy. To receive the master itself (up to 2000 MB), run a local Bot
API server:

1. Get `api_id` and `api_hash` at https://my.telegram.org.
2. Build and run `telegram-bot-api` from https://github.com/tdlib/telegram-bot-api, listening on 127.0.0.1:8081.
3. Call `logOut` once on the cloud API for your bot, as that project's README describes.
4. Set `TELEGRAM_API_BASE=http://127.0.0.1:8081` and `TELEGRAM_MAX_UPLOAD_MB=2000` in `.env`.

## 6. YouTube authorization (one time, only when you decide to)

```bash
# On the VPS (prints a URL; open it on your computer via an SSH tunnel to the printed port):
sudo -u glivarao /opt/glivarao/.venv/bin/python -m glivarao youtube-auth
```

Uploading stays manual: `python -m glivarao publish <job_id>` in an interactive SSH session. Uploads are
always private.

## 7. Optional daily rendering schedule

`sudo -u glivarao crontab -e` and paste the block from `docs/OPERATIONS.md`. That schedule only renders
and sends to Telegram. Nothing in it uploads.

## 8. Maintenance

```bash
# back up the job database daily
sqlite3 /opt/glivarao/app/data/glivarao.sqlite3 ".backup '/opt/glivarao/backup-$(date +%F).sqlite3'"
# prune rendered files older than 30 days
find /opt/glivarao/app/output -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec rm -rf {} +
# update the code
cd /opt/glivarao/app && sudo -u glivarao git pull && sudo -u glivarao /opt/glivarao/.venv/bin/pip install -r requirements.txt
```

Firewall: no inbound ports are needed (Telegram uses polling). `sudo ufw allow OpenSSH && sudo ufw enable`.
