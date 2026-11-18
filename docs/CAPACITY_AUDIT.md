# GLIVARAO Finance: production capacity audit at $100/month (2026-11-18)

**Method:**
- Benchmarks of the real v2 pipeline, using `deploy/benchmark.py` (kept in the repo so the same test can be run
  on the VPS).
- Code inspection.
- No paid API calls and no purchases. Nothing was uploaded.

**Labels used in this document:**
- **MEASURED** = timed in this session.
- **EXTRAPOLATED** = measured throughput × length, linear (render cost per second of video was steady across
  runs: 5.0–5.35 CPU-s per video-second).
- **ESTIMATE** = not measurable without a paid call or a purchase.

---

## 1. Is 15–18-minute script generation genuinely working? **No, not today.**

| Path | Status | Long-video length produced |
|---|---|---|
| Free writer (default, $0) | Working and tested on all 33 topics | **2–4 min** (201–537 words). The end-to-end run produced a **3.7-min** "long" video. **This does not count as a 15–18-min video.** |
| Claude writer (`ALLOW_PAID_APIS=true`) | Built, **never run live** (no key, no paid calls allowed). Only a mocked-SDK test passed | Designed for 16.5 min (~2,475 words). **Unverified** |

Known issues in the Claude path, found by inspection:
- **Length gate.** Compliance requires 2,200–2,800 words for a paid long script. If the model writes fewer words,
  the script is rejected **after being paid for**, and there is no automatic "extend" or retry step.
- **No spend guard in code.** Nothing tracks API cost or stops at a monthly limit. Only an Anthropic Console
  spend limit would protect the budget.
- **No chapters.** Claude descriptions lack the `{CHAPTERS}` placeholder, so long videos would ship without
  chapters.
- **No v2 direction fields.** The Claude script schema has no set, entrance or money-effect fields. The director
  falls back to automatic choices, which works but gives less variety.

**So with the current system, qualifying 15–18-minute videos per month = 0 until the Claude path is approved
and verified with one live test.**

## 2. Rendering benchmark (MEASURED)

Full-length test: **16.9-minute video** (1,014.7 s, 2,477 words, 63 scenes), plus the Telegram review copy and
2 Shorts.

| Hardware (simulated by CPU pinning) | Long render | Review copy (≤50 MB) | Per Short (~40 s) | Peak RAM | Daily set (1 long + 2 Shorts) |
|---|---|---|---|---|---|
| 4 vCPU, 4 workers (**measured full length**) | 24.6 min | 3.2 min | ~1.0 min | **5.08 GB** | **29.8 min** |
| 2 vCPU, 2 workers (measured on a 217 s section) | 2.54 s per video-s → **43 min** for 16.9 min (EXTRAPOLATED) | ~9 min | 1.6 min | **2.21 GB** | **≈55 min** |
| 1 vCPU, 1 worker (measured on a 217 s section) | 4.34 s per video-s → **73 min** (EXTRAPOLATED) | ~16 min | 2.7 min | **1.66 GB** | **≈94 min** |

- CPU work per daily set: **≈106 CPU-minutes** (MEASURED total: 6,349 CPU-s).
- Where the RAM goes:
  - the main process holds the voice model, dictionaries and pronunciation engine (**~0.7 GB**) for the whole
    render;
  - each scene worker adds roughly 0.5–1 GB (frame caches, including a rotated-sprite cache of up to 2,048
    images, plus its ffmpeg encoder).
- **Bottleneck = RAM, not CPU.**
  - Even the slowest case (1 vCPU) finishes a daily set in about 1.6 h of a 24 h day.
  - But 1 worker needs **1.66 GB**. On full-length videos this is likely higher (the main process holds the
    whole narration and music in memory); that part is an ESTIMATE.

### Storage and bandwidth per daily set (MEASURED)

| Item | Size |
|---|---|
| Long master MP4 (1080p) | 351 MB |
| Telegram review copy (720p) | 47.5 MB |
| Intermediate WAVs (deletable after render) | 146 MB |
| 2 Shorts plus covers | ~20 MB |
| **Total** | **≈575 MB/day → ≈17 GB/month at 30-day retention** (≈13 GB if the WAVs are deleted) |

Telegram upload: about 70 MB/day, roughly 2 GB/month.

## 3. Is a $5 VPS sufficient?

| $5-class VPS (third-party listings; verify on the provider site) | Verdict |
|---|---|
| 1 vCPU / 1 GB RAM (typical DigitalOcean or Vultr tier) | **No.** Peak RAM of 1.66 GB with 1 worker exceeds 1 GB, so it would run out of memory. A swap file might make it limp through, but that is untested |
| **2 vCPU / 4 GB RAM / 40 GB NVMe** (Hetzner CX22, listed at about $4.35–$5) | **Yes, with 2 workers.** 2.21 GB measured on a section; full length estimated at about 2.6–3 GB. About 55 min per daily set. Disk holds about 30 days of output. Add a 2 GB swap file as a safety margin |
| Anything with 4 workers | **No.** It needs about 5 GB of RAM. The code currently defaults workers = CPU count, so this must be capped on the VPS |

## 4. Recurring monthly costs

