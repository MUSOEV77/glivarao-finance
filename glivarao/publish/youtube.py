"""YouTube Data API v3 upload + YouTube Analytics API v2 reporting.

AUTOMATIC UPLOADING, PUBLISHING AND SCHEDULING ARE DISABLED BY DESIGN.

Safety gates (all must pass before any upload):
  1. job.status == APPROVED (only reachable through a human decision),
  2. YOUTUBE_PUBLISH_ENABLED=true (default false),
  3. an OAuth token created interactively by the channel owner (`python -m glivarao youtube-auth`),
  4. `operator_confirmation` equal to the job id, which the CLI only collects by a human typing it
     into an interactive terminal (no flag, env var or cron job can supply it).
Uploads are ALWAYS `private` and never carry `publishAt`, so YouTube can neither show nor schedule
them. Making a video public is done by the owner in YouTube Studio.
"""
from __future__ import annotations

import json

import logging
from datetime import date, timedelta
from pathlib import Path

from ..config import Settings
from ..models import Job, JobStatus, Script
from ..storage import JobStore

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",      # captions + thumbnails
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


class PublishBlocked(RuntimeError):
    pass


def authorize(settings: Settings) -> None:
    """Interactive one-time OAuth consent. Stores a refresh token at YOUTUBE_TOKEN_FILE."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not settings.youtube_client_secrets_file.exists():
        raise PublishBlocked(f"OAuth client file not found: {settings.youtube_client_secrets_file}")
    flow = InstalledAppFlow.from_client_secrets_file(str(settings.youtube_client_secrets_file), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=False)
    settings.youtube_token_file.parent.mkdir(parents=True, exist_ok=True)
    settings.youtube_token_file.write_text(creds.to_json())
    settings.youtube_token_file.chmod(0o600)


def _credentials(settings: Settings):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if not settings.youtube_token_file.exists():
        raise PublishBlocked("No YouTube token. Run: python -m glivarao youtube-auth")
    creds = Credentials.from_authorized_user_file(str(settings.youtube_token_file), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        settings.youtube_token_file.write_text(creds.to_json())
    return creds


UPLOAD_PRIVACY = "private"  # hard-coded on purpose; no setting or flag changes it


def build_metadata(script: Script, settings: Settings, altered_content: bool = True) -> dict:
    title = script.title
    description = script.description
    tags = list(dict.fromkeys(script.tags))[:30]
    if script.format == "short":
        if "#shorts" not in title.lower() and len(title) <= 92:
            title = f"{title} #Shorts"
        description = f"{description}\n\n#Shorts"
    return {
        "snippet": {"title": title[:100], "description": description[:5000], "tags": tags,
                    "categoryId": settings.youtube_category_id, "defaultLanguage": "en-US",
                    "defaultAudioLanguage": "en-US"},
        "status": {"privacyStatus": UPLOAD_PRIVACY,  # never public, never scheduled (no publishAt)
                   "selfDeclaredMadeForKids": False,
                   # YouTube "altered or synthetic content" flag, decided per video by studio/disclosure.py
                   # (metadata.json "youtube_altered_content"); True unless explicitly known to be False
                   "containsSyntheticMedia": bool(altered_content),
                   "embeddable": True},
    }


def check_gates(job: Job, settings: Settings, operator_confirmation: str = "") -> None:
    if operator_confirmation != job.id:
        raise PublishBlocked("Manual operator confirmation missing: uploads are manual-only")
    if job.status != JobStatus.APPROVED:
        raise PublishBlocked(f"Job {job.id} is '{job.status.value}', not 'approved'")
    if not settings.youtube_publish_enabled:
        raise PublishBlocked("YOUTUBE_PUBLISH_ENABLED is not 'true' (kill-switch engaged)")
    if not job.video_path or not Path(job.video_path).exists():
        raise PublishBlocked("Rendered video file is missing")


def _altered_flag(job: Job) -> bool:
    """The per-video disclosure decision saved at render time; defaults to disclosing when unknown."""
    try:
        meta = json.loads((Path(job.video_path).parent / "metadata.json").read_text())
        return bool(meta.get("youtube_altered_content", True))
    except (OSError, ValueError, TypeError):
        return True


def upload(job: Job, script: Script, store: JobStore, settings: Settings, operator_confirmation: str = "",
           youtube=None) -> str:
    check_gates(job, settings, operator_confirmation)
    from googleapiclient.http import MediaFileUpload

    if youtube is None:
        from googleapiclient.discovery import build

        youtube = build("youtube", "v3", credentials=_credentials(settings), cache_discovery=False)
    body = build_metadata(script, settings, altered_content=_altered_flag(job))
    if body["status"]["privacyStatus"] != "private" or "publishAt" in body["status"]:
        raise PublishBlocked("Refusing upload: metadata is not private-only")
    media = MediaFileUpload(job.video_path, mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info("upload %d%%", int(status.progress() * 100))
    video_id = response["id"]

    if job.format == "long" and job.thumbnail_path:
        youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(job.thumbnail_path)).execute()
    if job.subtitles_path:
        youtube.captions().insert(
            part="snippet",
            body={"snippet": {"videoId": video_id, "language": "en", "name": "English", "isDraft": False}},
            media_body=MediaFileUpload(job.subtitles_path, mimetype="application/octet-stream"),
        ).execute()
    job.youtube_video_id = video_id
    store.transition(job, JobStatus.PUBLISHED, f"youtube {video_id} (private, manual upload)")
    return video_id


def fetch_analytics(store: JobStore, settings: Settings, days: int = 28, analytics=None) -> list[dict]:
    """Per-video metrics for published jobs, stored in the analytics table."""
    if analytics is None:
        from googleapiclient.discovery import build

        analytics = build("youtubeAnalytics", "v2", credentials=_credentials(settings), cache_discovery=False)
    end = date.today()
    start = end - timedelta(days=days)
    metrics = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,subscribersGained"
    rows = []
    for job in store.list(JobStatus.PUBLISHED, limit=500):
        if not job.youtube_video_id:
            continue
        res = analytics.reports().query(ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
                                         metrics=metrics, filters=f"video=={job.youtube_video_id}").execute()
        names = [h["name"] for h in res.get("columnHeaders", [])]
        values = (res.get("rows") or [[0] * len(names)])[0]
        row = {"job_id": job.id, "video_id": job.youtube_video_id, "format": job.format, **dict(zip(names, values))}
        store.put_analytics(job.youtube_video_id, end.isoformat(), row)
        rows.append(row)
    return rows
