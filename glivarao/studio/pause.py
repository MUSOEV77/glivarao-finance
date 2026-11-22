"""Production pause: a file `data/PAUSED` that every production entry point checks. Survives updates/reboots.

    python -m glivarao pause --reason "audit"     # stop all production (long, Shorts, retries, remakes)
    python -m glivarao pause --status
    python -m glivarao resume                     # only when you explicitly approve restarting

While paused: no research-driven planning, no script/voice/image generation, no held-video retries, no remakes,
no voice auditions, no paid live tests in doctor. Still active: Telegram polling (your buttons, reviews already
made, upload packs), the health report, backups and the dashboard. Nothing is ever published automatically.
deploy/install.sh also keeps the production timers off while this file exists.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def pause_file(settings) -> Path:
    return Path(settings.db_path).with_name("PAUSED")


def status(settings) -> dict | None:
    p = pause_file(settings)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text() or "{}") or {"since": "?", "reason": "paused"}
    except ValueError:
        return {"since": "?", "reason": p.read_text()[:200] or "paused"}


def pause(settings, reason: str = "") -> dict:
    p = pause_file(settings)
    p.parent.mkdir(parents=True, exist_ok=True)
    info = {"since": datetime.now(timezone.utc).isoformat(timespec="seconds"), "reason": reason or "paused by owner"}
    p.write_text(json.dumps(info))
    return info


def resume(settings) -> bool:
    p = pause_file(settings)
    if p.exists():
        p.unlink()
        return True
    return False


class Paused(RuntimeError):
    pass


def guard(settings, what: str) -> None:
    """Raise Paused if production is paused (callers print it and exit 0, so timers never fail)."""
    st = status(settings)
    if st:
        raise Paused(f"production is PAUSED since {st.get('since')} ({st.get('reason')}): {what} skipped. "
                     "Resume only with: python -m glivarao resume")


__all__ = ["pause", "resume", "status", "guard", "Paused", "pause_file"]
