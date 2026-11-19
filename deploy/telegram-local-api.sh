#!/usr/bin/env bash
# Local Telegram Bot API server (Telegram's official open-source server, github.com/tdlib/telegram-bot-api).
# Lets the GLIVARAO bot send files up to 2,000 MB (the normal cloud Bot API stops at 50 MB), so approved long
# videos arrive in Telegram in full quality.
#
#   sudo bash /opt/glivarao/app/deploy/telegram-local-api.sh
#
# Safe by design: listens on 127.0.0.1 only (no open ports, no domain, no public links); runs as the 'glivarao'
# user; api_id/api_hash are typed at hidden prompts and stored in a root-only file, never on the command line.
# Needs api_id + api_hash (free): https://my.telegram.org -> API development tools.
# Build takes about 20-40 minutes on 6 vCPU. Safe to re-run.
set -euo pipefail
APP=/opt/glivarao/app
SRC=/opt/telegram-bot-api-src
DATA=/opt/glivarao/telegram-bot-api
SECRETS=/etc/telegram-bot-api.env
PORT=8081

echo "==> build dependencies"
apt-get update -q
apt-get install -y -q make git zlib1g-dev libssl-dev gperf cmake g++

echo "==> source (official repository)"
if [ ! -d "$SRC/.git" ]; then
  git clone --recursive https://github.com/tdlib/telegram-bot-api.git "$SRC"
else
  git -C "$SRC" pull -q && git -C "$SRC" submodule update --init --recursive
fi

echo "==> build (this takes a while; it is fine to leave Termius open in the background)"
mkdir -p "$SRC/build"
cd "$SRC/build"
cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX:PATH=/usr/local .. > /dev/null
MEM_JOBS=$(awk '/MemAvailable/ {print int($2 / 1048576 / 2.5)}' /proc/meminfo)  # ~2.5 GB per compile job
JOBS=$(( MEM_JOBS < $(nproc) ? MEM_JOBS : $(nproc) )); [ "$JOBS" -lt 1 ] && JOBS=1
cmake --build . --target install -j "$JOBS"
/usr/local/bin/telegram-bot-api --version || true

echo "==> api_id / api_hash (from https://my.telegram.org -> API development tools)"
if [ ! -s "$SECRETS" ]; then
  read -r -p "api_id (a number): " API_ID
  read -r -s -p "api_hash (hidden): " API_HASH; echo
  [[ "$API_ID" =~ ^[0-9]+$ && -n "$API_HASH" ]] || { echo "invalid api_id/api_hash"; exit 1; }
  umask 077
  printf 'TELEGRAM_API_ID=%s\nTELEGRAM_API_HASH=%s\n' "$API_ID" "$API_HASH" > "$SECRETS"
fi
chmod 600 "$SECRETS"

echo "==> service"
mkdir -p "$DATA/data" "$DATA/tmp"
chown -R glivarao:glivarao "$DATA"
chmod 750 "$DATA"
cat > /etc/systemd/system/telegram-bot-api.service <<EOF
[Unit]
Description=Local Telegram Bot API server for GLIVARAO (127.0.0.1:${PORT} only; files up to 2000 MB)
After=network-online.target
Wants=network-online.target

[Service]
User=glivarao
EnvironmentFile=${SECRETS}
ExecStart=/usr/local/bin/telegram-bot-api --local --http-ip-address=127.0.0.1 --http-port=${PORT} --dir=${DATA}/data --temp-dir=${DATA}/tmp
Restart=on-failure
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now telegram-bot-api
sleep 3
systemctl is-active telegram-bot-api

echo "==> move the bot from Telegram's cloud server to this local server"
TOKEN=$(grep '^TELEGRAM_BOT_TOKEN=' "$APP/.env" | cut -d= -f2- | tr -d ' ')
[ -n "$TOKEN" ] || { echo "TELEGRAM_BOT_TOKEN is not set in $APP/.env (run deploy/set-key.sh first)"; exit 1; }
if ! grep -q '^TELEGRAM_API_BASE=http://127.0.0.1' "$APP/.env"; then
  # logOut on the cloud server once (required by Telegram before using a local server)
  curl -s "https://api.telegram.org/bot${TOKEN}/logOut" | grep -q '"ok":true' && echo "   logged out of the cloud Bot API" \
    || echo "   cloud logOut not confirmed (fine if it was already done)"
  bash "$APP/deploy/set-key.sh" TELEGRAM_API_BASE "http://127.0.0.1:${PORT}"
  bash "$APP/deploy/set-key.sh" TELEGRAM_MAX_UPLOAD_MB 1900
fi
unset TOKEN

echo "==> check"
sudo -u glivarao bash -c "cd $APP && .venv/bin/python -c \"
from glivarao.config import get_settings
from glivarao.publish.telegram import _client
print('bot:', _client(get_settings(), None).call('getMe')['username'], 'via', get_settings().telegram_api_base)\""
echo "Done. Approved videos (up to ~1.9 GB) now arrive in Telegram in full quality."
echo "To undo: set TELEGRAM_API_BASE=https://api.telegram.org and TELEGRAM_MAX_UPLOAD_MB=50 with deploy/set-key.sh,"
echo "then: systemctl disable --now telegram-bot-api  (Telegram lets the bot return to the cloud 10 minutes later)."
