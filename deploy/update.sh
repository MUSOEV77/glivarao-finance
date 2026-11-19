#!/usr/bin/env bash
# Safe update with automatic rollback. Run on the VPS as root:
#   sudo bash /root/glivarao-src/deploy/update.sh            # install the newest version
#   sudo bash /root/glivarao-src/deploy/update.sh --force    # reinstall even if the version is unchanged
# 1. fetches the newest code into /root/glivarao-src (any local edits there are discarded; it's a mirror)
# 2. compares it with the version INSTALLED in /opt/glivarao/app (.deployed_commit) - so a `git pull` you ran
#    yourself beforehand no longer hides an update
# 3. waits until no production run is active, snapshots the installed code, installs, runs a smoke test
# 4. if anything fails: restores the previous version and sends you a Telegram alert
# Data, output, .env, secrets and models are never touched.
set -euo pipefail
SRC=/root/glivarao-src
APP=/opt/glivarao/app
SNAP=/opt/glivarao/rollback
BRANCH=claude/glivarao-finance-mvp-n153rg
LOG=/var/log/glivarao-update.log
FORCE="${1:-}"
mkdir -p "$SNAP"
touch "$LOG" && chmod 600 "$LOG"
cd "$SRC"

echo "==> fetching the newest version"
for i in 1 2 3 4; do git fetch -q origin "$BRANCH" && break; echo "   network error, retrying in $((i * 10)) s"; sleep $((i * 10)); done
git reset -q --hard FETCH_HEAD
NEW=$(git rev-parse HEAD)
DEPLOYED=$(cat "$APP/.deployed_commit" 2>/dev/null || echo "none")
echo "   installed: ${DEPLOYED:0:8}   newest: ${NEW:0:8}"
if [ "$NEW" = "$DEPLOYED" ] && [ "$FORCE" != "--force" ]; then
  echo "already up to date (installed version = newest). Use --force to reinstall anyway."
  exit 0
fi

echo "==> waiting for any running production job to finish (up to 2 h)"
mkdir -p "$APP/data"
exec 9>"$APP/data/daily.lock"
flock -w 7200 9 || { echo "a production run is still active; try again later"; exit 1; }

TS=$(date +%Y%m%d-%H%M%S)
echo "==> snapshot of the installed version (${DEPLOYED:0:8})"
tar -C "$APP" --exclude=.venv --exclude=output --exclude=data --exclude=downloads --exclude=reports \
    --exclude=models --exclude=secrets --exclude=.env --exclude=logs --exclude=__pycache__ \
    -czf "$SNAP/app-$TS.tar.gz" .
ls -1t "$SNAP"/app-*.tar.gz | tail -n +6 | xargs -r rm -f   # keep the last 5 snapshots

rollback() {
  echo "!!! update failed: rolling back to ${DEPLOYED:0:8} (details: $LOG)"
  tar -C "$APP" -xzf "$SNAP/app-$TS.tar.gz"
  if [ "$DEPLOYED" != "none" ]; then git -C "$SRC" reset -q --hard "$DEPLOYED" || true; fi
  flock -u 9 || true
  bash "$SRC/deploy/install.sh" >> "$LOG" 2>&1 || true
  sudo -u glivarao bash -c "cd $APP && .venv/bin/python -m glivarao alert 'update to ${NEW:0:8} failed and was rolled back to ${DEPLOYED:0:8}. Details: $LOG'" || true
  exit 1
}

echo "==> installing ${NEW:0:8} (log: $LOG)"
flock -u 9
bash deploy/install.sh >> "$LOG" 2>&1 || rollback

echo "==> smoke test"
sudo -u glivarao bash -c "cd $APP && .venv/bin/python -m glivarao doctor --strict" >> "$LOG" 2>&1 || rollback
sudo -u glivarao bash -c "cd $APP && .venv/bin/python -m glivarao health --no-telegram" >> "$LOG" 2>&1 || rollback
[ "$(cat "$APP/.deployed_commit" 2>/dev/null)" = "$NEW" ] || rollback

echo "updated ${DEPLOYED:0:8} -> ${NEW:0:8}. Rollback snapshot: $SNAP/app-$TS.tar.gz"
sudo -u glivarao bash -c "cd $APP && .venv/bin/python -m glivarao alert --info 'updated to ${NEW:0:8} (smoke test passed)'" || true
