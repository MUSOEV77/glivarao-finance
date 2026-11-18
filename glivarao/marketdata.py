"""Real US economic data from FRED (Federal Reserve Bank of St. Louis).

Scripts may request a real chart by setting chart.source to "FRED:<SERIES>" with empty values.
`fill_fred_charts` replaces those with yearly data fetched from the API, so on-screen numbers
come from the source rather than from the language model's memory.
"""
from __future__ import annotations

from collections import defaultdict

import requests

from .models import Script

SERIES = {
    # id: (title, unit, transform)
    "CPIAUCSL": ("US inflation (CPI, year over year)", "%", "yoy"),
    "FEDFUNDS": ("Federal funds rate (yearly average)", "%", "level"),
    "MORTGAGE30US": ("30-year fixed mortgage rate (yearly average)", "%", "level"),
    "UNRATE": ("US unemployment rate (yearly average)", "%", "level"),
    "DGS10": ("10-year Treasury yield (yearly average)", "%", "level"),
}


class MarketDataError(RuntimeError):
    pass


def fetch_yearly(series_id: str, api_key: str, start_year: int = 2000, session=None) -> tuple[list[str], list[float]]:
    if series_id not in SERIES:
        raise MarketDataError(f"Unsupported FRED series {series_id}")
    if not api_key:
        raise MarketDataError("FRED_API_KEY is not set")
    http = session or requests
    try:
        resp = http.get("https://api.stlouisfed.org/fred/series/observations",
                        params={"series_id": series_id, "api_key": api_key, "file_type": "json",
                                "observation_start": f"{start_year - 1}-01-01"}, timeout=30)
    except requests.RequestException as exc:
        # FRED only accepts the key as a query parameter; drop the URL from the error message
        raise MarketDataError(f"FRED request failed: {type(exc).__name__}") from None
    if resp.status_code != 200:
        raise MarketDataError(f"FRED HTTP {resp.status_code}")
    by_year: dict[int, list[float]] = defaultdict(list)
    for obs in resp.json().get("observations", []):
        if obs["value"] not in (".", ""):
            by_year[int(obs["date"][:4])].append(float(obs["value"]))
    years = sorted(y for y, v in by_year.items() if len(v) >= 1)
    avg = {y: sum(by_year[y]) / len(by_year[y]) for y in years}
    if SERIES[series_id][2] == "yoy":
        pts = [(y, (avg[y] / avg[y - 1] - 1) * 100) for y in years if y - 1 in avg and y >= start_year]
    else:
        pts = [(y, avg[y]) for y in years if y >= start_year]
    return [str(y) for y, _ in pts], [round(v, 2) for _, v in pts]


def fill_fred_charts(script: Script, api_key: str, session=None) -> list[str]:
    """Fill FRED-backed charts in place. Returns notes for the reviewer."""
    notes = []
    for scene in script.scenes:
        src = scene.chart.source.strip()
        if not src.upper().startswith("FRED:"):
            continue
        sid = src.split(":", 1)[1].strip().upper()
        labels, values = fetch_yearly(sid, api_key, session=session)
        title, unit, _ = SERIES[sid]
        scene.chart.kind = "line_series"
        scene.chart.labels, scene.chart.values, scene.chart.unit = labels, values, unit
        scene.chart.title = scene.chart.title or title
        scene.chart.source = f"FRED, Federal Reserve Bank of St. Louis ({sid})"
        notes.append(f"{sid}: {labels[0]}-{labels[-1]}, latest {values[-1]}{unit}")
    return notes
