> **Evergreen rule (2026-11-22).** Topics are ranked by steady long-term search demand (Google Trends 12-month and
> 5-year stability, cached 30 days; YouTube search suggestions; Wikipedia monthly views), not one-week spikes. Long
> videos: at most 1 timely/date-bound video in 4 (75% evergreen) and at most 1 per week. Evergreen titles and scripts
> carry no dates or "this week" wording (checked in code; one Claude rewrite, else rejected); current numbers are
> stated "as of <Month Year>". Launch list: 14 evergreen + 2 timely (max 2).

> **Final rule since 2026-11-22: US-only.** The audience is ordinary Americans; every video is about a US problem
> and its effect on a US household's money. Macro topics (US housing, the US stock market, the Fed, the national
> debt, US banks, recession signals) are allowed in a 6th pillar, "The US economy and your money"; other countries
> only when the story directly hits Americans (e.g. Japan selling Treasuries). US data only (Fed, FRED, BLS, Census,
> CFPB, NY Fed Household Debt and Credit Report, Treasury). Sponsor-friendly: no profanity, no panic clickbait, no
> political sides (checked in code; one rewrite, else the script is rejected). Every long video ends with a
> "What to do" section; each description gets an `[AFFILIATE: category]` placeholder (budgeting app, high-yield
> savings, credit monitoring, debt payoff, tax software, insurance), no real links yet. Launch list:
> `python -m glivarao launch-list [--verify] [--send]`; nothing from it is planned until you approve it in Telegram.

# Channel focus: 5 pillars, series and affiliate links

**One channel:** English, US finance. A Spanish channel is postponed.

**Niche:** everyday US personal finance for people aged 25–45 who struggle with money.

**Main focus for the next 12 months: debt and credit**, in the style *"the big economic story → what it means for
YOUR money"*.
- At least 60% of long videos are debt and credit: 3 of every 5, checked on every pick.
- Other pillars (taxes, ACA health costs, scams, budgeting, retirement) are used only when tied to a money impact.
- **News-driven videos: at most 1 in 4 long videos.** Evergreen topics get a ranking boost.
- **The first 16 long videos are your launch list** (`docs/LAUNCH_PLAN.md`). The automatic rules start after it.

## The 5 pillars

Every topic must fit one pillar. Anything else is rejected automatically, and the review lists it under
"skipped": crypto, single stocks, options, gold, real-estate investing, Canada-only accounts, insurance, wills,
and general news.

| Pillar | Covers | Series |
|---|---|---|
| **1. Debt and credit** | credit cards, BNPL, personal/payday, auto, student loans, mortgages, credit report and score, debt payoff, collections | Money Traps · Credit Score Fixes · Debt Escape Plan |
| **2. Budgeting and saving** | budgets, subscriptions, spending habits, bank fees, emergency fund, high-yield savings, CDs | Money Traps · Budget Reset · Savings That Work |
| **3. Taxes** | filing, free filing, refunds, credits (EITC, Child Tax Credit), W-4 withholding, side-hustle taxes, IRS changes | **Tax Season 2027** (Dec–Apr) · Tax Smart (rest of year) |
| **4. Retirement and investing basics** | 401(k), IRA/Roth, HSA, 529, index funds, fees, compound interest | Retirement Basics · Investing 101 |
| **5. Scams and consumer protection** | scams, identity theft, payment-app fraud, FDIC protection, your rights | Scam Alert · Know Your Rights |

## Rotation (automatic)

- **Debt and credit: at least 3 of every 5 long videos.** It may run twice in a row, as long as the topic family
  differs. A debt topic may come back after 8 videos with a new angle; other topics need 30 videos.
- **Every other pillar: at most once in 5 long videos, and never twice in a row.** Taxes: twice in 5 in tax
  season.
- Pillars that haven't been covered for a while get a boost in the ranking.
- **Taxes, December–April:** a strong boost, and up to 3 of the last 5 videos. Taxes still never run twice in a
  row. The rest of the year, taxes get a small penalty.
- The existing rules still apply: no topic from the last 30 videos, no similar angle, and every claim needs a
  source URL.

The topic announcement and the review in Telegram show the **pillar** and the **series**. Shorts follow the same
pillar rules on their own days.

## Series and links between episodes

You upload the videos yourself, so the bot needs the YouTube link of each video once.

1. After you upload, **reply to the upload pack's 🕒 PUBLISH TIME message with the YouTube link**. Sending just the
   link also works: it goes to the newest video that doesn't have a link yet, and the bot tells you which one.
2. Create one playlist per series in YouTube Studio, then send:
   `/playlist Money Traps https://www.youtube.com/playlist?list=...`
3. From then on, each upload pack in that series contains:
   - **Description:** "📺 Series: Money Traps", links to the earlier episodes, and the playlist link.
   - **End screen** (long videos): which earlier episode to pick under "Choose specific video", the playlist and
     Subscribe.
   - **Related video** (Shorts): the long episode to link.
   - A reminder to add the video to the series playlist.

`/series` shows each series, its approved episodes, and which ones still need a link.

## Affiliate programs

**Programs:** Rocket Money, Monarch Money, Wise, Rocket Dollar, TurboTax and FreeTaxUSA. YNAB comes later.

**All are placeholders until you're approved.** A placeholder never appears in a description. The upload pack only
lists which placeholders would fit that video.

| Program | Used for |
|---|---|
| Rocket Money | subscriptions, bills, budgeting; debt and budget pillars |
| Monarch Money | budgets and debt payoff |
| Wise | only money-transfer topics |
| Rocket Dollar | retirement (IRA, 401(k)) |
| FreeTaxUSA, then TurboTax | taxes (the IRS free options are mentioned first) |
| YNAB | later |

**Rules:**
- 1–2 links per **long** video: the best topic match first, then the pillar.
- **No links in Shorts.**
- Links sit directly above the affiliate disclosure (an FTC requirement).
- No payday lenders, debt-settlement companies or high-APR cards.

**Telegram:**
- When you're approved: `/affiliate rocketmoney https://your-link`
- Status of every program: `/affiliate`
- Back to placeholder: `/affiliate rocketmoney clear`

If a video ever mentions or shows an affiliate product in the video itself, tick **"Paid promotion"** in YouTube
Studio.
