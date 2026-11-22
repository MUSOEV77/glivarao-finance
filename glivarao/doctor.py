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

# Google API keys: classic "AIza…" (39 chars) or the newer AI Studio auth keys "AQ.…" (both work in x-goog-api-key)
GOOGLE_KEY = re.compile(r"^(AIza[0-9A-Za-z_\-]{35}|AQ\.[A-Za-z0-9_\-.]{20,})$")
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
    _key(r, "GEMINI_API_KEY (voice, images)", s.gemini_api_key, GOOGLE_KEY,
         "deploy/set-key.sh GEMINI_API_KEY")
    _key(r, "YOUTUBE_API_KEY (competitor research)", s.youtube_api_key, GOOGLE_KEY, "deploy/set-key.sh YOUTUBE_API_KEY")

    print("\nSCRIPT WRITER")
    r.check(s.writer in ("claude_openrouter", "claude_vertex", "claude_api", "free"), "WRITER", s.writer,
            f"{s.writer!r} -> claude_openrouter | claude_vertex | claude_api | free")
    if s.writer == "free":
        r.row("warn", "WRITER", "free = offline templates (development only); production holds instead of using them")
    if s.writer == "claude_openrouter":
        _key(r, "OPENROUTER_API_KEY", s.openrouter_api_key, re.compile(r"^sk-or-[A-Za-z0-9_-]{20,}$"),
             "deploy/set-key.sh OPENROUTER_API_KEY")
        r.check(s.openrouter_model.startswith("anthropic/claude-"), "OPENROUTER_MODEL", s.openrouter_model,
                f"{s.openrouter_model!r} is not a Claude model (Claude only) -> anthropic/claude-sonnet-5.5")
        r.row("info", "OpenRouter price / effort", f"${s.openrouter_price_in:g} in / ${s.openrouter_price_out:g} out "
              f"per 1M tokens (pre-flight cap check; real cost recorded), effort {s.openrouter_effort or 'default'}")
    elif s.writer == "claude_vertex":
        _key(r, "VERTEX_PROJECT_ID", s.vertex_project_id, GCP_PROJECT, "deploy/set-vertex-key.sh sets it")
        r.check(s.vertex_region in ("global", "us", "eu"), "VERTEX_REGION", s.vertex_region,
                f"{s.vertex_region!r} -> global, us or eu (Claude Sonnet 5.5 endpoints)")
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
    r.row("ok", "writer rule", "Claude only: no fallback writer (held + hourly retry + one alert a day if Claude "
          "can't write)")
    if os.environ.get("FALLBACK_WRITER", os.environ.get("WRITER_FALLBACK", "off")).lower() not in ("", "off", "none"):
        r.row("warn", "FALLBACK_WRITER", "set in .env but ignored: the Gemini writer was removed (Claude only)")
    held = json.loads(store.kv_get("writer_held", "{}"))
    if held:
        r.row("warn", "production", f"on hold since {held.get('since')}: Claude unavailable ({held.get('reason', '')[:80]})")
    r.row("info", "Shorts length", f"max {s.short_max_words} words; voiced and measured before rendering; over "
          f"{s.short_redo_seconds:g} s re-voiced (2x); over {s.short_tempo_seconds:g} s sped up (max "
          f"x{s.short_max_tempo:g}); held over {s.short_max_seconds:g} s; never sent over {s.short_max_seconds:g} s")
    r.row("info", "frame rate", f"{s.fps} fps (long 1920x1080, Shorts 1080x1920)")

    print("\nVOICE (locked)")
    try:
        voice_lock.check_model(s.gemini_tts_model)
        voice_lock.style_prompt(s)
        r.check(s.tts_provider == "gemini_tts", "TTS_PROVIDER", "gemini_tts", f"{s.tts_provider} -> gemini_tts")
        r.row("ok", "voice", f"{s.gemini_tts_voice} on {s.gemini_tts_model}, pace {s.gemini_tts_pace}, speed "
              f"x{s.gemini_tts_speed} (target {s.tts_target_wpm} wpm)")
        saved = store.kv_get("voice_lock")
        if saved and json.loads(saved) != voice_lock.fingerprint(s):
            r.row("INVALID", "voice lock", "settings changed since the lock -> voice-lock --reset if intended")
        elif saved:
            src = json.loads(store.kv_get("voice_locked_from", "{}")).get("job")
            r.row("ok", "voice lock", "LOCKED for every long video and Short" + (f" (copied from {src})" if src else ""))
        else:
            r.row("warn", "voice lock", "not recorded yet (recorded on the first narration)")
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
    gemini_total = s.tts_monthly_budget_usd + s.image_monthly_budget_usd
    for name, cap in (("Claude (writer)", s.claude_monthly_budget_usd), ("Gemini voice", s.tts_monthly_budget_usd),
                      ("Gemini images", s.image_monthly_budget_usd)):
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
        models = [("Gemini voice model", s.gemini_tts_model), ("Gemini image model", s.image_model)]
        for label, model in models:
            try:
                res = http.get(base + model, headers=hdr, timeout=30)
                say(res.status_code == 200, label, f"{model} available", f"{model}: HTTP {res.status_code}")
            except Exception as exc:  # noqa: BLE001
                say(False, label, "", f"network error {type(exc).__name__}")
        try:
            # billing check on the VOICE model (Gemini is used only for voice and images): a one-word clip
            res = http.post(base + s.gemini_tts_model + ":generateContent", headers=hdr, timeout=60, json={
                "contents": [{"parts": [{"text": "OK."}]}],
                "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": s.gemini_tts_voice}}}}})
            hint = {402: "prepay balance is empty: buy credits on the AI Studio Billing page (a Cloud Billing "
                         "credit balance does not count)",
                    403: "key not allowed for this API/project", 429: "rate limit or quota"}.get(res.status_code, "")
            say(res.status_code == 200, "Gemini test answer (voice)", "billing works",
                f"HTTP {res.status_code}" + (f": {hint}" if hint else ""))
            if res.status_code != 200:
                print("        full error from Google:\n" + _error_body(res, s.gemini_api_key))
        except Exception as exc:  # noqa: BLE001
            say(False, "Gemini test answer", "", f"network error {type(exc).__name__}")
    if s.writer == "claude_openrouter":
        openrouter_live(s, r, http)
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
            if "RateLimit" in name or "429" in str(exc):
                hint = (" (Vertex quota for anthropic-claude-sonnet is 0 or used up in region "
                        f"{s.vertex_region}: run deploy/vertex-quota.sh in Cloud Shell, or switch: WRITER=claude_openrouter)")
            elif "PermissionDenied" in name or "403" in str(exc):
                hint = " (grant the service account 'Vertex AI User'; enable Claude Sonnet 5.5 in Model Garden)"
            elif "NotFound" in name or "404" in str(exc):
                hint = " (model not enabled for this project/region in Vertex AI Model Garden?)"
            say(False, "Claude writer", "", f"{name}{hint}")
            print("        full error:\n        " + str(exc)[:1500].replace("\n", "\n        "))


