# GLIVARAO Finance: production stack audit and decision (2026-11-18)

**Scope.**
- Research only: nothing was purchased, no billing was activated, no keys were used and no production code was
  changed.
- Volume assumed: 30 long videos (15–18 min) and 60 Shorts (30–60 s) per month, which is about **555 minutes of
  narration**, or about **500,000 characters a month** (consistent with the earlier measured 475–522k).

**About the sources.**
- The vendors' own pricing pages could not be loaded from this cloud container (DNS blocked).
- Prices come from recent (mid–late 2026) third-party trackers, plus the vendors' help and license pages that search
  surfaced.
- **Every price must be re-checked on the vendor's page before buying.** Where sources disagreed, the range is shown.

**A correction first: we do not use Remotion today.**
- The current engine is our own **Python (Pillow/numpy) + FFmpeg** renderer, with the editorial documentary theme
  built this week.
- Remotion is a React-based alternative. It is compared below.

---

## 1. Platform-by-platform findings

| Platform | Price (monthly, as reported) | Annual billing | Music / SFX | Image / video generation | Voice | Commercial use (YT / IG / TikTok) | API / automation | Works on our VPS? | Hidden costs and limits |
|---|---|---|---|---|---|---|---|---|---|
| **Artlist Max** | ~$29.99–$39.99 entry (7,500 credits); higher tiers up to 120k credits; Max Pro footage add-on ~$19.92 | Headline prices are **annual** | Full stock music, SFX and footage catalog | 7,500 credits ≈ 25 Full-HD AI videos, 250 images or 1.5 h of AI voiceover per month (shared pool) | AI voiceover inside the credit pool | Broad social and YouTube license. The license bans "static video / loop animation + Artlist music" | **No self-serve API.** The music API is Enterprise / sales only. The license **forbids downloading "by software, bots or any automatic means"** | Only as a manually curated library downloaded by a person | Credits expire monthly (no rollover). AI quota is small for 90 videos |
| **Envato** | Core ~$16.50 (annual) / ~$33 (monthly); Plus ~$39; Ultimate ~$109–169 (new tiers since Feb 2026) | Discount if annual | Large music and SFX catalog (third-party authors) | **10 AI generations per user per month** since 25 Feb 2026 (unlimited ended). MusicGen output has extra limits | VoiceGen within the 10 generations | Commercial license, but **each item must be registered to a project**. Music items carry extra restrictions | Scripts, bots and automated tools are **not permitted** | Manual only | Per-project registration conflicts with reusing a library across 90 videos a month. Third-party music → more Content ID claims |
| **Epidemic Sound** | Personal ~$10–11; **Pro ~$17**; Business ~$30 (Business+ ~$100) | Yearly is discounted | ~50k tracks plus SFX, human-composed, stems | None relevant | None | **Pro covers YouTube, Instagram, TikTok and Facebook, monetized, up to 3 channels per platform.** Content published while subscribed **stays cleared after cancelling** | Partner API ("Connect") by agreement only | Manual library | New uploads need an active subscription. Connect channels for Content ID whitelisting |
| **Adobe (Firefly / Creative Cloud)** | Firefly plans ~$10–20+; CC ~$55+ | Mostly annual | Firefly sound / music (credit based) | Firefly image and video (credits; partner models cost more) | No pro narrator | Commercially safe training claim | Firefly Services API is **enterprise**: reported ~$1,000/month minimum or $100–250 per 1,000 calls | Premiere / After Effects **cannot run headless on a Linux VPS** | Credits don't roll over. API contract minimums |
| **ElevenLabs** | Starter $6 (30k credits), Creator $22 (121k), **Pro $99 (600k)**, Scale $299 (1.8M), Business $990 | ~2 months free when annual | **Eleven Music** (trained on licensed catalogs; API ~$0.15–0.30/min) and **SFX generation** (~$0.12/min) | None | **Top blind-test tier** (Eleven v4/v3, ~1,340 Elo vs ~1,270 for Gemini Flash TTS). TTS API ~$0.08–0.10 per 1k chars (v2/v3/v4), $0.04–0.05 Flash | Paid plans include commercial rights, including monetized YouTube. Free plan does not | **Full self-serve REST API** for voice, music and SFX | **Yes**: pure HTTPS from the VPS | Credits are shared by voice, music and SFX; retakes use credits; overage on top tiers |
| **Runway** | App $12–76; **API $0.01/credit**: Gen-4 Turbo $0.05/s, Gen-4.5 $0.12/s | App: annual discount | No | Text/image → video, 5–10 s clips | No | Commercial on paid plans | Self-serve API | Yes (API) | **Billed whether or not you keep the clip.** Models are retired from the API without much notice (July 2026) |
| **Google Gemini API** (already in our stack for Charon TTS) | Pay as you go | — | No | **Nano Banana 2** ~$0.067 per 1K image, Pro ~$0.134; Veo / Omni ~$0.10/s | Gemini TTS Charon (~$7–20/month at our volume) | Commercial; Google claims no ownership of output | Self-serve API | Yes | Batch is half price for some image models |
| **Recraft** | API ~$0.08 per vector image (V4.1), Pro $0.30 | — | No | **Native SVG/vector illustration**, consistent brand styles | No | Paid plans: commercial (verify; one source says "restricted" for one model) | API | Yes | — |
| **Creatomate / Shotstack** (cloud render) | ~$41–99+ / ~$39–75+ | — | No | No | No | n/a | Render API | Calls from the VPS | **Per-rendered-minute.** About 555 min/month ≈ $110–170+/month, and less creative control than our engine |
| **Remotion** (React video framework) | **Free** for individuals and companies with ≤3 employees. Company license from $100/month min ($0.01/render) | — | No | No | No | n/a | Code framework | Yes (Node + Chrome on the VPS) | A full rewrite of our renderer in React/TypeScript. Self-hosted rendering needs Chrome and RAM |
| **Contabo VPS** | Cloud VPS 20: 6 vCPU / 12 GB / 100 GB NVMe, ~€7. **Cloud VPS 30: 8 vCPU / 24 GB / 200 GB NVMe, ~€14** | Small discount for 12-month term | — | — | — | — | — | — | Shared vCPU: steal time ranges from ~0% to 15–35% at peak in some reviews. **Benchmark our render on it.** VAT on top |

