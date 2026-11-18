# GLIVARAO Finance — Implementation Plan

**Goal:** every day, produce one original 15–18 minute US personal-finance explainer and two original
YouTube Shorts. Each one has American English male narration, original hand-drawn-style cartoon characters
and illustrations, animated charts, subtitles and a thumbnail. A human approves each video in Telegram
before anything is published, and YouTube analytics flow back into planning.

**Rules for every phase:**
- Original scripts and artwork only. No imitation of other channels.
- Credentials come only from environment variables or secret files that are kept out of git.
- No purchases and no publishing without the owner's explicit approval.

---

## Starting point

The repository `musoev77/glivarao-finance` was empty: no commits, no code. Everything below was built from scratch.

## Phase 0 — MVP (this delivery) ✅

| # | Component | Module | Status |
|---|-----------|--------|--------|
| 1 | Config from env, secret redaction, readiness report | `glivarao/config.py`, `doctor` | Done, tested |
| 2 | Job store and status machine (approval cannot be skipped) | `glivarao/storage.py` | Done, tested |
| 3 | Topic bank and de-duplication | `glivarao/topics.py`, `config/topics.yaml` | Done, tested |
| 4 | Script generation with the Claude API (structured JSON output, refusal fallback) | `glivarao/scriptgen/claude.py` | Done, tested with a mocked SDK; needs an API key to run for real |
| 5 | Offline script generator for dry runs and CI | `glivarao/scriptgen/offline.py` | Done (generic placeholder copy) |
| 6 | Compliance checks: banned guarantee language, disclaimer, length, originality overlap, fact-check list | `glivarao/compliance.py` | Done, tested |
| 7 | Narration (ElevenLabs / Google TTS for production; espeak and silent for development) | `glivarao/tts/` | Dev voices tested; production voices need keys |
| 8 | Original cast (Max and Penny), 16 illustrations, hand-drawn line style | `glivarao/art/` | Done |
| 9 | Animated charts: compound growth (exact math), bar, line, pie | `glivarao/art/charts.py` | Done, math tested |
| 10 | Real economic data from FRED (CPI, Fed funds, mortgage rates, unemployment, 10-year yield) | `glivarao/marketdata.py` | Done, tested with mocked HTTP; needs a free key |
| 11 | Scene compositor with lip-flap from audio loudness, blinking, line boil, chart reveal | `glivarao/render/scene.py` | Done |
| 12 | Subtitles: SRT for YouTube captions, ASS burned into the video | `glivarao/render/subtitles.py` | Done, tested |
| 13 | ffmpeg assembly: H.264/AAC, −14 LUFS loudness, 30 fps | `glivarao/render/video.py` | Done, tested |
| 14 | Thumbnails (1280×720) and vertical covers | `glivarao/render/thumbnail.py` | Done |
| 15 | Telegram approval: Approve/Reject buttons, approver allow-list, audit log | `glivarao/publish/telegram.py` | Tested with a mocked Bot API; needs a bot token |
| 16 | YouTube upload (private by default, kill-switch, captions, thumbnail, synthetic-media disclosure) | `glivarao/publish/youtube.py` | Tested with a mocked client; needs OAuth |
| 17 | YouTube Analytics pull into SQLite | `glivarao/publish/youtube.py` | Tested with a mocked client |
| 18 | CLI and daily orchestration (1 long video + 2 Shorts) | `glivarao/__main__.py`, `glivarao/pipeline.py` | Done |

## Phase 1 — Go live safely (needs the owner's accounts; no code blockers)

1. Create the credentials listed in `docs/CREDENTIALS.md`.
2. Pick the voice: shortlist 3–5 US-English male voices you are licensed to use commercially, render the
   same script with each, and choose one. Then set `TTS_PROVIDER=elevenlabs` or `google`.
3. Run `python -m glivarao produce --format long` in `GLIVARAO_MODE=production` with Telegram configured.
   Review the output end to end. Tune `SYSTEM_PROMPT` in `scriptgen/prompts.py` until the scripts read well.
