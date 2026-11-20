#!/usr/bin/env bash
# Install the Vertex AI service-account JSON key for the Claude writer, securely (phone friendly):
#   sudo bash /opt/glivarao/app/deploy/set-vertex-key.sh                    # paste the JSON (hidden), then Ctrl+D
#   sudo bash /opt/glivarao/app/deploy/set-vertex-key.sh /root/key.json     # or use an uploaded file (then shredded)
# The key is checked (it must be a service-account key), saved to secrets/vertex-sa.json readable only by the
# 'glivarao' user (600, folder 700), never printed, never put in shell history, logs or Git (secrets/ is ignored).
# It also sets WRITER=claude_vertex and VERTEX_PROJECT_ID from the key.
set -euo pipefail
APP="${APP:-/opt/glivarao/app}"
export ENV_FILE="$APP/.env"
DST="$APP/secrets/vertex-sa.json"
umask 077
mkdir -p "$APP/secrets"
TMP=$(mktemp "$APP/secrets/.vertex-XXXXXX")
trap 'shred -u "$TMP" 2>/dev/null || rm -f "$TMP"' EXIT
if [ $# -ge 1 ]; then
  [ -f "$1" ] || { echo "file not found: $1"; exit 1; }
  cat "$1" > "$TMP"
  SRC_FILE="$1"
else
  echo "Paste the whole JSON key now (nothing will show on screen)."
  echo "When it's pasted, press Enter, then Ctrl+D (in Termius: the keyboard's Ctrl key, then D)."
  stty -echo 2>/dev/null || true
  cat > "$TMP"
  stty echo 2>/dev/null || true
  echo
  SRC_FILE=""
fi
INFO=$(python3 - "$TMP" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("ERROR not valid JSON (paste the whole file, from { to })"); sys.exit(0)
need = {"type", "project_id", "private_key", "client_email", "token_uri"}
if d.get("type") != "service_account" or not need <= d.keys():
    print("ERROR this is not a service-account key file"); sys.exit(0)
print(f"OK {d['project_id']} {d['client_email']}")
PY
)
case "$INFO" in
  OK*) ;;
  *) echo "${INFO#ERROR }. Nothing was saved."; exit 1 ;;
esac
read -r _ PROJECT EMAIL <<< "$INFO"
mv "$TMP" "$DST"
trap - EXIT
id glivarao >/dev/null 2>&1 && chown glivarao:glivarao "$DST" "$APP/secrets"
chmod 600 "$DST"; chmod 700 "$APP/secrets"
if [ -n "$SRC_FILE" ]; then shred -u "$SRC_FILE" 2>/dev/null || rm -f "$SRC_FILE"; echo "Uploaded copy deleted."; fi
bash "$(dirname "$0")/set-key.sh" WRITER claude_vertex >/dev/null
bash "$(dirname "$0")/set-key.sh" VERTEX_PROJECT_ID "$PROJECT" >/dev/null
grep -q '^VERTEX_REGION=[a-z]' "$ENV_FILE" 2>/dev/null || bash "$(dirname "$0")/set-key.sh" VERTEX_REGION global >/dev/null
bash "$(dirname "$0")/set-key.sh" VERTEX_MODEL claude-sonnet-5-5 >/dev/null
echo "Saved: service account $EMAIL, project $PROJECT (file is owner-only)."
echo "Test it:  cd $APP && sudo -u glivarao .venv/bin/python -m glivarao doctor --live"
