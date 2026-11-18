#!/usr/bin/env bash
# Daily: consistent SQLite backup (kept 30 days) and pruning of rendered output older than 30 days.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
DB="${GLIVARAO_DB_PATH:-data/glivarao.sqlite3}"
[ -f "$DB" ] && sqlite3 "$DB" ".backup 'backups/glivarao-$(date +%F).sqlite3'"
find backups -name 'glivarao-*.sqlite3' -mtime +30 -delete
find output -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec rm -rf {} +
find reports/research/raw -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec rm -rf {} + 2>/dev/null || true
echo "backup ok $(date -Is)"
