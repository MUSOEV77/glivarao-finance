"""`python -m glivarao doctor [--live] [--strict]`: every key and setting, shown as ok / MISSING / INVALID / warn.

Key values are never printed: only whether they are set and look right.
--live  also makes tiny real calls (cost well under one cent in total):
        Telegram getMe + getChat, YouTube Data API (1 quota unit), Gemini (model lookups for the voice, image and
        fallback-writer models + a few-token test answer), Claude on Vertex (or the Anthropic API) one short answer.
--strict exits 1 only when the installation itself is broken (used by deploy/update.sh to decide on a rollback),
        never for keys you haven't added yet.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

GOOGLE_KEY = re.compile(r"^AIza[0-9A-Za-z_\-]{35}$")
TG_TOKEN = re.compile(r"^\d{6,12}:[A-Za-z0-9_\-]{30,}$")
GCP_PROJECT = re.compile(r"^[a-z][a-z0-9\-]{4,28}[a-z0-9]$")


class Report:
    def __init__(self):
        self.broken, self.todo, self.warn = [], [], []

    def row(self, state: str, name: str, detail: str = "", critical: bool = False):
        mark = {"ok": "  ok   ", "MISSING": "MISSING", "INVALID": "INVALID", "warn": " warn  ", "info": "       "}[state]
        print(f"  [{mark}] {name:42s} {detail}")
        if state in ("MISSING", "INVALID"):
            (self.broken if critical else self.todo).append(name)
        elif state == "warn":
            self.warn.append(name)

    def check(self, ok: bool, name: str, detail_ok: str = "", detail_bad: str = "", bad: str = "INVALID",
              critical: bool = False):
        self.row("ok" if ok else bad, name, detail_ok if ok else detail_bad, critical)
        return ok


def _key(r: Report, name: str, value: str, rx: re.Pattern | None, hint: str, needed: bool = True):
    if not value:
        return r.row("MISSING" if needed else "info", name, f"-> {hint}" if needed else "(not used)")
    if rx is not None and not rx.match(value):
        return r.row("INVALID", name, f"set, but it doesn't look like a valid value ({len(value)} characters) -> "
                     f"{hint}")
    r.row("ok", name, "set")


def _perm(path: Path) -> str:
    return oct(stat.S_IMODE(path.stat().st_mode))[2:] if path.exists() else "-"


def check_settings(s, store) -> Report:
    from .tts import voice_lock

    r = Report()
    print("INSTALLATION")
    r.check(bool(shutil.which("ffmpeg")), "ffmpeg", "installed", "-> apt-get install ffmpeg", critical=True)
    try:
        store.kv_set("doctor_ping", "1")
        r.row("ok", "database", f"writable ({s.db_path})")
    except Exception as exc:  # noqa: BLE001
        r.row("INVALID", "database", f"not writable: {type(exc).__name__}", critical=True)
    env = Path(".env")
    if env.exists():
        r.check(_perm(env) in ("600", "400"), ".env file permissions", "600 (owner only)",
                f"{_perm(env)} -> chmod 600 .env", bad="INVALID")
    sec = Path("secrets")
    if sec.exists():
        r.check(_perm(sec) == "700", "secrets/ folder permissions", "700 (owner only)", f"{_perm(sec)} -> chmod 700 secrets")
    r.check(not s.youtube_publish_enabled, "YouTube auto-publishing", "OFF (you upload manually)",
            "ON -> must be false", critical=True)
    from .studio.health import disk_free_gb, failed_units

    free = disk_free_gb(Path(s.output_dir))
    r.check(free >= s.disk_alert_gb, "disk free", f"{free:.0f} GB", f"{free:.1f} GB (alert below {s.disk_alert_gb:g})",
            bad="warn")
    fails = failed_units()
    r.check(not fails, "systemd services", "none failed", "failed: " + ", ".join(fails), bad="warn")
    if Path("/var/run/reboot-required").exists():
        r.row("warn", "system restart", "required -> sudo bash deploy/safe-reboot.sh (waits for renders)")
    dep = Path(".deployed_commit")
    if dep.exists():
        r.row("info", "installed version", dep.read_text().strip()[:8])

    print("\nTELEGRAM")
    _key(r, "TELEGRAM_BOT_TOKEN", s.telegram_bot_token, TG_TOKEN, "deploy/set-key.sh TELEGRAM_BOT_TOKEN")
    _key(r, "TELEGRAM_APPROVER_CHAT_ID", s.telegram_approver_chat_id, re.compile(r"^-?\d+$"),
         "deploy/set-key.sh TELEGRAM_APPROVER_CHAT_ID")
    r.row("info", "TELEGRAM_API_BASE", f"{s.telegram_api_base} (max upload {s.telegram_max_upload_mb} MB)")

    print("\nPAID SERVICES (all capped in code)")
    r.check(s.allow_paid_apis, "ALLOW_PAID_APIS", "true", "false -> deploy/set-key.sh ALLOW_PAID_APIS true",
            bad="MISSING")
    _key(r, "GEMINI_API_KEY (voice, images, fallback writer)", s.gemini_api_key, GOOGLE_KEY,
         "deploy/set-key.sh GEMINI_API_KEY")
    _key(r, "YOUTUBE_API_KEY (competitor research)", s.youtube_api_key, GOOGLE_KEY, "deploy/set-key.sh YOUTUBE_API_KEY")

    print("\nSCRIPT WRITER")
    r.check(s.writer in ("claude_vertex", "claude_api", "free"), "WRITER", s.writer,
            f"{s.writer!r} -> claude_vertex | claude_api | free")
    if s.writer == "claude_vertex":
        _key(r, "VERTEX_PROJECT_ID", s.vertex_project_id, GCP_PROJECT, "deploy/set-vertex-key.sh sets it")
        r.row("ok" if s.vertex_region else "MISSING", "VERTEX_REGION", s.vertex_region or "-> global")
        r.row("ok" if s.vertex_model else "MISSING", "VERTEX_MODEL", s.vertex_model)
        kf = Path(s.vertex_credentials_file)
        if not kf.exists():
            r.row("MISSING", "Vertex service-account key", f"{kf} -> deploy/set-vertex-key.sh")
        else:
            perm = _perm(kf)
            try:
                d = json.loads(kf.read_text())
                good = d.get("type") == "service_account" and "private_key" in d
                proj_ok = d.get("project_id") == s.vertex_project_id
                r.check(good, "Vertex service-account key", f"{d.get('client_email', '?')}",
                        "not a service-account key -> deploy/set-vertex-key.sh")
                r.check(proj_ok, "key project = VERTEX_PROJECT_ID", d.get("project_id", "?"),
                        f"key is for {d.get('project_id')!r}, setting is {s.vertex_project_id!r}")
            except (OSError, ValueError):
                r.row("INVALID", "Vertex service-account key", "unreadable JSON -> deploy/set-vertex-key.sh")
            r.check(perm in ("600", "400"), "key file permissions", "600 (owner only)", f"{perm} -> chmod 600 {kf}")
    elif s.writer == "claude_api":
        _key(r, "ANTHROPIC_API_KEY", s.anthropic_api_key, re.compile(r"^sk-ant-"), "deploy/set-key.sh ANTHROPIC_API_KEY")
    r.row("info", "fallback writer", f"Gemini {s.gemini_writer_model} (automatic if Claude fails)")

    print("\nVOICE (locked)")
    try:
        voice_lock.check_model(s.gemini_tts_model)
        voice_lock.style_prompt(s)
        r.check(s.tts_provider == "gemini_tts", "TTS_PROVIDER", "gemini_tts", f"{s.tts_provider} -> gemini_tts")
        r.row("ok", "voice", f"{s.gemini_tts_voice} on {s.gemini_tts_model}, pace {s.gemini_tts_pace}")
        saved = store.kv_get("voice_lock")
        if saved and json.loads(saved) != voice_lock.fingerprint(s):
            r.row("INVALID", "voice lock", "settings changed since the lock -> voice-lock --reset if intended")
    except voice_lock.VoiceUnavailable as exc:
        r.row("INVALID", "voice settings", str(exc), critical=True)

    print("\nIMAGES")
    from .art.gemini_image import UNPINNED

    r.check(s.image_provider in ("gemini", "none"), "IMAGE_PROVIDER", s.image_provider, f"{s.image_provider!r}")
    r.check(bool(s.image_model) and not UNPINNED.search(s.image_model), "IMAGE_MODEL", s.image_model,
            f"{s.image_model!r} is not a pinned model")
    r.row("info", "sizes", f"scenes {s.image_scene_size}, thumbnails {s.image_thumb_size}, max {s.image_scenes_max} "
          "scenes per long video")

    print("\nMONTHLY CAPS (alert at {:.0%})".format(s.spend_alert_ratio))
    gemini_total = s.tts_monthly_budget_usd + s.image_monthly_budget_usd + s.gemini_writer_monthly_budget_usd
    for name, cap in (("Claude (writer)", s.claude_monthly_budget_usd), ("Gemini voice", s.tts_monthly_budget_usd),
                      ("Gemini images", s.image_monthly_budget_usd),
                      ("Gemini fallback writer", s.gemini_writer_monthly_budget_usd)):
        r.check(cap > 0, name, f"${cap:g}", f"${cap:g} -> must be above 0")
    r.check(gemini_total <= s.ai_studio_limit_usd, "AI Studio spend limit",
            f"${s.ai_studio_limit_usd:g} covers the Gemini caps (${gemini_total:g})",
            f"${s.ai_studio_limit_usd:g} is below the Gemini caps (${gemini_total:g}): raise it to ${gemini_total:g} in "
            "AI Studio (then set AI_STUDIO_LIMIT_USD), or the voice may stop late in the month", bad="warn")

    print("\nSCHEDULE AND PACE")
    try:
        ZoneInfo(s.local_tz)
        time.fromisoformat(s.quiet_start)
        time.fromisoformat(s.quiet_end)
        r.row("ok", "time zone and quiet hours", f"{s.local_tz}, quiet {s.quiet_start}-{s.quiet_end}")
    except Exception:  # noqa: BLE001
        r.row("INVALID", "time zone / quiet hours", f"{s.local_tz} {s.quiet_start}-{s.quiet_end}")
    r.check(s.long_videos_per_month == 16 and s.shorts_per_month == 90 and s.shorts_per_day == 3, "pace",
            "16 long + 90 Shorts a month (3 a day)",
            f"{s.long_videos_per_month} long + {s.shorts_per_month} Shorts ({s.shorts_per_day}/day)", bad="warn")
    r.row("info", "buffer", f"{s.buffer_long} long + {s.buffer_shorts} Shorts ready, {s.production_lead_days} days ahead")
    sys_tz = os.environ.get("TZ") or (Path("/etc/timezone").read_text().strip() if Path("/etc/timezone").exists() else "")
    if sys_tz:
        r.check(sys_tz == s.local_tz, "server clock", sys_tz,
                f"{sys_tz} -> timedatectl set-timezone {s.local_tz}", bad="warn")
    return r


# ------------------------------------------------------------------------------------------- live checks
def live_checks(s, r: Report, session=None) -> None:
    import requests

    http = session or requests.Session()
    print("\nLIVE TESTS (tiny real calls)")

    def say(ok, name, good, bad):
        r.check(ok, name, good, bad)

    if s.telegram_bot_token:
        try:
            from .publish.telegram import _client

            c = _client(s, None)
            me = c.call("getMe")
            say(True, "Telegram bot", f"@{me.get('username')}", "")
            if s.telegram_approver_chat_id:
                c.call("getChat", chat_id=s.telegram_approver_chat_id)
                say(True, "Telegram chat", "reachable", "")
        except Exception as exc:  # noqa: BLE001
            say(False, "Telegram", "", f"failed: {str(exc)[:100]} (send /start to your bot first?)")
    if s.youtube_api_key:
        try:
            res = http.get("https://www.googleapis.com/youtube/v3/i18nRegions", params={"part": "snippet", "hl": "en"},
                           headers={"x-goog-api-key": s.youtube_api_key}, timeout=30)
            reason = ""
            if res.status_code != 200:
                try:
                    reason = res.json()["error"]["errors"][0]["reason"]
                except Exception:  # noqa: BLE001
                    pass
            say(res.status_code == 200, "YouTube Data API", "key works (1 quota unit)",
                f"HTTP {res.status_code} {reason} (enable 'YouTube Data API v3' for this key's project?)")
        except Exception as exc:  # noqa: BLE001
            say(False, "YouTube Data API", "", f"network error {type(exc).__name__}")
    if s.gemini_api_key:
        base = "https://generativelanguage.googleapis.com/v1beta/models/"
        hdr = {"x-goog-api-key": s.gemini_api_key}
        for label, model in (("Gemini voice model", s.gemini_tts_model), ("Gemini image model", s.image_model),
                             ("Gemini fallback writer", s.gemini_writer_model)):
            try:
                res = http.get(base + model, headers=hdr, timeout=30)
                say(res.status_code == 200, label, f"{model} available", f"{model}: HTTP {res.status_code}")
            except Exception as exc:  # noqa: BLE001
                say(False, label, "", f"network error {type(exc).__name__}")
        try:
            res = http.get(base.rstrip("/"), params={"pageSize": 200}, headers=hdr, timeout=30)
            if res.status_code == 200:
                pros = sorted(m["name"].split("/")[-1] for m in res.json().get("models", [])
                              if "pro" in m["name"] and "generateContent" in m.get("supportedGenerationMethods", []))
                r.row("info", "Pro models for your key", ", ".join(pros[:8]) or "none")
            res = http.post(base + s.gemini_writer_model + ":generateContent", headers=hdr, timeout=60, json={
                "contents": [{"parts": [{"text": "Reply with the single word OK."}]}],
                "generationConfig": {"maxOutputTokens": 64}})
            say(res.status_code == 200, "Gemini test answer", "billing works", f"HTTP {res.status_code} (billing "
                "enabled on the AI Studio project? Tier 1?)")
        except Exception as exc:  # noqa: BLE001
            say(False, "Gemini test answer", "", f"network error {type(exc).__name__}")
    if s.writer in ("claude_vertex", "claude_api"):
        try:
            from .scriptgen.backends import claude_client
            from .scriptgen.claude import ClaudeSpendLedger, usage_cost

            client, platform, model, p_in, p_out = claude_client(s)
            msg = client.messages.create(model=model, max_tokens=256, output_config={"effort": "low"},
                                         messages=[{"role": "user", "content": "Reply with the single word OK."}])
            usd, tin, tout = usage_cost(msg.usage, p_in, p_out)
            ClaudeSpendLedger(Path(s.claude_spend_ledger_path)).add(usd, tin, tout)
            text = next((b.text for b in msg.content if getattr(b, "type", "") == "text"), "").strip()
            say(msg.stop_reason in ("end_turn", "max_tokens"), f"Claude ({'Vertex AI' if platform == 'vertex' else 'API'})",
                f"{model} answered '{text[:20]}' (${usd:.4f})", f"stop: {msg.stop_reason}")
        except Exception as exc:  # noqa: BLE001
            hint = ""
            name = type(exc).__name__
            if "PermissionDenied" in name or "403" in str(exc):
                hint = " (grant the service account 'Vertex AI User'; enable Claude Sonnet 5.5 in Model Garden)"
            elif "NotFound" in name or "404" in str(exc):
                hint = " (model not enabled for this project/region in Vertex AI Model Garden?)"
            say(False, "Claude writer", "", f"{name}: {str(exc)[:120]}{hint}")


def run(s, store, live: bool = False, strict: bool = False, session=None) -> Report:
    print("GLIVARAO doctor (key values are never shown)\n")
    r = check_settings(s, store)
    if live:
        live_checks(s, r, session)
    print()
    if r.broken:
        print("BROKEN (fix first): " + ", ".join(r.broken))
    print(("to do: " + ", ".join(r.todo)) if r.todo else "all keys and settings look right")
    if r.warn:
        print("warnings: " + ", ".join(r.warn))
    if not live:
        print("tip: add --live to test every API with a tiny real call")
    if strict and r.broken:
        raise SystemExit(1)
    return r


__all__ = ["run", "check_settings", "live_checks", "Report"]
