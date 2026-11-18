# GLIVARAO autonomous topic research and content system: design proposal

**Status:** proposal only. No production code has been changed. Waiting for the owner's approval.

**Goal:** every day, the system researches, chooses and produces the strongest **finance-only** video by
itself. The owner only reviews finished videos in Telegram.

**Hard rules, enforced in code:**
- **Nothing is ever uploaded, published or scheduled on YouTube automatically.** Approval only marks a
  video as approved. Uploading stays a manual, interactive, private-only command.
- **Finance-only.** Allowed topics fall into seven categories:
  1. Personal Finance
  2. Financial Psychology
  3. Investing
  4. Credit and Debt
  5. Saving and Wealth Building
  6. Banking and Money
  7. Financial Mistakes and Scams

  Politics, general news, general economics, geopolitics and unrelated subjects are rejected at two
  separate checkpoints.
- **No virality promises.** Scores are *opportunity estimates* with stated confidence, never predictions
  that a video "will go viral".
- **No copying.** Competitor videos are used only as **metadata signals** (titles, view counts, upload
  dates, durations). Their scripts, visuals, thumbnails and wording are never reused. Our titles are
  checked for similarity against competitor titles.

---

## 1. How it works: one day in the system

```
 05:00  COLLECT ─ official APIs and public data sources ─▶ raw signals (phrases, questions, view stats)
 05:20  CLUSTER ─ Claude groups signals into candidate topics and tags each with a category and market (US/CA)
 05:25  GATE 1  ─ finance-only filter (blocklist + Claude classifier) ─▶ off-topic candidates discarded and logged
 05:30  SCORE   ─ 8 criteria, each 0–10 with evidence ─▶ ranked opportunity table
 05:35  SELECT  ─ diversity rules (category rotation, no repeats, evergreen/trending mix) ─▶ 1 long + 2 Shorts
 05:40  RESEARCH─ fact sheet from authoritative sources only; numbers computed in code; unsourced claims dropped
 06:00  CREATE  ─ idea → script → GATE 2 (finance-only + compliance) → storyboard → narration → animation
                  → thumbnail → title, description and tags
 ~08:00 REVIEW  ─ Telegram: finished MP4, thumbnail, metadata, WHY this topic (scores + evidence), fact sheet
        OWNER   ─ Approve / Reject. Nothing is uploaded either way. Uploading is a separate manual step.
 Weekly LEARN   ─ YouTube Analytics feeds back into scoring weights and title/thumbnail patterns
```

---

## 2. Where the research comes from

Only official APIs and public datasets are used. YouTube pages are never scraped, and Google Trends and
Reddit are not scraped either.

| Source | What it tells us | Access | Cost | Notes |
|---|---|---|---|---|
| **YouTube Data API v3**: search, videos, channels | Competitor videos on each candidate topic: views, upload age, **views per day**, **outlier ratio** (a video's views divided by its channel's median views), number of recent videos (competition), title patterns | API key (Google Cloud) | Free quota of 10,000 units/day. A search costs 100 units, so about 60–80 topic probes a day plus stats lookups | The core signal for "potential views" and "competition" |
| **Our YouTube Analytics API** (already integrated) | Our views, watch time, average view %, audience retention curve, subscribers gained per video | OAuth (existing) | Free | Powers the learning loop |
| **CFPB Consumer Complaint Database** | What Americans actually struggle with, by product and issue (credit reports, debt collection, credit cards, banking) and how that changes month to month | Public API, no key | Free | Strong "real problem" signal for Credit and Debt, and Banking |
| **FTC Consumer Sentinel data** (public reports) | Top scam types, reported losses and payment methods | Public downloads | Free | Drives the Scams category. Updated periodically, not daily |
| **Canadian Anti-Fraud Centre, FCAC** (public pages and data) | Canadian scam trends and consumer-finance issues | Public | Free | Canadian relevance |
| **Wikipedia Pageviews API** | Long-run and seasonal interest in finance concepts (for example "Roth IRA", "TFSA", "credit score") | Public API, no key | Free | Evergreen-demand and seasonality proxy |
| **Stack Exchange API** (Personal Finance & Money) | Frequently asked money questions, with views and votes | Public API (optional free key) | Free | "Audience curiosity" signal: real questions in people's own words |
| **FRED** (household-finance series only) | Credit-card interest rate, saving rate, revolving credit, delinquencies, mortgage rates | Free key | Free | Provides real data for charts and "why now" timeliness, framed only as personal money |
| **Claude with server-side web search** | Fresh context: new product launches, rate changes, scam waves, seasonal moments (tax season, back-to-school, holidays). Searches can be restricted to listed domains | Anthropic API | Billed per search plus tokens | Used for **synthesis**, not as the only evidence. Every claim it surfaces needs a source URL |
| **Optional, needs your decision** | Reddit (r/personalfinance, r/PersonalFinanceCanada and similar) is a strong question source, but its API terms restrict commercial use. Google Trends has no generally available official API | Agreement or application required | — | **Not included** unless you approve after reviewing their terms |

