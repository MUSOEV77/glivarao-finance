"""Daily health report (09:05 Tashkent) and alert checks: failures, disk, spend at 80%, buffer low.

    python -m glivarao health          # print + send to Telegram (glivarao-health.timer)
    python -m glivarao alert "text"    # used by systemd OnFailure= when any GLIVARAO service fails
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path


def _spend(settings) -> list[tuple[str, float, float]]:
    from ..scriptgen.claude import ClaudeSpendLedger
    from ..tts.gemini_tts import SpendLedger

    m = date.today().strftime("%Y-%m")
    return [("Voice (Gemini Charon)", SpendLedger(Path(settings.tts_spend_ledger_path)).spent(m),
             settings.tts_monthly_budget_usd),
            ("Scripts (Claude)", ClaudeSpendLedger(Path(settings.claude_spend_ledger_path)).spent(m),
             settings.claude_monthly_budget_usd)]


def spend_alerts(settings, store) -> list[str]:
    """One alert per service per month at SPEND_ALERT_RATIO (80%) and one at the cap."""
    out, month = [], date.today().strftime("%Y-%m")
    for name, spent, cap in _spend(settings):
        if cap <= 0:
            continue
        level = 100 if spent >= cap * 0.995 else (80 if spent >= cap * settings.spend_alert_ratio else 0)
        key = f"spend_alert:{name}:{month}"
        if level and int(store.kv_get(key, "0")) < level:
            store.kv_set(key, str(level))
            out.append(f"💰 {name}: ${spent:.2f} of ${cap:.2f} this month ({spent / cap:.0%})."
                       + (" Cap reached: paid use stops until next month (videos wait; nothing else is used)."
                          if level == 100 else " Hard cap stops spending at 100%."))
    return out


def disk_free_gb(path: Path) -> float:
    return shutil.disk_usage(path if path.exists() else Path(".")).free / 1e9


def failed_units() -> list[str]:
    if not shutil.which("systemctl"):
        return []
    try:
        r = subprocess.run(["systemctl", "list-units", "--failed", "--plain", "--no-legend", "glivarao-*"],
                           capture_output=True, text=True, timeout=20)
        return [ln.split()[0] for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:  # noqa: BLE001
        return []


def alerts(settings, store) -> list[str]:
    """Problems worth an alert right now (also listed at the top of the health report)."""
    from . import buffer

    out = spend_alerts(settings, store)
    free = disk_free_gb(Path(settings.output_dir))
    if free < settings.disk_alert_gb:
        out.append(f"💽 Disk low: {free:.1f} GB free (alert below {settings.disk_alert_gb:g} GB). Old renders can be "
                   "pruned from output/.")
    b = buffer.status(store, settings)
    if b["low_long"] or b["low_shorts"]:
        key = f"buffer_alert:{date.today().isoformat()}"
        if not store.kv_get(key):
            store.kv_set(key, "1")
            out.append("📉 Buffer low:\n" + buffer.text(b, settings) + "\nApprove the videos waiting for review; "
                       "the next production run makes extra Shorts (up to 6) and an early long video if needed.")
    fails = failed_units()
    if fails:
        out.append("🔴 Failed services: " + ", ".join(fails) + " (they restart automatically; see logs/).")
    return out


def report(settings, store) -> str:
    from ..daily_v2 import held_videos
    from . import buffer, launch_plan, quiet
    from .planner import active_item

    b = buffer.status(store, settings)
    lines = [f"🩺 GLIVARAO health — {date.today():%a %d %b %Y}", "", "BUFFER", buffer.text(b, settings), ""]
    made, due = buffer.long_due(store, date.today(), settings)
    shorts = sum(n for d, n in json.loads(store.kv_get("short_counts", "{}")).items()
                 if d[:7] == date.today().isoformat()[:7])
    lines += ["PACE (this month)", f"Long videos: {made}/{settings.long_videos_per_month} (due by now incl. "
              f"{settings.production_lead_days}-day lead: {due})",
              f"Shorts: {shorts}/{settings.shorts_per_month}",
              f"Launch list: {16 - launch_plan.remaining(store)}/16 planned", ""]
    nxt = active_item(store)
    lines += ["NEXT", f"{nxt.topic} ({nxt.status})" if nxt else "Next topic is picked at 09:00", ""]
    held = held_videos(store)
    lines += ["SPEND"] + [f"{n}: ${s:.2f} of ${c:.2f} ({s / c:.0%})" if c else f"{n}: ${s:.2f}"
                          for n, s, c in _spend(settings)]
    lines += ["", "SYSTEM", f"Disk free: {disk_free_gb(Path(settings.output_dir)):.1f} GB",
              f"Voice: {settings.gemini_tts_voice} on {settings.gemini_tts_model}"
              + (f" · ⏸ {len(held)} video(s) on hold" if held else " · OK"),
              f"Failed services: {', '.join(failed_units()) or 'none'}"]
    q = quiet.pending(store)
    if any(q):
        lines.append(f"Queued from quiet hours: {q[0]} alert(s), {q[1]} review(s)")
    return "\n".join(lines)


__all__ = ["report", "alerts", "spend_alerts", "disk_free_gb", "failed_units"]
