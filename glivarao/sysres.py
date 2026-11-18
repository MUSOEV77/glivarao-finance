"""Host resource checks so a render never runs the machine out of memory.

Measured (docs/CAPACITY_AUDIT.md): each scene worker needs roughly 0.5-1 GB on top of the main process, so the
worker count is capped by *available* RAM, not by CPU count. Overrides: RENDER_WORKERS (fixed count) and
RENDER_MB_PER_WORKER (budget per worker, default 1000)."""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

MB_PER_WORKER = 1000
RESERVE_MB = 400  # main process, ffmpeg mux, OS


def available_mb() -> int | None:
    """MemAvailable from /proc/meminfo (Linux), or None if unknown."""
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def safe_workers(requested: int | None = None) -> int:
    """Worker count that fits both CPUs and free RAM; never below 1."""
    env = os.environ.get("RENDER_WORKERS", "").strip()
    if requested is None and env.isdigit() and int(env) > 0:
        requested = int(env)
    cpus = os.cpu_count() or 2
    want = requested or cpus
    per = int(os.environ.get("RENDER_MB_PER_WORKER", MB_PER_WORKER) or MB_PER_WORKER)
    avail = available_mb()
    if avail is None:
        return max(1, min(want, cpus))
    by_ram = max(1, (avail - RESERVE_MB) // max(1, per))
    n = max(1, min(want, cpus, by_ram))
    if n < want:
        log.info("render workers capped at %d (requested %d, %d CPUs, %d MB available)", n, want, cpus, avail)
    return n


def free_disk_mb(path: Path) -> int:
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free // (1024 * 1024)


def check_disk(path: Path, need_mb: int = 1500) -> None:
    """Fail early (with a clear message) instead of mid-render when the disk is nearly full."""
    free = free_disk_mb(path)
    if free < need_mb:
        raise RuntimeError(f"only {free} MB free at {path}; need at least {need_mb} MB for a daily render "
                           "(prune old output/ or backups/)")