**Note:** this cloud test environment currently blocks youtube.com and some other research hosts. The
production server (VPS) would need normal internet access to these APIs.

---

## 3. Finding candidate topics

Raw signals are phrases and questions, such as "is a HYSA worth it", a competitor video called "I Tried
the Envelope Method for 90 Days" with 14× its channel's usual views, or a rising CFPB complaint count
about "debt collection: attempts to collect debt not owed".

Claude clusters the signals into **candidate topics**. Each candidate records:
- **category** (one of the seven);
- **market**: US, CA or both. For example a Roth IRA is US-only, a TFSA is Canada-only, credit scores
  apply to both;
- **type**: evergreen or timely;
- **core viewer question**: "Why does my credit-card balance never go down?";
- **evidence**: the signals behind it, with links and numbers.

**Gate 1, finance-only.**
- A keyword blocklist rejects politics, elections, parties, wars, geopolitics, celebrities and general
  economics framed without a personal-money angle.
- A Claude classifier then asks: "Is this directly about a person's money decisions, products, behavior
  or risks?" A candidate must pass both checks.
- Borderline cases are reframed or dropped. For example "the Fed raised rates" becomes "what a rate change
  does to *your* credit-card APR and savings yield", or is discarded if it can't be personal.
- Every rejection is logged, so you can audit what was filtered out.

---

## 4. Scoring (your 8 criteria), with transparent evidence

Each criterion is scored 0–10. A score is never just an AI opinion: each one is tied to measurable
evidence where that's possible.

| Criterion | How it is measured | Evidence type |
|---|---|---|
| **Audience demand** | Wikipedia pageview level and trend, Stack Exchange question volume, CFPB complaint volume for the issue, and the number of YouTube results with real view counts | Measured |
| **Potential views** | Median views per day of the top recent YouTube videos on the topic (last 6 months), and the share of them that are **outliers** (more than 3× their channel's median) | Measured |
| **Competition** (higher = easier) | Number of videos on the topic in the last 90 days, and the size of the channels dominating results. Demand divided by supply gives the opportunity gap | Measured |
| **Thumbnail potential** | Is there one striking number or one clear visual metaphor? Claude drafts 3 thumbnail concepts and scores them against a fixed rubric | AI judgment (labelled) |
| **Title potential** | Claude drafts 10 titles and rates them on curiosity, clarity and honesty. Titles are checked for similarity against competitor titles | AI judgment (labelled) |
| **Audience curiosity** | Share of signals phrased as questions ("why", "how", "is it worth", "should I"), and the views and votes on those questions | Measured plus judgment |
| **US/Canada relevance** | Applies to both markets = high. One market only = medium. The system alternates US-only and CA-only topics | Rule-based |
| **Sponsorship and monetization** | Category value from public industry reporting (credit cards, investing apps, banking and budgeting tools usually attract more finance sponsors than general money tips) | Estimate (labelled) |

**Opportunity score** = the weighted sum of the eight criteria (0–100), plus two modifiers:
- **Freshness:** timely topics get a bonus that decays over about 2 weeks.
- **Learned performance:** a boost or penalty from our own channel's results in that category and title
  style, once enough data exists.

Starting weights: demand 20%, potential views 20%, competition 15%, curiosity 10%, thumbnail 10%,
title 10%, US/CA relevance 8%, monetization 7%. The learning loop adjusts them over time.

Each score also carries a **confidence level** (high, medium or low) based on how much measured evidence
supports it. A topic with high AI-judged scores but little measured evidence is marked low-confidence.

**Example of the daily ranking table you would see.** The rows are illustrative only, not real research
results:

| Rank | Topic | Category | Market | Score | Confidence | Why |
|---|---|---|---|---|---|---|
| 1 | *"Why your credit-card balance never goes down"* | Credit and Debt | US+CA | 81 | High | Rising complaint volume, 3 outlier videos in 60 days, strong single-number thumbnail |
| 2 | *"The 'too good to be true' text-message job scam"* | Scams | US+CA | 77 | Medium | Recent FTC reporting increase, low competition |
| … | | | | | | |

---

## 5. Choosing the day's videos

- **1 long video:** the top-scoring candidate that passes the diversity rules.
- **2 Shorts:** either two angles on the long video's topic, or the next best quick-hit topics (a single
  idea that works in 45 seconds).
- **Diversity rules:**
  - no category more than twice in 7 days;
  - no topic repeated within 90 days, unless it is a deliberate refresh of a past winner;
  - about 70% evergreen and 30% timely each week;
  - US-only, CA-only and both-market topics balanced across the week.
- **Exploration:** about 1 video in 7 deliberately tests an under-explored category or format, so the
  system keeps learning instead of only repeating early winners.

---

## 6. Research and fact verification (before any script is written)

1. Claude builds a **fact sheet** for the topic using web search restricted to authoritative domains:
   - US: irs.gov, consumerfinance.gov, ftc.gov, investor.gov, sec.gov, finra.org, fdic.gov, ssa.gov,
     federalreserve.gov (data only);
   - Canada: canada.ca, cra-arc.gc.ca, fcac-acfc.gc.ca, antifraudcentre-centreantifraude.ca, osc.ca;
   - plus FRED for data.
