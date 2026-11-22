"""Affiliate programs (the creator's list). Every program starts as a PLACEHOLDER: nothing appears in a
description until you're approved and add your link in Telegram:

    /affiliate rocketmoney https://your-link     (approved: used from the next upload pack)
    /affiliate rocketmoney clear                  (back to placeholder)
    /affiliate                                    (status of every program)

Rules: 1-2 links per LONG video (topic match first, then pillar), none in Shorts; always placed right above the
affiliate disclosure. YNAB is listed for later and is off until you add a link.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Program:
    key: str
    name: str
    pitch: str
    pillars: frozenset[str] = field(default_factory=frozenset)
    topics: frozenset[str] = field(default_factory=frozenset)


PROGRAMS: dict[str, Program] = {p.key: p for p in [
    Program("rocketmoney", "Rocket Money", "find and cancel forgotten subscriptions, track bills",
            frozenset({"budget", "debt"}), frozenset({"cost_of_living", "bank_fees", "budgeting", "spending_psych"})),
    Program("monarch", "Monarch Money", "budget and debt-payoff tracking",
            frozenset({"budget", "debt"}), frozenset({"budgeting", "debt_payoff", "emergency_fund", "credit_card",
                                                      "money_relationships"})),
    Program("wise", "Wise", "low-cost international money transfers", frozenset(),
            frozenset({"money_transfer", "currency_exchange"})),
    Program("rocketdollar", "Rocket Dollar", "self-directed IRA and Solo 401(k)", frozenset({"retire"}),
            frozenset({"ira_roth", "retirement_401k", "retirement_planning"})),
    Program("freetaxusa", "FreeTaxUSA", "low-cost tax filing", frozenset({"taxes"}),
            frozenset({"income_tax", "tax_filing", "tax_refund", "tax_credits", "side_income_tax"})),
    Program("turbotax", "TurboTax", "guided tax filing", frozenset({"taxes"}),
            frozenset({"income_tax", "tax_filing", "tax_refund", "side_income_tax"})),
    Program("ynab", "YNAB", "zero-based budgeting (later)", frozenset({"budget"}), frozenset({"budgeting"})),
]}
MAX_PER_LONG = 2

# Product CATEGORIES for the closing "What to do" section. Every video's description gets a placeholder line
# "[AFFILIATE: <category>]" (no real links yet); you replace it with your link when uploading.
CATEGORIES = ("budgeting app", "high-yield savings", "credit monitoring", "debt payoff", "tax software", "insurance")
CATEGORY_FOR_TOPIC = {
    **dict.fromkeys(("credit_card", "debt_payoff", "household_debt", "student_loan", "personal_loan",
                     "debt_collection", "bankruptcy"), "debt payoff"),
    **dict.fromkeys(("credit_score", "credit_report", "medical_debt", "identity_theft", "scams"), "credit monitoring"),
    **dict.fromkeys(("budgeting", "cost_of_living", "spending_psych", "money_relationships", "paycheck", "bnpl",
                     "auto_loan", "bank_fees", "money_mistakes"), "budgeting app"),
    **dict.fromkeys(("hysa", "emergency_fund", "cd_gic", "fed_rates", "recession", "us_banks", "deposit_insurance",
                     "national_debt", "treasury_market", "us_housing", "financial_crisis", "mortgage", "rent_vs_buy", "us_stock_market",
                     "inflation_personal", "retirement_401k", "ira_roth", "bank_account"), "high-yield savings"),
    **dict.fromkeys(("income_tax", "tax_filing", "tax_refund", "tax_credits", "tax_withholding", "side_income_tax"),
                    "tax software"),
    **dict.fromkeys(("aca_marketplace", "insurance"), "insurance"),
}


def category_for(topic_key: str, card: dict | None = None) -> str:
    """The product category that fits this video's "What to do" section (launch list entries set their own)."""
    cat = (card or {}).get("affiliate_category") or CATEGORY_FOR_TOPIC.get(topic_key, "budgeting app")
    return cat if cat in CATEGORIES else "budgeting app"


def placeholder(category: str) -> str:
    return f"[AFFILIATE: {category}]"


def add_placeholder(description: str, category: str) -> str:
    """Put the category placeholder on its own line (once), ahead of the disclosure."""
    tag = placeholder(category)
    if tag in description:
        return description
    return description.rstrip() + f"\n\nRecommended for the \"What to do\" steps: {tag}\n"


def links(store) -> dict[str, str]:
    return json.loads(store.kv_get("affiliate_programs", "{}"))


def set_link(store, key: str, url: str | None) -> None:
    cur = links(store)
    if url:
        cur[key] = url
    else:
        cur.pop(key, None)
    store.kv_set("affiliate_programs", json.dumps(cur))


def candidates(topic_key: str, pillar: str | None) -> list[Program]:
    """Programs that fit this video, best match first (topic match, then pillar)."""
    by_topic = [p for p in PROGRAMS.values() if topic_key in p.topics]
    by_pillar = [p for p in PROGRAMS.values() if pillar and pillar in p.pillars and p not in by_topic]
    return by_topic + by_pillar


def for_video(store, topic_key: str, pillar: str | None, fmt: str) -> tuple[list[tuple[str, str]], list[str]]:
    """([(name, url)] to put in the description, [placeholder names]). Shorts get none."""
    if fmt != "long":
        return [], []
    approved, pending = [], []
    have = links(store)
    for p in candidates(topic_key, pillar):
        if p.key in have:
            if len(approved) < MAX_PER_LONG:
                approved.append((p.name, have[p.key]))
        elif p.key != "ynab":
            pending.append(p.name)
    return approved, pending[:MAX_PER_LONG]


def status_text(store) -> str:
    have = links(store)
    lines = ["💵 Affiliate programs (1-2 per long video, none in Shorts)"]
    for p in PROGRAMS.values():
        state = "✅ link set" if p.key in have else ("⏳ later" if p.key == "ynab" else "⏳ placeholder (not approved yet)")
        lines.append(f"• {p.name} [{p.key}] — {p.pitch}: {state}")
    lines += ["", "When you're approved:  /affiliate <program> <https link>", "Example:  /affiliate rocketmoney "
              "https://your-link", "Back to placeholder:  /affiliate <program> clear"]
    return "\n".join(lines)


__all__ = ["PROGRAMS", "for_video", "set_link", "links", "status_text", "candidates", "MAX_PER_LONG"]
