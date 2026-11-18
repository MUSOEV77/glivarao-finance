#!/usr/bin/env bash
# Daily backup (kept 30 days) and pruning of rendered output older than 30 days.
# Backs up: the SQLite job/approval/audit database (consistent online backup) and the paid-API spend ledgers.
# Never backs up .env or secrets/ (credentials stay only on the server).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
STAMP="$(date +%F)"
DB="${GLIVARAO_DB_PATH:-data/glivarao.sqlite3}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if [ -f "$DB" ]; then
  if command -v sqlite3 >/dev/null; then
    sqlite3 "$DB" ".backup '$TMP/glivarao.sqlite3'"
  else
    python3 -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close()" "$DB" "$TMP/glivarao.sqlite3"
  fi
  # verify the copy before keeping it
  python3 -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'" "$TMP/glivarao.sqlite3"
fi
for f in data/tts_spend.json data/tts_usage.json data/claude_spend.json; do
  [ -f "$f" ] && cp "$f" "$TMP/"
done
if [ -n "$(ls -A "$TMP")" ]; then
  tar -czf "backups/glivarao-$STAMP.tar.gz" -C "$TMP" .
fi
find backups -name 'glivarao-*.tar.gz' -mtime +30 -delete
find backups -name 'glivarao-*.sqlite3' -mtime +30 -delete
find output -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec rm -rf {} + 2>/dev/null || true
find reports/research/raw -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec rm -rf {} + 2>/dev/null || true
echo "backup ok $(date -Is)"
