# TTSMaker evaluation for GLIVARAO Finance narration (2026-11-18)

**Scope.**
- Evaluation only: nothing was purchased and no production code was changed.
- Real API calls used only TTSMaker's **public demo key**, spending about 900 characters of that shared demo quota.

## What was actually tested

| Test | Result |
|---|---|
| API reachable from our stack (`api.ttsmaker.com`, REST + JSON) | ✅ Works. The live endpoints are `/v2/get-voice-list`, `/v2/get-token-status` and `/v2/create-tts-order` (the docs' `/v1` paths return 404) |
| Voice catalog | ✅ 120 English voices, **31 US male voices** |
| Per-request limit | 20,000 characters per request (from the API) |
| Output | WAV / MP3 download URL. **24 kHz mono for most voices, 16 kHz for "Miles"** (lower bandwidth). Files **expire after 24 h**. Audio is served from at least 6 file hosts (s2c1, s4, s5-1, s5-9, s5-10, s6 plus a backup host) |
| Rate limit | 5 requests per second (documented) |
| **Our own text** (long scripts, financial terms, pauses, emotion) | ❌ **Not testable without paying.** The demo key refuses custom text (`TEXT_MISMATCH_DEMO_API_KEY`) and speaks only one fixed sentence |
| 14 candidate US male voices on that fixed sentence | ✅ Generated and measured (below). Files: `output/tts_eval/listen/` |

## Objective measurements (fixed demo sentence, 11 words)

| Voice (id) | Sample rate | Median pitch (lower = deeper) | Intonation range | Notes |
|---|---|---|---|---|
| **Whitaker (2665)** | 24 kHz | **104 Hz** | 7.9 semitones | Deepest |
| **Peter (147)** | 24 kHz | 111 Hz | 9.1 st | Deep; marked "Hot + Unlimited" |
| *Kokoro am_michael (our free voice)* | 24 kHz | 118 Hz | 7.7 st | Reference |
| Anthony (2569) | 24 kHz | 121 Hz | 8.6 st | |
| **Ethan (2702)** | 24 kHz | 122 Hz | **14.0 st** | Most expressive |
| Gary (2560) | 24 kHz | 124 Hz | 5.7 st | Flattest |
| Matthew (2593) | 24 kHz | 133 Hz | 10.2 st | |
| Miles / Miles V2 (777 / 1777) | **16 kHz** | 135 Hz | 10.6 st | The two returned identical audio |
| Ryan (2567) | 24 kHz | 136 Hz | 12.3 st | |
| Jacob, Clyde, Mason, James, Michael | 24 kHz | 139–212 Hz | 6–13 st | Lighter voices |

**What these measurements can't tell us:**
- I can't listen to audio, so naturalness can't be judged here. These numbers describe depth and intonation only.
- **Listen to the 15 files yourself.** All of them say the same sentence. One is our current Kokoro voice, as a
  baseline.

## Monthly character consumption (exact formula)

Our measured narration rate is **14.7 characters per second**, spaces and punctuation included. Billing counts
input characters.

| | Per video | × count | Month |
|---|---|---|---|
| Long, 15 min | 13,230 | × 30 | 396,900 |
| Long, 16.5 min (typical) | 14,553 | × 30 | 436,590 |
| Long, 18 min | 15,876 | × 30 | 476,280 |
| Short, 30 s | 441 | × 60 | 26,460 |
| Short, 45 s (typical) | 662 | × 60 | 39,690 |
| Short, 60 s | 882 | × 60 | 52,920 |
| **Total** | | | **423,360 – 529,200 (typical 476,280)** |
| **+10% retakes** | | | **≈ 466,000 – 582,000** |

**Fit with TTSMaker's plans:**
- The official Pro plan (1,000,000 characters a month) covers this about twice over.
- A whole long script (≤ 15,876 characters) even fits under the 20,000-character per-request limit.

## Pricing and limits

**Official (pro.ttsmaker.com, as reported by search):**

| Plan | Price | Notes |
|---|---|---|
| Lite | $8/month promo ($12.99 list) | |
| **Pro** | **$24/month promo ($29.99 list)** | 1,000,000 characters a month |
| Studio | $120/month | |

**"Pro Max"** (about $32.99, 1.2M characters) appears only on third-party sites. It looks like an older tier name.

**⚠️ The official Pro FAQ says the TTSMaker Pro API is "currently in the development phase".**
- The working API is the separate ttsmaker.com developer API.
- Its paid "dedicated API key" pricing is not published. The demo account itself shows a yearly character quota.
- **So whether "TTSMaker Pro Max API" can generate our daily narration can't be verified: the Pro API doesn't exist
  yet, and the developer API's price is unpublished.**

## Licensing

- The **official Pro FAQ** says Pro output may be used on YouTube, social media and commercial projects, and that
  users have "100% copyright ownership".
- The only Terms of Service page found is marked historical (2023-10-01). It refers to separate commercial-license
  terms that weren't retrievable.
- **Not established:** where the voices come from. Several voice names match voices sold by larger providers
  (for example "Fable", "Steffan/Stefan").
  - If TTSMaker resells third-party engines, our rights depend on its upstream agreements, which aren't published.
  - This is an unverified risk, not a finding.
- YouTube, Instagram and TikTok monetization depends on the platforms' own policies (inauthentic / mass-produced
  content), not on the TTS license.

