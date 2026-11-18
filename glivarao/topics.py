"""Topic bank and selection. Topics are evergreen US personal-finance explainers.

Selection avoids anything used in the recent history so the channel does not repeat itself.
Edit config/topics.yaml to extend the bank without touching code.
"""
from __future__ import annotations

import random
from pathlib import Path

import yaml

DEFAULT_TOPICS = [
    "How compound interest really works",
    "Roth IRA vs Traditional IRA explained",
    "What a 401(k) employer match is worth",
    "How credit scores are calculated in the US",
    "Why inflation shrinks your savings",
    "Index funds vs picking individual stocks",
    "How to build an emergency fund",
    "The true cost of minimum credit card payments",
    "How the Federal Reserve sets interest rates",
    "Renting vs buying a home: the real math",
    "How US income tax brackets actually work",
    "What a high-yield savings account is",
    "Dollar-cost averaging explained",
    "How student loan interest works",
    "What an HSA is and why it is triple tax-advantaged",
    "Treasury bills, notes and bonds explained",
    "How mortgages and amortization work",
    "The 50/30/20 budgeting rule",
    "What the stock market actually is",
    "How Social Security benefits are calculated",
    "Expense ratios: the small fee that costs a fortune",
    "What a recession is and how it is measured",
    "Car loans: how to avoid overpaying",
    "Why diversification reduces risk",
]


def load_topics(path: Path = Path("config/topics.yaml")) -> list[str]:
    if path.exists():
        data = yaml.safe_load(path.read_text()) or {}
        topics = data.get("topics") or []
        if topics:
            return [str(t) for t in topics]
    return DEFAULT_TOPICS


def pick_topic(recent: list[str], seed: int | None = None, topics: list[str] | None = None) -> str:
    topics = topics or load_topics()
    recent_lower = {t.lower() for t in recent}
    fresh = [t for t in topics if t.lower() not in recent_lower]
    pool = fresh or topics  # bank exhausted -> allow repeats (better: extend the bank)
    return random.Random(seed).choice(pool)