4. Run `python -m glivarao youtube-auth` once. Keep `YOUTUBE_PUBLISH_ENABLED=false` until you have reviewed
   several videos. Then switch it on, keeping uploads `private`, and make videos public by hand at first.
5. Schedule the daily run. See "Scheduling" in `docs/OPERATIONS.md`.

## Phase 2 — Quality upgrades (recommended order)

1. **Visual variety.** Add more poses, backgrounds (office, kitchen table, city), and transitions between
   scenes. Add 20–40 more illustrations. Optionally commission a human illustrator for a character model
   sheet and rebuild the cast from layered PNG parts. The renderer already composites RGBA layers, so the
   swap is contained.
2. **Word-level caption timing.** ElevenLabs can return character timestamps, so captions can follow the
   speech exactly rather than being spread out proportionally.
3. **Music and sound effects.** Add a licensed royalty-free bed, ducked under the narration. This is not
   included now on purpose, to avoid licensing risk.
4. **Shorts derived from the long video.** Today each Short is written on its own about the same topic.
   Option: have Claude choose the best 45 seconds of the long script and re-render it vertically.
5. **Topic research.** Rank topics using Analytics data (CTR, retention) and seasonality (tax season,
   open enrollment, Fed meetings).
6. **Second-pass script review.** A separate Claude call that critiques the script for accuracy, clarity and
   hook strength before rendering, and records any fixes in `compliance.txt`.

## Phase 3 — Scale and operations

- Run on a small VM or a GitHub Actions runner with a persistent disk. Render cost is CPU only.
- Back up `data/` (SQLite) and `output/` to object storage. Prune rendered files 30 days after publishing.
- Use a Telegram webhook instead of polling (needs an HTTPS endpoint).
- Alert in Telegram when a run fails. `notify()` already exists; the scheduler should call it on failure.
- Watch the YouTube Data API quota. An upload costs about 1,600 units of the default 10,000 per day, so
  3 uploads a day plus captions and thumbnails fits. Request more quota before adding more videos.

## Architecture

```
topic bank ──▶ script (Claude, JSON schema) ──▶ FRED data fill ──▶ compliance checks
                                                                      │ (fail → rejected_compliance)
                                                                      ▼
            per-scene TTS (WAV) ──▶ timing + captions ──▶ frame compositor ──▶ ffmpeg (burn subs, loudnorm)
                                                                      │
                                                     thumbnail ◀──────┤
                                                                      ▼
                                 Telegram card (thumbnail + checks + preview) [Approve] [Reject]
                                                                      │ approver chat only
                                                                      ▼
                         YouTube upload (gate: approved + kill-switch + OAuth; private by default)
                                                                      ▼
                                                YouTube Analytics ──▶ SQLite ──▶ topic planning
```

Job states: `planned → scripted → rendered → pending_approval → approved → published`. The other
states are `rejected_compliance`, `rejected` and `failed`. Moves between states are enforced in
`storage.ALLOWED`, and every move is recorded in the `events` table (`python -m glivarao events JOB`).

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Wrong financial figures | Compound charts are computed, not written by the model. Real series come from FRED. Other numbers are flagged for human fact-checking in the Telegram card. Year-specific claims are flagged. |
| Content read as investment advice | The system prompt forbids personalized advice and guarantees. A regex check catches guarantee language. Every video ends with a disclaimer. |
| Repetitive or "mass-produced" content (YouTube monetization policy) | Topics are de-duplicated. An 8-word overlap check compares each script with earlier ones. Every video is reviewed by a human. Phase 2 adds visual variety. |
| Synthetic voice disclosure | `containsSyntheticMedia: true` is set on upload. |
| Credential leaks | `.env` and `secrets/` are git-ignored. Secrets are redacted in `doctor`. The Telegram token never appears in error messages. The OAuth token file is chmod 600. |
| Accidental publishing | Three independent gates (human approval, kill-switch, OAuth), and uploads are private by default. |