def openrouter_live(s, r: Report, http=None) -> None:
    """Tiny real OpenRouter call (a few tokens, well under a cent, counted in the Claude cap) + the key's credit."""
    from .scriptgen.backends import WriterUnavailable, openrouter_chat
    from .scriptgen.claude import ClaudeSpendLedger

    try:
        text, u = openrouter_chat(s, "You are a test.", "Reply with the single word OK.", max_tokens=16,
                                  session=http, attempts=2)
        tin, tout = u["prompt_tokens"], u["completion_tokens"]
        usd = float(u["cost"]) if u.get("cost") is not None else (tin * s.openrouter_price_in
                                                                    + tout * s.openrouter_price_out) / 1e6
        ClaudeSpendLedger(Path(s.claude_spend_ledger_path)).add(usd, tin, tout)
        r.check(bool(text.strip()), "Claude (OpenRouter)", f"{u.get('model')} answered '{text.strip()[:20]}' "
                f"(${usd:.5f})", f"{u.get('model')} gave an empty answer ({u.get('finish_reason')})")
    except WriterUnavailable as exc:
        r.check(False, "Claude (OpenRouter)", "", str(exc)[:300])
    try:
        res = (http or __import__("requests")).get("https://openrouter.ai/api/v1/key", timeout=30,
                                                    headers={"Authorization": f"Bearer {s.openrouter_api_key}"})
        if res.status_code == 200:
            d = res.json().get("data", {})
            lim = d.get("limit_remaining")
            r.row("info", "OpenRouter key", f"used ${float(d.get('usage') or 0):.2f}"
                  + (f", ${float(lim):.2f} left on the key's limit" if lim is not None else ", no key limit set")
                  + " (credit balance: openrouter.ai/settings/credits)")
    except Exception:  # noqa: BLE001  informational only
        pass


def _error_body(res, *secrets: str) -> str:
    """The API's own error text (pretty JSON when possible), with any key value masked, for the reader."""
    try:
        text = json.dumps(res.json(), indent=2, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        text = getattr(res, "text", "") or ""
    for sec in secrets:
        if sec:
            text = text.replace(sec, "***")
    return "\n".join("        " + ln for ln in text[:3000].splitlines())


def run(s, store, live: bool = False, strict: bool = False, session=None) -> Report:
    print("GLIVARAO doctor (key values are never shown)\n")
    r = check_settings(s, store)
    from .studio.pause import status as pause_status

    st = pause_status(s)
    if st:
        r.row("warn", "PRODUCTION", f"PAUSED since {st.get('since')} ({st.get('reason')}); resume: python -m glivarao resume")
    if live and st:
        print("\nLIVE TESTS skipped: production is paused (no paid calls while paused)")
        live = False
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
