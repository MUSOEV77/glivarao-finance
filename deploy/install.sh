#!/usr/bin/env bash
# GLIVARAO Finance VPS installer (Ubuntu 22.04/24.04). Run as root from the repository checkout:
#   sudo bash deploy/install.sh
# Idempotent. Installs into /opt/glivarao, runs as the unprivileged 'glivarao' user. Never uploads anything.
set -euo pipefail
APP_DIR=/opt/glivarao/app
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SKIP_SYSTEMD="${SKIP_SYSTEMD:-0}"

echo "==> system packages"
apt-get update -q
apt-get install -y -q python3 python3-venv python3-pip ffmpeg git sqlite3 curl fonts-dejavu-core util-linux
apt-get install -y -q tesseract-ocr || echo "   tesseract-ocr not installed: competitor thumbnail text is skipped"

echo "==> service user"
id glivarao >/dev/null 2>&1 || adduser --system --group --home /opt/glivarao glivarao

echo "==> application files"
mkdir -p "$APP_DIR"
if [ "$SRC_DIR" != "$APP_DIR" ]; then
  # code only: never copy local environments, renders, data, models or secrets; never overwrite .env/data
  tar -C "$SRC_DIR" --exclude=.git --exclude=.venv --exclude=output --exclude=data --exclude=downloads \
      --exclude=reports --exclude=models --exclude=secrets --exclude=.env --exclude='*.bundle' \
      --exclude=__pycache__ -cf - . | tar -C "$APP_DIR" -xf -
fi
cd "$APP_DIR"
mkdir -p secrets data output logs reports models/kokoro
chown -R glivarao:glivarao /opt/glivarao
chmod 700 secrets
find secrets -type f -exec chmod 600 {} + 2>/dev/null || true   # keys: owner-only
[ -f .env ] && chmod 600 .env
# record exactly which version is installed (deploy/update.sh compares against this, not against git pull)
if git -C "$SRC_DIR" rev-parse HEAD >/dev/null 2>&1; then
  git -C "$SRC_DIR" rev-parse HEAD > "$APP_DIR/.deployed_commit"
  chown glivarao:glivarao "$APP_DIR/.deployed_commit"
fi

echo "==> python environment"
sudo -u glivarao python3 -m venv .venv
sudo -u glivarao .venv/bin/pip install -q --upgrade pip setuptools wheel
sudo -u glivarao .venv/bin/pip install -q -r requirements.txt
sudo -u glivarao .venv/bin/pip install -q \
  https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

echo "==> voice-note transcription (optional, local and free; model downloads on first use)"
sudo -u glivarao .venv/bin/pip install -q faster-whisper || echo "   faster-whisper not installed: send your input as text"
sudo -u glivarao .venv/bin/pip install -q pytesseract || true

echo "==> voice model (Kokoro-82M, Apache-2.0, ~350 MB)"
B=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
[ -f models/kokoro/kokoro-v1.0.onnx ] || sudo -u glivarao curl -fsSL -o models/kokoro/kokoro-v1.0.onnx "$B/kokoro-v1.0.onnx"
[ -f models/kokoro/voices-v1.0.bin ] || sudo -u glivarao curl -fsSL -o models/kokoro/voices-v1.0.bin "$B/voices-v1.0.bin"

echo "==> configuration"
if [ ! -f .env ]; then
  sudo -u glivarao cp .env.example .env
  sed -i 's/^GLIVARAO_MODE=.*/GLIVARAO_MODE=production   /; s/^TTS_PROVIDER=.*/TTS_PROVIDER=gemini_tts/' .env
  chmod 600 .env
  echo "   created .env - fill in TELEGRAM_BOT_TOKEN and TELEGRAM_APPROVER_CHAT_ID"
fi

echo "==> self-test"
sudo -u glivarao .venv/bin/python -m glivarao doctor | head -20

if [ "$SKIP_SYSTEMD" != "1" ]; then
  echo "==> systemd timers"
  cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
  cp deploy/logrotate-glivarao /etc/logrotate.d/glivarao
  systemctl daemon-reload
  systemctl disable --now glivarao-propose.timer 2>/dev/null || true   # weekly ideas are only for TOPIC_MODE=queue
  # always on: Telegram polling, health report, backups
  systemctl enable --now glivarao-poll.timer glivarao-backup.timer glivarao-health.timer
  if [ -f "$APP_DIR/data/PAUSED" ]; then
    # production is paused by the owner: keep production timers OFF until `python -m glivarao resume`
    systemctl disable --now glivarao-daily.timer glivarao-plan.timer glivarao-voice-retry.timer \
      glivarao-competitors.timer 2>/dev/null || true
    echo "   production is PAUSED (data/PAUSED): production timers left off"
  else
    systemctl enable --now glivarao-daily.timer glivarao-plan.timer glivarao-competitors.timer \
      glivarao-voice-retry.timer
  fi
  systemctl list-timers 'glivarao-*' --no-pager
fi
echo "Done. Installed $(cat "$APP_DIR/.deployed_commit" 2>/dev/null | cut -c1-8). Nothing is ever uploaded automatically."
