"""systemd units: a timer may never start its service more often than the service's start limit allows
(Part C bug: the 15-minute daily timer vs StartLimitBurst=3 per 6 h -> "start-limit-hit" every check).
Parses every deploy/systemd/*.timer and its .service; no systemd needed."""
import math
import re
from pathlib import Path

import pytest

UNITS = Path(__file__).resolve().parents[1] / "deploy" / "systemd"


def _ini(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "[")) and "=" in line:
            k, v = line.split("=", 1)
            out.setdefault(k.strip(), []).append(v.strip())
    return out


def seconds(v: str) -> float:
    """systemd time span: '6h', '1h 30min', '15min', '90s', '0', '2min'."""
    v = v.strip()
    if re.fullmatch(r"\d+(\.\d+)?", v):
        return float(v)
    total = 0.0
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(d|h|min|m|s|sec)", v):
        total += float(num) * {"d": 86400, "h": 3600, "min": 60, "m": 60, "s": 1, "sec": 1}[unit]
    return total


def _field(spec: str, lo: int, hi: int) -> list[int]:
    vals = []
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, st = part.split("/")
            step = int(st)
            if ".." not in part and part != "*":
                part = f"{part}..{hi}"
        if part == "*":
            a, b = lo, hi
        elif ".." in part:
            a, b = (int(x) for x in part.split(".."))
        else:
            a = b = int(part)
        vals += list(range(a, b + 1, step))
    return vals


def calendar_minutes(spec: str) -> list[int]:
    """Minutes of the day an OnCalendar fires ('*-*-* 09..21:00/15:00 Asia/Tashkent'). A weekday prefix is
    treated as every day (stricter)."""
    clock = next(t for t in spec.split() if ":" in t)
    hh, mm = clock.split(":")[:2]
    return sorted(h * 60 + m for h in _field(hh, 0, 23) for m in _field(mm, 0, 59))


def max_starts_in(window_s: float, timer: dict) -> int:
    """Worst-case timer starts inside any window of `window_s` seconds."""
    if "OnUnitActiveSec" in timer:
        return math.floor(window_s / seconds(timer["OnUnitActiveSec"][0])) + 1
    mins = []
    for spec in timer.get("OnCalendar", []):
        mins += calendar_minutes(spec)
    mins = sorted(set(mins))
    ts = mins + [m + 1440 for m in mins]        # two days, so windows across midnight count
    w = window_s / 60
    return max(sum(1 for t in ts if s <= t < s + w) for s in ts) if ts else 0


def pairs():
    for t in sorted(UNITS.glob("*.timer")):
        svc = UNITS / (_ini(t).get("Unit", [t.stem + ".service"])[0])
        yield t.name, _ini(t), _ini(svc)


@pytest.mark.parametrize("name,timer,svc", list(pairs()), ids=[p[0] for p in pairs()])
def test_timer_never_exceeds_the_service_start_limit(name, timer, svc):
    window = seconds(svc.get("StartLimitIntervalSec", ["10s"])[0])       # systemd defaults: 10 s, burst 5
    burst = int(svc.get("StartLimitBurst", ["5"])[0])
    if window == 0:                                                       # start limit disabled
        return
    starts = max_starts_in(window, timer)
    restart = svc.get("Restart", ["no"])[0]
    if restart not in ("no", ""):                                         # one failure's restart must fit too
        starts += 1
    assert starts <= burst, (f"{name}: up to {starts} starts in {svc['StartLimitIntervalSec'][0]} "
                             f"but StartLimitBurst={burst} -> start-limit-hit")


def test_daily_checks_every_15_minutes_without_systemd_restarts():
    timer = _ini(UNITS / "glivarao-daily.timer")
    svc = _ini(UNITS / "glivarao-daily.service")
    assert max_starts_in(3600, timer) == 4
    assert "Restart" not in svc                     # the app backs off itself; a restart would add starts
    assert int(svc["StartLimitBurst"][0]) >= 4 and seconds(svc["StartLimitIntervalSec"][0]) >= 3600
    assert "--scheduled" in svc["ExecStart"][0]


def test_the_old_units_would_have_failed():
    old_svc = {"StartLimitIntervalSec": ["6h"], "StartLimitBurst": ["3"], "Restart": ["on-failure"]}
    timer = {"OnCalendar": ["*-*-* 09..21:00/15:00 Asia/Tashkent"]}
    assert max_starts_in(seconds(old_svc["StartLimitIntervalSec"][0]), timer) + 1 > 3


def test_parser():
    assert seconds("6h") == 21600 and seconds("15min") == 900 and seconds("1h 30min") == 5400
    assert calendar_minutes("*-*-* 03:40:00 Asia/Tashkent") == [220]
    assert len(calendar_minutes("*-*-* 09..21:00/15:00 Asia/Tashkent")) == 13 * 4
    assert max_starts_in(3600, {"OnUnitActiveSec": ["5min"]}) == 13