2. **Every factual claim** in the fact sheet must carry a source URL and its retrieval date. Claims
   without a source are dropped.
3. **All numbers in examples are computed in code**: loan payoff, compound growth, fees, inflation
   effects. The script may only quote a number that is in the fact sheet or comes from a calculation.
4. **Year-specific figures** (contribution limits, tax brackets, rates) are stated with their year, and
   the reviewer sees them flagged.
5. The fact sheet goes into the Telegram review package next to the video.

---

## 7. Creating the video (connects to the existing pipeline)

The existing pipeline produces scripts, narration, rendering, thumbnails and compliance checks. It also
sends the Telegram review package. The research system adds:
- an **original idea brief** before the script: angle, hook built on a real number, story arc, and
  what's new compared with existing videos;
- a **script grounded only in the fact sheet**;
- **Gate 2**: the finance-only check is re-run on the finished script, plus the existing compliance rules
  (no guarantees, no personal advice, disclaimer, originality);
- the **storyboard / visual beats** and the new hand-drawn style (Phase 1 of the visual upgrade, still
  awaiting your approval);
- a **"why this topic" card** in Telegram: scores, evidence links, confidence, and the runner-up topics.

---

## 8. Continuous improvement (learning loop)

Collected weekly from the YouTube Analytics API for every published video:
- views at 48 hours, 7 days and 28 days;
- average view percentage and the retention curve;
- subscribers gained;
- likes;
- **CTR and impressions** where the API exposes them. If a figure isn't available through the API, the
  system asks you to paste it from YouTube Studio once a week. It never guesses.

What it learns:
- **Topic level:** which categories, markets and evergreen-vs-timely mixes beat our channel's baseline.
- **Packaging:** which title patterns (question, number, warning, "why…") and thumbnail templates earn
  more clicks, compared within similar topics.
- **Retention:** which script structures and hook styles hold viewers. The system records where viewers
  drop off in the retention curve and maps that to the script beat playing at that moment.
- **Subscribers and sponsors:** which categories convert viewers to subscribers. Category value for
  sponsors is tracked separately from views.

How the learning changes behavior:
- Scoring weights are re-fitted monthly once at least 30 videos have data. Until then the defaults
  apply, plus small adjustments.
- Category choice uses a **multi-armed bandit**: categories that perform get picked more, while the
  1-in-7 exploration slot keeps testing the others.
- A weekly **"what we learned" report** goes to Telegram: top and bottom videos, and patterns, with sample
  sizes so small numbers aren't over-read.

**Honest expectation:** with one long video a day, reliable conclusions need several weeks of data. In
the first month, external research signals carry most of the weight.

---

## 9. What you see and do

The daily Telegram review package contains:
1. **Why this topic:** the score, evidence links and confidence, plus the 2 runner-up topics.
2. **Fact sheet:** every claim with its source.
3. **The finished MP4**, thumbnail, title, description and tags.
4. **Compliance report** and items flagged for fact-checking.
5. **Approve / Reject** buttons, plus an optional **"Reject – reason"** reply. Rejection reasons feed the
   learning loop (for example "wrong tone" or "topic too basic").

**Your role:** review and approve. You don't choose topics. Uploading to YouTube stays a manual step that
you trigger yourself.

---

## 10. Credentials and costs

| Need | Status | Cost |
|---|---|---|
| YouTube Data API key | **New**, needed | Free (quota-limited) |
| Anthropic API key | Needed (already planned) | Pay per use: research, synthesis, scripts and scoring. Rough order of a few dollars per day; check current pricing |
| FRED API key | Needed (already planned) | Free |
| YouTube OAuth for Analytics | Already planned | Free |
| CFPB, Wikipedia, Stack Exchange, FTC/CAFC data | No key needed | Free |
| Reddit API / Google Trends | **Optional.** Only if you approve after reviewing their terms | Terms apply |
| VPS with normal internet access | Needed for research | Existing plan |

---

## 11. Build plan (each step needs your approval; the main pipeline is untouched until approved)

| Step | Deliverable | Touches production? |
|---|---|---|
| R1 | `glivarao/research/` module: collectors (YouTube Data API, CFPB, Wikipedia, Stack Exchange, FRED), signal store in SQLite, finance-only Gate 1, scoring, ranking report. **Dry-run mode prints the ranked table only** | No. New module plus a `research` CLI command |
| R2 | Run it for 3–5 days in report-only mode. You review the daily ranking tables and judge whether the picks are good. Weights are tuned | No |
| R3 | Fact-sheet builder with restricted-domain search and code-computed numbers; script generation grounded in the fact sheet; Gate 2 | Script generation (after approval) |
| R4 | Wire it into the daily run: research, select, create, then send to Telegram for review. Includes the "why this topic" card | Daily orchestration (after approval) |
| R5 | Learning loop: analytics ingestion, weekly report, bandit category selection, monthly weight re-fit | Analytics module |

**Not part of any step:** automatic uploading, publishing or scheduling.
