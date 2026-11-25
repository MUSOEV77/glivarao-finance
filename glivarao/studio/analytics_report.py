"""YouTube analytics without a computer:
* `youtube-auth --phone`: Google's device sign-in. The bot sends you a short code and a link; you open the link on
  your phone, enter the code and allow read-only access. Needs an OAuth client of type "TVs and Limited Input
  devices" (its JSON at YOUTUBE_CLIENT_SECRETS_FILE).
* `analytics-pull` (09:00 daily): views, CTR, average view % and 30-second retention for every video whose YouTube
  link you saved; on Mondays a Telegram report with the best topics, hooks and thumbnails.
Read-only: nothing is uploaded or changed on YouTube."""
from __future__ import annotations

import json
import time
from datetime import date, timedelta

READ_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly",
               "https://www.googleapis.com/auth/yt-analytics.readonly"]
DEVICE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _client_ids(settings) -> tuple[str, str]:
    d = json.loads(settings.youtube_client_secrets_file.read_text())
    c = d.get("installed") or d.get("web") or d
    return c["client_id"], c.get("client_secret", "")


def device_auth(settings, notify, session=None, sleep=time.sleep, max_wait: int = 900) -> None:
    """Phone-only sign-in (OAuth device flow). notify(text) sends the link + code (Telegram)."""
    import requests

    s = session or requests.Session()
    cid, secret = _client_ids(settings)
    r = s.post(DEVICE_URL, data={"client_id": cid, "scope": " ".join(READ_SCOPES)}, timeout=30).json()
    if "device_code" not in r:
        raise RuntimeError(f"Google refused the device sign-in: {r.get('error_description') or r.get('error')}")
    notify(f"🔐 YouTube analytics sign-in: open {r['verification_url']} on your phone and enter the code "
           f"{r['user_code']} (valid {r.get('expires_in', 1800) // 60} min). Read-only access.")
    waited, step = 0, int(r.get("interval", 5))
    while waited < max_wait:
        sleep(step)
        waited += step
        t = s.post(TOKEN_URL, data={"client_id": cid, "client_secret": secret, "device_code": r["device_code"],
                                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}, timeout=30).json()
        if "access_token" in t:
            tok = {"token": t["access_token"], "refresh_token": t.get("refresh_token"), "token_uri": TOKEN_URL,
                   "client_id": cid, "client_secret": secret, "scopes": READ_SCOPES}
            settings.youtube_token_file.parent.mkdir(parents=True, exist_ok=True)
            settings.youtube_token_file.write_text(json.dumps(tok))
            settings.youtube_token_file.chmod(0o600)
            notify("✅ YouTube analytics connected (read-only).")
            return
        if t.get("error") == "slow_down":
            step += 5
        elif t.get("error") not in ("authorization_pending", None):
            raise RuntimeError(f"sign-in failed: {t.get('error')}")
    raise RuntimeError("sign-in timed out: run youtube-auth --phone again")


def _analytics(settings):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(settings.youtube_token_file))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)


def _q(api, vid, metrics, start, end, dims=None):
    kw = dict(ids="channel==MINE", startDate=start, endDate=end, metrics=metrics, filters=f"video=={vid}")
    if dims:
        kw["dimensions"] = dims
    res = api.reports().query(**kw).execute()
    names = [h["name"] for h in res.get("columnHeaders", [])]
    return [dict(zip(names, row)) for row in (res.get("rows") or [])]


def pull(settings, store, api=None, day: date | None = None) -> dict:
    """Metrics for every linked video (episodes with a YouTube link), stored in kv 'analytics_daily'."""
    from . import series as S
    from .batch import video_id

    api = api or _analytics(settings)
    day = day or date.today()
    start, end = (day - timedelta(days=90)).isoformat(), day.isoformat()
    out = {}
    for e in S.episodes(store):
        vid = video_id(e.get("url", ""))
        if not vid:
            continue
        row = {}
        for m in ("views,averageViewPercentage", "videoThumbnailImpressions,videoThumbnailImpressionsClickRate"):
            try:
                r = _q(api, vid, m, start, end)
                row.update(r[0] if r else {})
            except Exception:  # noqa: BLE001  a metric YouTube doesn't give for this video: skip it
                pass
        r30 = None
        try:
            dur = float(store.get(e["job"]).duration_sec or 0)
            curve = _q(api, vid, "audienceWatchRatio", start, end, "elapsedVideoTimeRatio")
            if dur > 0 and curve:
                x = min(1.0, 30.0 / dur)
                r30 = min(curve, key=lambda c: abs(float(c["elapsedVideoTimeRatio"]) - x))["audienceWatchRatio"]
        except Exception:  # noqa: BLE001
            pass
        out[e["job"]] = {"date": end, "format": e.get("format"), "series": e.get("series"),
                         "views": float(row.get("views", 0) or 0), "avp": float(row.get("averageViewPercentage", 0)
                                                                                  or 0),
                         "ctr": float(row.get("videoThumbnailImpressionsClickRate", 0) or 0),
                         "r30": float(r30) if r30 is not None else None}
    store.kv_set("analytics_daily", json.dumps(out))
    return out


def _fingerprints(store) -> dict:
    fp = {}
    for fmt in ("long", "short"):
        for h in json.loads(store.kv_get(f"variety_history:{fmt}", "[]")):
            if h.get("job"):
                fp[h["job"]] = h
    return fp


def _best(rows: list[tuple[str, dict]], key: str, n: int = 3) -> list[str]:
    groups: dict[str, list[dict]] = {}
    for g, m in rows:
        if g:
            groups.setdefault(g, []).append(m)
    ranked = sorted(groups.items(), key=lambda kv: -sum(x[key] or 0 for x in kv[1]) / len(kv[1]))
    return [f"{g} ({sum(x[key] or 0 for x in ms) / len(ms):.1f})" for g, ms in ranked[:n]]


def weekly_text(store, data: dict) -> str:
    fp = _fingerprints(store)
    rows = list(data.items())
    lines = ["📈 GLIVARAO weekly analytics (linked videos, last 90 days)",
             f"Videos measured: {len(rows)}"]
    if not rows:
        return "\n".join(lines + ["No linked videos yet: reply to each upload pack with its YouTube link."])
    lines.append("Best topics by views: " + ", ".join(_best([(m.get("series"), m) for _, m in rows], "views")))
    lines.append("Best hooks by 30-s retention: " + ", ".join(
        _best([(fp.get(j, {}).get("hook_type"), {**m, "r30": m["r30"] or 0}) for j, m in rows], "r30")))
    lines.append("Best thumbnails by CTR (long): " + ", ".join(
        _best([(fp.get(j, {}).get("thumb_layout"), m) for j, m in rows if m.get("format") == "long"], "ctr")))
    lines.append("Story vs other long formats (avg views): " + ", ".join(
        _best([("story" if fp.get(j, {}).get("structure") == "money_story" else "explainer/other", m)
               for j, m in rows if m.get("format") == "long"], "views", 2)))
    return "\n".join(lines)


__all__ = ["device_auth", "pull", "weekly_text", "READ_SCOPES"]