## Comparison

| | TTSMaker | ElevenLabs | Google (Chirp 3 HD / Gemini Flash TTS) | OpenAI TTS |
|---|---|---|---|---|
| Independent blind ranking (Artificial Analysis Speech Arena) | **Not ranked anywhere** | Ranked: Eleven v3 ~1,177–1,210 Elo in 2026 snapshots; v4 newer | Gemini Flash TTS ranked ~1,206–1,260; Chirp 3 HD not ranked | tts-1 not near the top; one source reports **all OpenAI TTS models shut down 6 Jan 2027** (unconfirmed) |
| Style or emotion control | "V2 Multi-Emotion" variants for a few voices | Strong (v3 audio tags) | Strong (plain-English style prompts) | Instructions (gpt-4o-mini-tts) |
| Custom pronunciation (APR, FICO, Roth, 401(k), GLIVARAO) | **None documented** (respelling only) | Pronunciation dictionaries | Chirp: IPA custom pronunciations; Gemini: respelling | Respelling |
| Our volume (~500k characters) | ~$24/month (Pro), **but no Pro API yet** | Pro $99 | Gemini ~$7–20 (already integrated, $20 cap) | ~$7.50–15 |
| API fit with our engine | Feasible (REST → WAV URL → our master chain) but unverified on paid keys | Yes | **Already built and tested with simulated calls** | Yes |

## Recommendation

**Do not replace ElevenLabs or Gemini with TTSMaker.**

1. The **Pro API is officially not available yet**, and the developer API's paid terms are unpublished. So it can't
   reliably run 1 long video + 2 Shorts a day today.
2. **No independent blind test includes TTSMaker.** Our only professional-quality evidence for it is its own
   marketing.
3. **No pronunciation lexicon.** We rely on one for finance terms, and our IPA lexicon wouldn't carry over.
4. Licensing provenance is unclear, compared with providers whose terms are explicit.
5. The only advantage is price, and Gemini Charon is already cheaper at our volume, integrated, and capped at $20.

**If you still want a definitive TTSMaker test:**
- One month of Lite or Pro ($8–24) would let me run the full test with our real text:
  - a 17-minute script;
  - our 60+ finance terms;
  - pauses and emotion.
- That requires your approval, and a TTSMaker confirmation that the subscription includes an API key.
- The two candidate voices to test would be **Whitaker (2665)** and **Peter (147)**, the deepest, plus **Ethan
  (2702)**, the most expressive.

## Integration sketch (not implemented)

A `ttsmaker` narrator would follow the existing Gemini pattern (about 80 lines):
- one request per scene (≤ 20,000 characters, ≤ 5 requests/second);
- download the WAV immediately (URLs expire in 24 h), with fallback to the backup host;
- recover sentence timing with the existing `split_by_pauses`;
- the same voice mastering chain;
- a character ledger with a monthly cap;
- automatic fallback to Kokoro, never mixing voices within a video.

**VPS needs:** outbound HTTPS to `api.ttsmaker.com` and to its several `*.ttsmaker-vip-file.com` file hosts.

## Sources

- [TTSMaker API docs](https://ttsmaker.com/developer-api-docs)
- [TTSMaker Pro pricing](https://pro.ttsmaker.com/pricing)
- [TTSMaker Pro FAQ](https://pro.ttsmaker.com/faq)
- [TTSMaker terms (historical)](https://ttsmaker.com/terms-of-service)
- [Third-party price listing](https://costbench.com/software/ai-voice-tools/ttsmaker/)
- [Independent review](https://aumiqx.com/learn/ttsmaker-free-text-to-speech-review-2026/)
- [Artificial Analysis Speech Arena](https://artificialanalysis.ai/text-to-speech/leaderboard)
- [Leaderboard snapshot (Sep 2026)](https://www.digitalapplied.com/blog/best-text-to-speech-models-september-2026-ranked-priced)
- [OpenAI TTS pricing and shutdown note](https://www.activepieces.com/blog/openai-tts-pricing-cost-per-model-2026-guide.md)