| Item | Status | $/month |
|---|---|---|
| VPS (2 vCPU / 4 GB) | Required | **$5** (assumed; listed at $4.35–$5) |
| Narration (Kokoro am_michael, local) | Working, free | $0 |
| Music bed and sound effects (synthesized) | Working, free | $0 |
| Research data (CFPB, Stack Exchange, Wikipedia) | Working, free | $0 |
| YouTube Data API (competition data) | Not configured; free quota | $0 |
| FRED | Optional, free | $0 |
| Telegram Bot API | Free | $0 |
| Storage | Within the VPS disk | $0 |
| Music licensing | Not needed (original) | $0 |
| **Claude scripts (only if approved)** | ESTIMATE, see below | **$0 today; $6–$42 if enabled** |

**Claude cost ESTIMATE.** Prices are from the SDK reference table cached 2026-11-03. Token counts are estimated
from a full-length script object: about 9.1k visible output tokens per long script, plus unmeasured
adaptive-thinking tokens assumed at 5k–25k. Input is about 2–4k tokens.

| Model | Per long script | Per Short script | 30 long + 60 Shorts | With 1.5× retry headroom |
|---|---|---|---|---|
| Claude Opus 5.5 ($4 in / $20 out per MTok) | $0.29–$0.70 | $0.04–$0.12 | **$11–$28** | ≤ $42 |
| Claude Sonnet 5.5 ($2 / $10) | $0.15–$0.35 | $0.02–$0.06 | **$6–$14** | ≤ $21 |
| Claude Haiku 5.5 ($0.10 / $0.50) | <$0.02 | <$0.01 | **<$1** | <$2 (quality likely too low for 17 min) |

## 5. What runs free and offline, and what needs paid APIs

- **Free, runs on the VPS:**
  - topic research (needs internet for the public APIs);
  - topic selection;
  - fact sheets;
  - exact financial math;
  - the free script writer (short "long" videos and Shorts);
  - Kokoro narration (fully offline);
  - music and sound effects (offline);
  - mixing and mastering (offline);
  - animation, captions and thumbnails (offline);
  - metadata;
  - Telegram delivery and approval (free API).
- **Paid (needs your approval):** the Claude writer for 15–18-minute original scripts, and optional AI judgment
  in research.
- **Paid alternatives, not needed:** ElevenLabs or Google voices (blocked without approval).

## 6. Three scenarios within $100/month

| Scenario | Setup | Monthly cost | Qualifying 15–18-min long videos / month | Shorts / month | Confidence |
|---|---|---|---|---|---|
| **Conservative (today's system, no paid APIs)** | Free writer, $5 VPS | **$5** | **0** (it makes 30 videos of 2–4 min, which don't qualify) | **60** | High (tested) |
| **Realistic (after approval and one live verification run)** | Claude Opus 5.5 for scripts, 1 long + 2 Shorts per day | **≈$16–$47** | **30** | **60** | Medium: script generation is unverified until a live test |
| **Maximum within $100** | Opus 5.5, 3 daily sets per day on the 2 vCPU VPS (≈2.75 h CPU/day) | **≈$40–$90** | **≈90** | **≈180** | Low–medium. Limited by API spend, your review time and disk (≈50 GB/month → needs 10-day retention). Compute is not the limit |

## 7. What must be fixed for reliable, professional output (in priority order)

1. **Verify the Claude long-script path with one live run** (cost under $1, needs your approval). Then add:
   - an automatic "extend to target length" retry instead of discarding a paid script;
   - a **monthly API spend guard** in code, plus an Anthropic Console spend limit;
   - chapters for Claude descriptions.
2. **RAM-aware worker count.** Cap workers by free RAM (about 1 GB each), not CPU count, so a 2 vCPU / 4 GB VPS
   uses 2 workers and never runs out of memory.
3. **Release the voice model before rendering frames** (it holds about 0.7 GB the whole time). Cap the
   rotated-sprite cache. This lowers peak RAM.
4. **Delete intermediate WAVs after the master** (−146 MB/day). Prune masters after approval or rejection.
5. **Retry a failed daily run once, and send a Telegram alert** on failure. Today a failure just stops.
6. **Quality:**
   - the editorial hand-drawn restyle (Phase 1, awaiting approval);
   - more character and visual variety for 60-scene videos;
   - a richer music bed (the synthesized one is simple);
   - YouTube competition data (free key) for better topic picks.
7. **Telegram long-video delivery:** the review copy is 720p because of the 50 MB limit. Use a self-hosted Bot
   API server if you want the 1080p master in Telegram.

## Final answer

- **Today, exactly as built, for about $5/month on a 2 vCPU / 4 GB VPS:** **0 genuine 15–18-minute long videos
  and 60 Shorts per month.** The system can also produce 30 videos of 2–4 minutes, but those do not meet your
  long-form requirement.
- **After you approve the Claude writer and it passes one live test:** **30 long (15–18 min) + 60 Shorts per
  month**, estimated at **$16–$47/month total**, well inside $100. The hardware has been measured to handle it.
  Up to about **90 long + 180 Shorts** fit within $100 if you can review that many.
- **A 1 GB / 1 vCPU "$5" VPS will not work.** Use a 2 vCPU / 4 GB plan.
