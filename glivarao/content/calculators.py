"""Exact financial calculations used in scripts, charts and thumbnails.

Every number a script quotes must come from research data or from one of these functions, with the inputs
recorded, so a reviewer can re-check it.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Calc:
    name: str
    inputs: dict
    results: dict
    formula: str

    def fact(self, key: str) -> str:
        return f"{self.name}: {key} = {self.results[key]} (inputs: {self.inputs}; {self.formula})"


def minimum_payment_payoff(balance: float, apr: float, principal_pct: float = 0.01, min_floor: float = 25.0) -> Calc:
    """Credit-card payoff paying only the minimum, using a common issuer formula:
    minimum = (principal_pct x balance) + that month's interest, but at least `min_floor`.
    (A flat "2% of balance" minimum can equal the monthly interest at high APRs and never pay the card off.)"""
    b, months, interest, path = balance, 0, 0.0, [balance]
    while b > 0.005 and months < 1200:
        i = b * apr / 12
        pay = min(max(principal_pct * b + i, min_floor), b + i)
        interest += i
        b = b + i - pay
        months += 1
        if months % 12 == 0:
            path.append(round(max(b, 0), 2))
    return Calc("Minimum-payment payoff", {"balance": balance, "apr": apr, "minimum": f"{principal_pct:.0%} of balance "
                                           f"+ interest, at least ${min_floor:.0f}"},
                {"months": months, "years": round(months / 12, 1), "total_interest": round(interest, 2),
                 "total_paid": round(balance + interest, 2), "yearly_balance": path},
                "monthly interest = balance x APR / 12; minimum = 1% of balance + interest (floor applies)")


def fixed_payment_payoff(balance: float, apr: float, payment: float) -> Calc:
    b, months, interest = balance, 0, 0.0
    while b > 0.005 and months < 1200:
        i = b * apr / 12
        pay = min(payment, b + i)
        interest += i
        b = b + i - pay
        months += 1
    return Calc("Fixed-payment payoff", {"balance": balance, "apr": apr, "payment": payment},
                {"months": months, "years": round(months / 12, 1), "total_interest": round(interest, 2)},
                "same monthly payment until paid off")


def amortized_loan(principal: float, apr: float, years: int) -> Calc:
    """Standard fixed-rate amortizing loan (mortgage, auto, student)."""
    n, r = years * 12, apr / 12
    pay = principal * r / (1 - (1 + r) ** -n) if r else principal / n
    total = pay * n
    first_interest = principal * r
    return Calc("Amortized loan", {"principal": principal, "apr": apr, "years": years},
                {"monthly_payment": round(pay, 2), "total_paid": round(total, 2),
                 "total_interest": round(total - principal, 2),
                 "first_payment_interest": round(first_interest, 2),
                 "first_payment_principal": round(pay - first_interest, 2)},
                "payment = P·r / (1 − (1+r)^−n), r = APR/12, n = years×12")


def compound_growth(principal: float, monthly: float, rate: float, years: int) -> Calc:
    b, contrib, path = principal, principal, [principal]
    for m in range(1, years * 12 + 1):
        b = b * (1 + rate / 12) + monthly
        contrib += monthly
        if m % 12 == 0:
            path.append(round(b, 2))
    return Calc("Compound growth (hypothetical rate)", {"principal": principal, "monthly": monthly, "rate": rate,
                                                        "years": years},
                {"final": round(b, 2), "contributed": round(contrib, 2), "growth": round(b - contrib, 2),
                 "yearly_balance": path}, "monthly compounding; rate is hypothetical, not a forecast")


def fee_drag(principal: float, monthly: float, rate: float, fee_a: float, fee_b: float, years: int) -> Calc:
    a = compound_growth(principal, monthly, rate - fee_a, years).results["final"]
    b = compound_growth(principal, monthly, rate - fee_b, years).results["final"]
    return Calc("Fee drag", {"principal": principal, "monthly": monthly, "gross_rate": rate, "fee_a": fee_a,
                             "fee_b": fee_b, "years": years},
                {"final_low_fee": a, "final_high_fee": b, "difference": round(a - b, 2)},
                "compound growth at (rate − annual fee)")


def fmt_money(v: float) -> str:
    return f"${v:,.0f}"


def spoken_money(v: float) -> str:
    """Rounded, natural spoken form, e.g. 'about eleven thousand dollars' is left to TTS; we give digits."""
    if v >= 1_000_000:
        return f"about ${v / 1_000_000:.1f} million"
    if v >= 10_000:
        return f"about ${round(v, -3):,.0f}"
    if v >= 1_000:
        return f"about ${round(v, -2):,.0f}"
    return f"about ${round(v):,.0f}"
