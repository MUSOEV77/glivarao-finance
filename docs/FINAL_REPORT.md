# GLIVARAO Finance: final status report (2026-11-18)

**Testing basis:**
- Everything marked ✅ was run and checked in this session.
- "Historical" means a replay of past dates, not real daily observations. **No real day-to-day operation has
  happened yet.**
- Test suite: **59 passed**.
- Nothing was purchased, no paid API was called, and nothing was uploaded, published or scheduled on YouTube.

## Headline

One command (`python -m glivarao daily-v2`) now runs the whole day:
1. researches finance topics from live public data;
2. picks one (finance-only, US and Canada);
3. builds a fact sheet;
4. writes 1 long script and 2 Shorts scripts;
5. narrates them with a local American male neural voice;
6. adds an original music bed and sound effects;
7. animates, captions, thumbnails and packages each video;
8. delivers a full review package to Telegram, where approving uploads nothing.

The end-to-end run took **607 s** on 4 vCPU.

**The biggest gap is the "long" video. With the free script writer it is 3.7 minutes, not 15–18.** Full-length
original scripts need the Claude writer. It is built, but it is paid, so it is switched off until you approve it.

---

## ✅ Fully working (tested)

| Area | What was tested | Result |
|---|---|---|
| Topic research | Live run on CFPB complaints, Stack Exchange Personal Finance & Money, and Wikipedia (trending + 400-day history) | 33 ranked finance topics. 29 off-topic items rejected (economics, news, entertainment, non-US/CA) |
| Research validation | **Historical replay** of 4 past weekly dates | Week-to-week overlap of 54–82% in the top 10. Credit cards, mortgages, taxes, scams and stocks were in the top 10 every week. The finance-only filter caught off-topic items on every date |
| Finance-only gates | Gate 1 on research candidates and Gate 2 on every finished script (unit tests on politics, economics, news, entertainment) | Pass |
| Topic selection | Simulated 7 consecutive days on the real ranking (no topic repeats within 90 days; at most 2 picks per category in 7 days) | 6 different categories in 7 days, no repeats |
| Fact sheet | Every fact is labelled DATA (with source link), CALCULATION (inputs and formula), or EDITORIAL | Verified in the end-to-end run |
| Exact math | Card payoff, loan amortization, compound growth, fee drag (checked against closed-form formulas) | $5,000 at 24% APR paying the minimum: about 19.5 years and $8,887 in interest; at $200/month: 3 years and $2,001 |
| Free script writer | All 33 ranked topics, each producing 1 long script and 2 Shorts scripts, run through compliance | 33 of 33 pass |
| Narration | Kokoro-82M `am_michael` (US male, local, free, Apache-2.0); finance pronunciation lexicon; pauses and emphasis; sentence timing | 0 pronunciation-dictionary misses in the end-to-end run. **espeak is refused in production mode** (tested) |
| Music and sound effects | Synthesized in code (no licensing): piano/pad bed, pencil, whoosh, pop, coin, chime; cued to animation events | The music ducks about −9 dB under the voice. No clipping |
| Loudness | Two-pass EBU R128 | Measured **−15.5 to −15.9 LUFS** against a −14 target (see Partial) |
| Animation | Rigged characters (gestures, walk, blinks, lip-sync), 5 sets, props, camera moves, transitions. Long videos 1920×1080 at 24 fps; **Shorts 1080×1920** | Decoded without errors. Frames inspected |
| Captions | Burned in, sentence-timed, plus an SRT file | ✅ |
| Thumbnails | New serif + highlighter + calculated chart + Max design. 1280×720 (under 2 MB) plus vertical covers | Inspected for 7 topic families |
| Metadata | Title, description with automatic chapters, sources, calculation notes, disclaimer and tags | ✅ (12 chapters on the long video) |
| Telegram review | Real HTTP calls to a **local stand-in Bot API server**. Each video sends: thumbnail, title, description and tags, preview, **finished MP4** (46.9 MB review copy for the long video), SRT, research card, fact sheet, checks, Approve/Reject | 22 calls delivered |
| Approvals | Approve, reject, and a press from an unauthorized user | Unauthorized press ignored. Approve and reject recorded with an audit trail. **Approval uploads nothing** |
| No auto-upload | `publish` run non-interactively | Refused ("must be run by a person in an interactive terminal") |
| VPS installer | `deploy/install.sh` run on this machine with systemd skipped | Exit 0. Production mode, Kokoro ready, `.env` 600, `secrets/` 700, service user created, tests pass as that user |
| systemd units | `systemd-analyze verify` on all 6 units, plus a calendar check | No errors. Daily run at 04:17 New York time |
| Backups | `deploy/backup.sh` | Valid SQLite backup created. Prunes after 30 days |

