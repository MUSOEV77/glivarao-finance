"""Production benchmark: renders a long video (and optionally Shorts) with the real v2 pipeline and measures
wall time per stage, CPU seconds, peak RAM across the whole process tree (python + workers + ffmpeg), and disk.

Run on the VPS to verify capacity:
    .venv/bin/python deploy/benchmark.py --minutes 16.5 --workers 1 --label vps
Note: the long script comes from the offline generator purely to get realistic LENGTH (2,400+ words); its
content is filler. Rendering cost depends on length and scene count, not on wording.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import shutil
import sys
import threading
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _tree_rss_mb(root: int) -> float:
    kids: dict[int, list[int]] = {}
    rss: dict[int, int] = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat") as fh:
                parts = fh.read().rsplit(")", 1)[1].split()
            ppid, pages = int(parts[1]), int(parts[21])
        except (OSError, IndexError, ValueError):
            continue
        kids.setdefault(ppid, []).append(int(d))
        rss[int(d)] = pages
    total, stack = 0, [root]
    while stack:
        p = stack.pop()
        total += rss.get(p, 0)
        stack += kids.get(p, [])
    return total * os.sysconf("SC_PAGE_SIZE") / 1e6


class Monitor(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.peak, self.stop = 0.0, False

    def run(self):
        while not self.stop:
            self.peak = max(self.peak, _tree_rss_mb(os.getpid()))
            time.sleep(0.5)


def cpu_seconds() -> float:
    s, c = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return s.ru_utime + s.ru_stime + c.ru_utime + c.ru_stime


def du_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=16.5)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--shorts", type=int, default=0)
    ap.add_argument("--max-scenes", type=int, default=None, help="truncate long script (quick throughput test)")
    ap.add_argument("--label", default="bench")
    ap.add_argument("--out", default="output/bench")
    args = ap.parse_args()

    from glivarao.config import Settings
    from glivarao.render.animated import render_animated
    from glivarao.render.thumbnail_v3 import make_thumbnail_v3
    from glivarao.render.video import fit_to_size, probe
    from glivarao.scriptgen.offline import generate_offline

    settings = Settings(mode="production")
    root = Path(args.out) / args.label
    shutil.rmtree(root, ignore_errors=True)
    mon = Monitor()
    mon.start()
    results = {"label": args.label, "cpus_visible": len(os.sched_getaffinity(0)), "workers": args.workers,
               "stages": {}}

    def stage(name, fn):
        t0, c0 = time.time(), cpu_seconds()
        out = fn()
        results["stages"][name] = {"wall_s": round(time.time() - t0, 1), "cpu_s": round(cpu_seconds() - c0, 1),
                                   "peak_rss_mb_so_far": round(mon.peak)}
        return out

    long = generate_offline("How credit card interest really works", "long", minutes=args.minutes)
    if args.max_scenes:
        long = long.model_copy(update={"scenes": long.scenes[: args.max_scenes]})
    results["long_words"], results["long_scenes"] = long.word_count, len(long.scenes)
    res = stage("long_render", lambda: render_animated(long, root / "long", settings, workers=args.workers))
    info = probe(res.video)
    results["long_video_s"] = round(info["duration"], 1)
    stage("long_thumbnail", lambda: make_thumbnail_v3(long, root / "long" / "thumbnail.jpg"))
    lim = 50 * 1024 * 1024 - 512 * 1024
    if res.video.stat().st_size > lim:
        stage("telegram_review_copy", lambda: fit_to_size(res.video, root / "long" / "review_copy.mp4", lim))
    results["long_files_mb"] = {p.name: round(p.stat().st_size / 1e6, 1) for p in (root / "long").iterdir()
                                if p.is_file()}

    if args.shorts:
        from glivarao.content.brief import build_brief
        from glivarao.content.writer import write_shorts_free

        card = {"key": "credit_card", "topic": "Credit cards, interest and fees", "category": "Credit and Debt",
                "market": "both", "score": 90, "confidence": "medium", "why": [], "viewer_questions": [],
                "documented_problems": []}
        for k, sh in enumerate(write_shorts_free(build_brief(card, date.today()))[: args.shorts]):
            r = stage(f"short{k + 1}_render", lambda sh=sh, k=k: render_animated(sh, root / f"short{k + 1}",
                                                                              settings, workers=args.workers))
            results[f"short{k + 1}_video_s"] = round(r.duration, 1)
    mon.stop = True
    results["peak_rss_mb"] = round(mon.peak)
    results["total_wall_s"] = round(sum(s["wall_s"] for s in results["stages"].values()), 1)
    results["total_cpu_s"] = round(sum(s["cpu_s"] for s in results["stages"].values()), 1)
    results["disk_mb_total"] = round(du_mb(root), 1)
    (root / "benchmark.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
