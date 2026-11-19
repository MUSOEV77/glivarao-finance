# GLIVARAO Finance: production status (2026-11-18, after hardening and the editorial redesign)

**Testing basis:**
- "Tested" means it was run in this cloud container, end to end where stated.
- Nothing was purchased, no paid API was called, and nothing was uploaded, published or scheduled.
- Test suite: **109 passed**.

## ✅ Completed and tested here

| Area | Evidence |
|---|---|
| Daily run (`daily-v2`) | Live research → topic → fact sheet → **1 long + 2 Shorts** → narration → music/SFX → **editorial animation** → captions → thumbnails → metadata → Telegram package. Exit 0. The 3 videos are `pending_approval` |
| Editorial documentary look (new default) | Paper and grain, Caladea serif plus Inter (both OFL, bundled with licenses), chapter cards, count-up figures, full-frame charts, ledger lists, duotone plates, kinetic pull-quotes in sync with the voice, dissolves and a slow push-in. Real frames inspected from the finished MP4s (long 1920×1080, Shorts 1080×1920). The cartoon look is kept: `GLIVARAO_THEME=cartoon` |
| Editorial thumbnails | 1280×720 (under 2 MB) and a 1080×1920 cover. Headline number on a highlighter, plus the video's own chart or a plate |
| Audio | All 3 videos measured −14.2 to −14.3 LUFS, true peak −1.99 dBTP |
| Telegram delivery (local stand-in Bot API) | 23 calls: thumbnail, metadata, preview, review copy (46.4 MB, under 50 MB), Shorts MP4s, SRT, research card, fact sheet |
| Approvals | Unauthorized press ignored. Approve and reject recorded. A repeat press answers "Already approved". A callback without a message id no longer aborts the batch (bug found and fixed) |
| YouTube auto-publishing | Disabled. A non-interactive `publish` is refused. Uploads stay private-only and are never scheduled |
| One set per day | File lock, and a same-day re-run prints "skipped" (tested). `--force` to redo |
| Recovery | Whole-run retry plus a Telegram alert on final failure. Alert when any video fails or is rejected. Render retry with 1 worker. Disk check (unit-tested) |
| Memory | Workers capped by free RAM. Voice model released before frame rendering. Sprite cache capped. Intermediate WAVs deleted (verified: none left in the output folders) |
| Backups | `backup.sh` → tar.gz with an integrity-checked DB copy plus the spend ledgers (never `.env`). `restore.sh` round-trip tested |
| Logging | Timestamped `logs/daily.log`, rotated by logrotate |
| Claude spend guard and length revision | Monthly USD cap checked before every request. Real usage (including cache tokens) recorded. A draft outside 2,200–2,800 words gets one revision instead of being discarded. Claude descriptions get chapters, sources and the disclaimer. **Tested with a simulated SDK only** |
| Gemini Charon voice (locked, no fallback): code paths | Pinned model `gemini-3.8-flash-tts`, voice/pace/style locked, retries with backoff, videos held and retried hourly, $20 cap with an 80% alert (`docs/VOICE.md`). **Simulated HTTP only** |

## 🟡 Partially completed

| Area | Gap |
|---|---|
| **Long-video length** | The free writer makes **3.6 min** (215.6 s in today's run). 15–18 min needs the Claude writer, which is built and guarded but not run live |
| Visual variety | Plates reuse 16 illustrations. Scenes without numbers, lists or charts rely on quotes and plates |
| Render time on a 2 vCPU / 4 GB VPS | Measured here on 4 vCPU: 3.6 min long video in about 7 min wall time, about 1.3 min per Short. Extrapolated for a 17-min video on 2 vCPU: about 45–60 min. **Not measured on the VPS** |

## ⛔ Not tested (needs something only you can provide)

| Item | What's needed |
|---|---|
| Real 15–18-minute Claude scripts | `ANTHROPIC_API_KEY`, added by you as an environment variable in the environment settings (visible to everyone who uses that environment, picked up by a new session), plus `ALLOW_PAID_APIS=true`. About $0.30–$0.60 per long script |
| Real Gemini Charon audio and its real cost | Gemini API key on a billing-enabled project (network secret for `generativelanguage.googleapis.com`, header `x-goog-api-key`), plus your approval of the about 1–3 cent sample |
| Real Telegram | Bot token plus your chat ID on the VPS (`api.telegram.org` is blocked in this container) |
| systemd on a real VPS | A VPS (2 vCPU / 4 GB recommended) and running `deploy/install.sh` there |
| GitHub push | Reconnect GitHub and install the Claude GitHub App with write access to the repository |

## Monthly budget ceiling (enforced in code)

| | |
|---|---|
| VPS | ~$5 |
| Gemini voice | ≤ $20 |
| Claude scripts | ≤ $30 |
| **Worst case** | **~$55**, under $100 |