## 🟡 Partially working (works, but below target or not fully verified)

| Area | Status | What closes the gap |
|---|---|---|
| **Long video length** | **3.7 min** (537 words) with the free writer. Target is 15–18 min | Approve the paid Claude writer (`ALLOW_PAID_APIS=true` plus an API key). It is built, but tested only with a simulated SDK |
| Script quality and originality | Accurate and finance-only, but assembled from a reviewed template library. Videos in the same topic family will sound alike | Claude writer (above) |
| Topic angles | Strong for 7 topic families (cards, loans, credit reports, scams, saving, investing, banking). Other topics are skipped by the free writer | Claude writer |
| Research depth | No YouTube competition or view data (the API key was declined). Thumbnail and title potential are rules, not AI judgment. Stack Exchange has low volume. Wikipedia sometimes drops days. **Confidence is "medium" at best** | A free YouTube Data API key; optionally Claude |
| Real daily observations | None yet, only historical replay | The first days running on the VPS |
| Voice and music quality | Checked by measurements and pronunciation logs. **I can't listen to audio**, so you need to judge naturalness and music taste | Your review. ElevenLabs remains an option (paid) |
| Loudness | −15.5 LUFS against a −14 target (the true-peak limit stops it). YouTube handles this fine | Optional limiter pass |
| Visual style | v2 vector style. The editorial "doodle" restyle (Phase 1) was **not built** because it was never approved | Your decision on Phase 1 |
| Long video in Telegram | Delivered as a full-length **720p** copy (the Bot API limit is 50 MB). The 1080p master stays on the server | Optional self-hosted Bot API server (2 GB limit) |
| Learning loop | YouTube Analytics fetch exists. **Feeding results back into topic scoring isn't built yet** | Next development step, after a few weeks of real data |
| Shorts thumbnails | YouTube's API can't set custom Shorts thumbnails. The cover is for review only | YouTube limitation |

## 🔑 Requires VPS deployment or credentials (all free unless noted)

| Need | Why | Cost |
|---|---|---|
| **Telegram bot token + your chat ID** | Real delivery was tested only against the local stand-in server | Free |
| VPS with systemd | The timers were verified but have not actually run | Your server |
| GitHub write access (currently **403**) | Push the code. All commits are safe locally and in the bundle file | Free |
| YouTube Data API key | Competition and view-potential research | Free (quota) |
| YouTube OAuth client + `youtube-auth` | Analytics, and manual private uploads if you want them | Free (quota) |
| FRED key | Household-finance data charts (optional) | Free |
| **Anthropic API key + `ALLOW_PAID_APIS=true`** | Full-length, fully original scripts and AI judgment in research | **Paid. Needs your approval** |

## Errors found and fixed today (selected)

- Minimum-payment model: a flat 2% minimum never paid off at 24% APR. Switched to the common issuer formula of 1% of the balance plus interest.
- Research scoring: topics with a single source were inflated by estimates. Missing evidence now counts as weak evidence.
- False topic matches from long CFPB sub-issue text ("bankruptcy" matching mortgage complaints).
- Finance questions such as "financing a car" were wrongly rejected.
- Market tagging: credit cards and scams now count for the US **and** Canada.
- Most Shorts were under the 90-word minimum. They are now lengthened with reviewed explanations, never filler.
- Acronyms were lost in narration ("TIPS" was read as "tips").
- Thumbnail headlines overlapped the charts.
- The Shorts character panel showed the chart a second time.
- The renderer hung forever when a worker crashed. It now times out with a clear error.
- **systemd `EnvironmentFile` would have broken `.env` values with inline comments, silently falling back to dry-run.**
- The installer would have copied 1 GB of local environment and renders. It now copies code only and never overwrites `.env` or data.

## Safety rules (enforced in code and tested)

- No automatic upload, publish or schedule. Uploading needs an interactive terminal, the job ID retyped, the
  kill-switch on, and OAuth, and it is always private.
- No paid API without `ALLOW_PAID_APIS=true`.
- espeak and silent narration are refused in production.
- Secrets never appear in logs or errors.
- Backup tag: `backup/pre-integration-2026-11-18`. All earlier code is preserved; the v1 pipeline still works.
