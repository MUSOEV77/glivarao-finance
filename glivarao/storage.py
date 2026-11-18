"""SQLite job store with an explicit, enforced status machine."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import Job, JobStatus

S = JobStatus
ALLOWED = {
    S.PLANNED: {S.SCRIPTED, S.FAILED},
    S.SCRIPTED: {S.RENDERED, S.REJECTED_COMPLIANCE, S.FAILED},
    S.REJECTED_COMPLIANCE: {S.SCRIPTED},
    S.RENDERED: {S.PENDING_APPROVAL, S.FAILED},
    S.PENDING_APPROVAL: {S.APPROVED, S.REJECTED},
    S.APPROVED: {S.PUBLISHED, S.FAILED},
    S.REJECTED: set(),
    S.PUBLISHED: set(),
    S.FAILED: {S.PLANNED},
}


class InvalidTransition(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobStore:
    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (job_id TEXT, at TEXT, from_status TEXT,
                to_status TEXT, detail TEXT);
            CREATE TABLE IF NOT EXISTS analytics (video_id TEXT, day TEXT, metrics TEXT,
                PRIMARY KEY (video_id, day));
            CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
            """
        )
        self.conn.commit()

    # -- jobs ---------------------------------------------------------------
    def create(self, fmt: str, topic: str) -> Job:
        ts = _now()
        job = Job(id=f"{datetime.now().strftime('%Y%m%d')}-{fmt}-{uuid.uuid4().hex[:6]}",
                  format=fmt, topic=topic, created_at=ts, updated_at=ts)
        self.conn.execute("INSERT INTO jobs VALUES (?,?,?,?)",
                          (job.id, job.model_dump_json(), job.status.value, ts))
        self.conn.commit()
        return job

    def get(self, job_id: str) -> Job:
        row = self.conn.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise KeyError(job_id)
        return Job.model_validate_json(row["data"])

    def save(self, job: Job) -> None:
        job.updated_at = _now()
        self.conn.execute("UPDATE jobs SET data=?, status=? WHERE id=?",
                          (job.model_dump_json(), job.status.value, job.id))
        self.conn.commit()

    def transition(self, job: Job, to: JobStatus, detail: str = "") -> Job:
        if to not in ALLOWED[job.status]:
            raise InvalidTransition(f"{job.id}: {job.status.value} -> {to.value} not allowed")
        self.conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                          (job.id, _now(), job.status.value, to.value, detail))
        job.status = to
        self.save(job)
        return job

    def list(self, status: Optional[JobStatus] = None, limit: int = 50) -> list[Job]:
        if status:
            rows = self.conn.execute("SELECT data FROM jobs WHERE status=? ORDER BY created_at DESC LIMIT ?",
                                     (status.value, limit)).fetchall()
        else:
            rows = self.conn.execute("SELECT data FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [Job.model_validate_json(r["data"]) for r in rows]

    def events(self, job_id: str) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM events WHERE job_id=? ORDER BY at", (job_id,)).fetchall()
        return [dict(r) for r in rows]

    def recent_topics(self, limit: int = 120) -> list[str]:
        rows = self.conn.execute("SELECT data FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(r["data"])["topic"] for r in rows]

    # -- misc ---------------------------------------------------------------
    def put_analytics(self, video_id: str, day: str, metrics: dict) -> None:
        self.conn.execute("INSERT OR REPLACE INTO analytics VALUES (?,?,?)", (video_id, day, json.dumps(metrics)))
        self.conn.commit()

    def kv_get(self, k: str, default: str = "") -> str:
        row = self.conn.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return row["v"] if row else default

    def kv_set(self, k: str, v: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (k, v))
        self.conn.commit()
