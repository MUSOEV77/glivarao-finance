#!/usr/bin/env bash
# Set one setting in /opt/glivarao/app/.env without a text editor (phone friendly).
#   sudo bash deploy/set-key.sh TELEGRAM_BOT_TOKEN        # asks for the value, hidden (paste + Enter)
#   sudo bash deploy/set-key.sh ALLOW_PAID_APIS true      # non-secret value given directly
# The value is never printed, never stored in shell history, and .env stays readable only by 'glivarao'.
set -euo pipefail
ENV_FILE="${ENV_FILE:-/opt/glivarao/app/.env}"
NAME="${1:?usage: set-key.sh NAME [VALUE]}"
[[ "$NAME" =~ ^[A-Z][A-Z0-9_]*$ ]] || { echo "invalid name: $NAME"; exit 1; }
[ -f "$ENV_FILE" ] || { echo "$ENV_FILE not found (run deploy/install.sh first)"; exit 1; }
if [ $# -ge 2 ]; then
  VALUE="$2"
else
  read -r -s -p "Paste value for $NAME, then press Enter: " VALUE
  echo
fi
[ -n "$VALUE" ] || { echo "empty value, nothing changed"; exit 1; }
VALUE="$VALUE" python3 - "$ENV_FILE" "$NAME" <<'PY'
import os, sys
path, name, value = sys.argv[1], sys.argv[2], os.environ["VALUE"].strip()
lines = open(path).read().splitlines()
out, done = [], False
for line in lines:
    if line.split("=", 1)[0].strip() == name and not line.lstrip().startswith("#"):
        out.append(f"{name}={value}"); done = True
    else:
        out.append(line)
if not done:
    out.append(f"{name}={value}")
open(path, "w").write("\n".join(out) + "\n")
PY
chmod 600 "$ENV_FILE"
id glivarao >/dev/null 2>&1 && chown glivarao:glivarao "$ENV_FILE" || true
echo "$NAME saved (value hidden)."