**Verdict on "one platform for everything".**
- **No single platform covers all 10 functions in a way a VPS can automate legally.**
- Artlist Max comes closest on *assets*: music, SFX, footage, AI image, video and voice. But:
  - its license **bans automated downloads**;
  - it has **no self-serve API**;
  - its AI quota is far below 90 videos a month;
  - it does no assembly, mixing or rendering.
- Envato has the same automation ban, plus per-project registration.
- Adobe's automation is enterprise-priced, and its editors don't run on Linux servers.
- **Assembly, captions, mixing and mastering at this volume are best done by our own engine**, which already does
  them with zero per-render cost.

## 2. Our engine vs the alternatives

| | **Current Python + FFmpeg engine** | Remotion (self-hosted) | Creatomate / Shotstack |
|---|---|---|---|
| Cost at 555 min/month | $0 (VPS only) | $0 (we qualify for the free license); more RAM | ~$110–170+/month |
| Editorial documentary style | Built: chapter cards, count-up figures, data charts from exact math, kinetic quotes, plates | Possible after a rewrite (web-quality motion graphics) | Template-bound |
| Narration-synced beats and captions | Built, sentence-timed | Rebuild | Limited |
| Audio mix (ducking, SFX cues, −14 LUFS master) | Built and measured | Still FFmpeg | Basic |
| Risk | Known code, 109 tests | Weeks of rewrite | Vendor lock-in, per-minute bills |

**Decision: keep and extend our engine.**
- Remotion is the only credible upgrade path. It is worth revisiting only if we later want browser-grade motion
  design (complex Lottie / 3D).
- Cloud render APIs cost more and give less control.

## 3. Final decision

### Best overall recommendation
**Our own renderer on the Contabo VPS, plus ElevenLabs, plus image generation via API.**

| Service | Role |
|---|---|
| Our engine | Editorial animation, data charts, captions, mixing, mastering, thumbnails, Telegram review |
| **ElevenLabs Pro** | One API and one license for **narration** (top-ranked US male voices, v4/v3), **music beds** (Eleven Music, licensed training data) and **sound effects** |
| **Google Nano Banana 2** (or Recraft vector) | Editorial illustration plates and thumbnail art, generated in our house style |
| Claude (existing, capped) | Scripts |

**Why this combination:**
- It is the **smallest set that is fully automatable and legally clean on a VPS**: 2 new paid services.
- Every function is an API call.
- Licenses explicitly cover monetized use.
- No bot-download violations.

### Best integrated platform (if you accept manual curation)
**Artlist Max.**
- It has the best single catalog: music, SFX, footage, plus AI tools.
- Use it only as a library that **a person downloads manually** (for example, 40 tracks and 200 SFX a quarter). The
  pipeline then reuses those files locally.
- It cannot be the automated backbone.

### Best quality combination
**ElevenLabs (voice), Epidemic Sound Pro (human-composed music and SFX), Nano Banana Pro (images), and our engine.**
- Human-composed music still beats AI music for a documentary feel.
- Epidemic offers channel whitelisting on YouTube, Instagram and TikTok.
- The music library is refreshed manually each month, about 30 minutes of work from your phone or PC.

## 4. Monthly budget for 30 long videos + 60 Shorts

