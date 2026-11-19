#!/usr/bin/env bash
# Safe update with automatic rollback. Run on the VPS as root:
#   sudo bash /root/glivarao-src/deploy/update.sh
# 1. waits until no production run is active (same lock as the daily run)
# 2. snapshots the current app code + venv requirements and remembers the current git commit
# 3. pulls the new code and installs it (data, output, .env, secrets and models are never touched)
# 4. smoke test: doctor (strict) + health report + CLI import checks
# 5. if anything fails: restores the previous code, reinstalls it and sends you a Telegram alert
set -euo pipefail
SRC=/root/glivarao-src
APP=/opt/glivarao/app
SNAP=/opt/glivarao/rollback
BRANCH=claude/glivarao-finance-mvp-n153rg
mkdir -p "$SNAP"
cd "$SRC"
PREV=$(git rev-parse HEAD)
TS=$(date +%Y%m%d-%H%M%S)

echo "==> waiting for any running production job to finish (up to 2 h)"
exec 9>"$APP/data/daily.lock"
flock -w 7200 9 || { echo "a production run is still active; try again later"; exit 1; }

echo "==> snapshot of the current version ($PREV)"
tar -C "$APP" --exclude=.venv --exclude=output --exclude=data --exclude=downloads --exclude=reports \
    --exclude=models --exclude=secrets --exclude=.env --exclude=logs --exclude=__pycache__ \
    -czf "$SNAP/app-$TS.tar.gz" .
echo "$PREV" > "$SNAP/app-$TS.commit"
ls -1t "$SNAP"/app-*.tar.gz | tail -n +6 | xargs -r rm -f   # keep the last 5 snapshots

rollback() {
  echo "!!! update failed: rolling back to $PREV"
  git -C "$SRC" checkout -q "$PREV"
  tar -C "$APP" -xzf "$SNAP/app-$TS.tar.gz"
  flock -u 9 || true
  bash "$SRC/deploy/install.sh" > /tmp/glivarao-rollback.log 2>&1 || true
  sudo -u glivarao bash -c "cd $APP && .venv/bin/python -m glivarao alert 'update failed and was rolled back to ${PREV:0:8}. Details: /tmp/glivarao-update.log'" || true
  git -C "$SRC" checkout -q "$BRANCH" || true
  exit 1
}

echo "==> pulling the new version"
git fetch -q origin "$BRANCH" && git checkout -q "$BRANCH" && git merge -q --ff-only FETCH_HEAD || rollback
NEW=$(git rev-parse HEAD)
if [ "$NEW" = "$PREV" ]; then echo "already up to date ($NEW)"; exit 0; fi

echo "==> installing $NEW"
flock -u 9
bash deploy/install.sh > /tmp/glivarao-update.log 2>&1 || rollback

echo "==> smoke test"
sudo -u glivarao bash -c "cd $APP && .venv/bin/python -m glivarao doctor --strict" >> /tmp/glivarao-update.log 2>&1 || rollback
sudo -u glivarao bash -c "cd $APP && .venv/bin/python -m glivarao health --no-telegram" >> /tmp/glivarao-update.log 2>&1 || rollback
sudo -u glivarao bash -c "cd $APP && .venv/bin/python -m glivarao --help" > /dev/null 2>&1 || rollback

echo "updated ${PREV:0:8} -> ${NEW:0:8}. Rollback snapshot: $SNAP/app-$TS.tar.gz"
sudo -u glivarao bash -c "cd $APP && .venv/bin/python -m glivarao alert 'updated to ${NEW:0:8} (smoke test passed)'" || true
