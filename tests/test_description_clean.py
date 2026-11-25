"""Upload-pack descriptions: real sources only, plain sentences, no affiliate placeholders/disclosure before real
links, no 'My take' sentence without a take; titles of at most 60 characters."""
from glivarao.content.packaging import clean_description, short_title

DISC = "Some links may be affiliate links."
DESC = """Plain summary.

Sources:
- Federal Reserve G.19: https://www.federalreserve.gov/releases/g19/current/
- Reddit question: https://money.stackexchange.com/questions/123/x

Calculations:
- Minimum payment payoff: total_interest = 1800 (inputs: {'principal': 0, 'apr': 0.2236, 'years': 0}; amortization)

[AFFILIATE: debt payoff]

Some links may be affiliate links.

About this video: the narration is an AI voice. The "My take" section is the channel host's own view.
"""


def test_clean_description():
    out = clean_description(DESC, has_take=False, disclosure=DISC)
    assert "stackexchange" not in out and "federalreserve.gov" in out
    assert "{" not in out and "apr 0.2236" in out and "principal" not in out
    assert "[AFFILIATE" not in out and DISC not in out and "My take" not in out
    kept = clean_description(DESC, has_take=True, disclosure=DISC, keep_disclosure=True)
    assert DISC in kept and "My take" in kept


def test_titles_at_most_60_characters():
    t = short_title("How to Get Out of Credit Card Debt: A Plan That Works on Any Income for Real")
    assert len(t) <= 60 and t == "How to Get Out of Credit Card Debt"
    t2 = short_title("Why Paying Only the Minimum on Your Credit Card Keeps the Balance Alive For #Shorts")
    assert len(t2) <= 60 and t2.endswith("#Shorts") and not t2[:-8].split()[-1].lower() in ("the", "for", "on")