| Item | Recommended | Best quality | Within the old $100 cap |
|---|---|---|---|
| Contabo Cloud VPS 30 (8 vCPU / 24 GB) | $16 | $16 | $16 |
| Claude scripts (hard cap in code) | $20–30 | $20–30 | $20–30 |
| Narration | ElevenLabs Pro **$99** (600k credits ≈ all narration + ~10% retakes) | ElevenLabs Pro $99 | Gemini Charon ≤ $20 |
| Music | Eleven Music (from Pro credits; library of ~60 tracks, ~$5–15 of credits) | **Epidemic Sound Pro ~$17** | Epidemic Pro ~$17 |
| SFX | ElevenLabs SFX (one-off library, < $5) | Epidemic (included) | Epidemic (included) |
| Images and thumbnail art (~900 images: 15/long, 3/Short, 3 thumbnail variants per video) | Nano Banana 2 ~$60 | Nano Banana Pro ~$120 | Reused library, ~$15 |
| AI video b-roll | **Not recommended** (see risks). If wanted: ~$0.10/s ≈ $120 for 20 min/month | — | — |
| **Total** | **≈ $200–215/month** | **≈ $275–290/month** | **≈ $90–100/month** |

**Notes on the budget:**
- Annual billing would cut ElevenLabs by about 2 months a year (≈ $82/month equivalent).
- **The recommended stack exceeds the earlier $100/month cap.** Approving it means raising the budget to about
  $215/month.
- The $100 variant keeps the same engine and look. It trades voice quality (Gemini Charon is a step below
  ElevenLabs in blind tests) and image freshness.

## 5. Licensing and copyright risks (ranked)

1. **YouTube "inauthentic content" policy (clarified July 2026).**
   - Mass-produced, templated and repetitive channels lose monetization at the *channel* level, AI or not.
   - Daily faceless finance videos are squarely in scope.
   - "AI personas related to sensitive topics" is a listed category, and finance is a sensitive (YMYL) area.
   - **This is the biggest business risk, larger than any music license.**
   - Mitigation:
     - human approval of every video (already enforced);
     - original research-backed scripts;
     - varied visuals per topic;
     - never re-uploading near-duplicates;
     - a consistent, transparent narrator identity.
2. **Automation clauses.**
   - Artlist and Envato forbid bot or programmatic downloads.
   - Fetching their assets from the VPS would breach the license, and could void it for every video.
   - Use only manual downloads, or API-licensed vendors.
3. **Subscription lapse.**
   - Epidemic and Artlist: videos published while subscribed stay cleared.
   - New uploads need an active plan.
   - Keep a per-video license log: track ID, date, plan.
4. **Envato per-project registration.** Each reused item must be licensed to each video. This is impractical at 90
   videos a month.
5. **Content ID claims.** Third-party-author libraries (Envato) are claimed most often. Epidemic and Artlist offer
   channel whitelisting, so connect all channels.
6. **AI music.**
   - Eleven Music says it was trained on licensed catalogs, so it is lower risk than Suno or Udio.
   - Pure AI output generally **can't be copyrighted**, so others may reuse it.
7. **AI images.**
   - Not copyrightable either.
   - Never generate logos, real people, bank brands or fake documents.
   - **Charts and numbers stay code-drawn from exact math, never AI-generated.**
8. **Platform AI labels.**
   - TikTok, Instagram and YouTube require disclosure of *realistic* synthetic media.
   - Our illustrated style generally doesn't trigger this.
   - Any AI video b-roll that looks real would.
9. **Voices.**
   - Use an ElevenLabs default (premade) or properly licensed voice. Community-library voices can be withdrawn by
     their owners.
   - Never clone a real person.

## 6. Migration plan (each step needs your approval; nothing changes until then)

| Phase | What | Cost to test | Exit criterion |
|---|---|---|---|
| 0 | Approve the budget level (recommended ~$215, quality ~$290, or $100) | — | Your decision |
| 1 | Benchmark our render on the **Contabo VPS 30** (one full 17-min editorial video plus 2 Shorts at peak hours) | VPS only | Daily set renders in under ~3 h with no OOM |
| 2 | ElevenLabs: 60-second sample with 3 candidate US male voices; pick one | Creator for 1 month (~$22), or free-tier test (non-commercial, for listening only) | You approve the voice |
| 3 | Add an `elevenlabs` narrator next to Gemini and Kokoro. Same budget cap, fallback chain and whole-video voice consistency (code exists for Gemini; same pattern) | Within the plan's credits | Tests plus one real long video |
| 4 | Music and SFX library: generate (Eleven Music) or download manually (Epidemic) about 60 beds tagged by mood, and 150 SFX. The pipeline picks by tag. The license log is written per video | ~$5–17 | The mix stays at −14 LUFS and the license log is complete |
| 5 | Illustration generator: house-style prompts → Nano Banana / Recraft plates, cached and reused; human-approved style sheet; charts stay code-drawn | ~$10 test | 30 plates approved |
| 6 | Platform exports: YouTube (16:9 + Shorts), Instagram Reels and TikTok (9:16, safe zones for the right-side UI, ≤60 s), sent to Telegram for approval. **Still no automatic upload** | $0 | 3 exports per Short pass a spec check |
| 7 | Two-week parallel run (old vs new stack on the same topics), then switch the default | Plan costs | You approve the switch |

**Managing from your Android phone:** unchanged and sufficient.
- Telegram for review, approve or reject, and alerts.
- An SSH app (for example Termius) for rare server tasks.
- Desktop editors (Premiere, CapCut) are not needed.
