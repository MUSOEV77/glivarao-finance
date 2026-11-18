#!/usr/bin/env bash
# Restore the job database and spend ledgers from a backup made by backup.sh.
#   deploy/restore.sh backups/glivarao-2026-11-18.tar.gz
# Stops the timers first so nothing writes during the restore; the current files are kept as *.before-restore.
set -euo pipefail
cd "$(dirname "$0")/.."
ARCHIVE="${1:?usage: deploy/restore.sh backups/glivarao-YYYY-MM-DD.tar.gz}"
DB="${GLIVARAO_DB_PATH:-data/glivarao.sqlite3}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
tar -xzf "$ARCHIVE" -C "$TMP"
python3 -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'" "$TMP/glivarao.sqlite3"
if command -v systemctl >/dev/null && [ "$(id -u)" = 0 ]; then
  systemctl stop glivarao-daily.timer glivarao-poll.timer 2>/dev/null || true
fi
mkdir -p data
[ -f "$DB" ] && cp "$DB" "$DB.before-restore"
cp "$TMP/glivarao.sqlite3" "$DB"
for f in tts_spend.json tts_usage.json claude_spend.json; do
  if [ -f "$TMP/$f" ]; then [ -f "data/$f" ] && cp "data/$f" "data/$f.before-restore"; cp "$TMP/$f" "data/$f"; fi
done
if command -v systemctl >/dev/null && [ "$(id -u)" = 0 ]; then
  chown -R glivarao:glivarao data 2>/dev/null || true
  systemctl start glivarao-daily.timer glivarao-poll.timer 2>/dev/null || true
fi
echo "restored from $ARCHIVE"
