#!/usr/bin/env bash
# Reboot the VPS safely (e.g. when Ubuntu says "System restart required" after security updates):
#   sudo bash /opt/glivarao/app/deploy/safe-reboot.sh          # reboot now, as soon as no video is rendering
#   sudo bash /opt/glivarao/app/deploy/safe-reboot.sh --check  # only tell me if a reboot is needed
# Waits for the production lock (same one as the daily run), so a render is never cut off. All GLIVARAO timers
# are persistent: anything that was due while the server was down runs right after it comes back.
set -euo pipefail
APP=/opt/glivarao/app
if [ -f /var/run/reboot-required ]; then
  echo "A reboot IS needed:"; cat /var/run/reboot-required.pkgs 2>/dev/null | sed 's/^/  - /' | head -20
else
  echo "No reboot needed right now."
  [ "${1:-}" = "--check" ] && exit 0
fi
[ "${1:-}" = "--check" ] && exit 0
if systemctl is-active --quiet glivarao-daily.service; then
  echo "Production is running; waiting for it to finish (up to 3 h)..."
fi
exec 9>"$APP/data/daily.lock"
flock -w 10800 9 || { echo "production still running after 3 h; not rebooting"; exit 1; }
sudo -u glivarao bash -c "cd $APP && .venv/bin/python -m glivarao alert --info 'server rebooting now for system updates; back in about 1-2 minutes'" || true
echo "Rebooting now. Reconnect in Termius in about 1-2 minutes."
systemctl reboot
