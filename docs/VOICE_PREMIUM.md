# GLIVARAO premium narrator: final selection (2026-11-18)

> **Superseded (voice lock):** the channel voice is now locked to Gemini TTS "Charon" with no fallback voice. See `docs/VOICE.md`.


## Selected voice

**Google Gemini TTS: model `gemini-3.8-flash-tts`, voice `Charon`, with style direction "warm, deep, confident
American male documentary narrator explaining personal finance".**

Kokoro `am_michael` stays as the free automatic backup. Nothing has been purchased and no paid call has been made.

## How it was chosen (quality first, then budget)

I can't listen to audio, so the choice rests on **blind human-preference tests**, where listeners vote without
knowing the provider. That rules out choosing by popularity or brand.

| Model (Artificial Analysis Speech Arena, provider voices; snapshots vary) | Elo | Our 90-video month | Within $20? |
|---|---|---|---|
| ElevenLabs Eleven v4 / v4 Turbo | ~1,340 | needs the $99 Pro plan (600k credits) | ✗ |
| Cartesia Sonic 3.6 | ~1,273–1,282 | needs the $49 plan (1.25M credits) | ✗ |
| **Google Gemini 3.8 Flash TTS** | **~1,260–1,283** | **$7–$11 now (≤ $22.55 worst case after a reported 2027 price doubling, capped at $20 in code)** | **✓** |
| Inworld Realtime TTS-2 | ~1,270 | ≈ $13–$14 ($25/1M chars) | ✓ |
| Speechify Simba 3.2 | ~1,241 | ≈ $4 | ✓ |
| Google Chirp 3 HD (previous suggestion) | not ranked in any source found | ≈ $0–$17 | ✓, but no blind evidence, so it was replaced |

**Decision between the two in-budget leaders.** Gemini and Inworld are statistically tied on naturalness (an
independent blind study found the top 8 English voices tied). The deciding factors:

1. **Style direction in plain English.** Gemini accepts instructions such as "documentary narrator, measured
   pace, subtle emphasis on figures". That directly targets your brief: warm, confident, natural pauses,
   expressive but not exaggerated.
2. **A clearly American, professional male voice.** Charon is Google's "informative" male voice and is listed
   under VoiceRankings' "male professional" voices. Inworld's deepest male voices are described as "gruff"
   (Hades), British (Ronald) or unconfirmed as American.
3. **Price protection without changing the voice.** The same Charon voice exists on the cheaper Gemini 3.8
   Flash-Lite TTS. Near the cap, GLIVARAO switches model, not narrator.
4. **Terms.** Under the Gemini API terms, Google claims no ownership of generated content. On the paid tier,
   prompts aren't used to train models.

**Why Charon among Gemini's male voices:**
- Google's own labels: Charon "informative", Orus "firm", Algenib "gravelly", Sadaltager "knowledgeable".
- "Informative" plus warm style direction is the closest fit to a finance documentary narrator.
- "Gravelly" risks sounding rough over 17 minutes; "firm" risks sounding stern.
- **No per-voice blind ranking exists** in the sources found, so one listening sample should confirm the choice.

## Exact cost and billing (MEASURED volume × published prices)

- **Volume (measured from GLIVARAO scripts):** 475,000–522,000 characters per month, about 540–593 minutes
  of speech. Our own pauses are inserted as silence and never billed.
- **Billing basis:** per audio token. Google states 25 tokens per second of audio; one third party measured 32.

| Volume | at $9/1M (2026 rate) | at $18/1M (reported 2027 rate) |
|---|---|---|
| 475k chars, 25 tok/s | $7.29 | $14.58 |
| 522k chars, 32 tok/s | $10.25 | $20.50 |
| 574k chars (+10% edits), 32 tok/s | $11.28 | $22.55 |

Input text adds about 144k tokens a month, a negligible amount.

**What the code guarantees:**
- Defaults use the conservative $18 and 32 tok/s figures.
- Spending is tracked in USD from Google's own usage metadata.
- The hard cap is **$20/month**.
- If a video would cross the cap, it uses **Charon on Flash-Lite** (about half price, same voice). If that
  can't fit either, the whole video uses Kokoro am_michael.
- **Monthly spend cannot exceed $20.**

**Billing requirements:**
- A Google Cloud project with **billing enabled**. The paid tier is needed so prompts aren't used for
  training.
- A **Gemini API key** from Google AI Studio for that project.
- Pay as you go, with no subscription.
- Also set a **$20 budget alert** in Google Cloud Billing as a second safety net.

**Prices conflict between Google's own pages ($9 vs $4.50 per 1M audio tokens).** The first approved call's
usage metadata will confirm real cost per minute, and the config is then set to the real rate.

## Confirmation sample (needs your approval)

```bash
python -m glivarao voice-sample --provider gemini_tts   # prints plan + cost; refuses without approval
```

- Script: `config/samples/voice_sample_60s.txt` (792 characters).
- Cost: **about $0.012–$0.031** (1–3 cents).
- To run it:
  1. enable billing and create a Gemini API key;
  2. approve the run;
  3. I set `ALLOW_PAID_APIS=true` for the sample, save the key via the secure credential form (host
     `generativelanguage.googleapis.com`, header `x-goog-api-key`) and allow that host in the environment's
     network;
  4. I run the command and measure the result (loudness, pace, timing, clipping), confirm the real cost from
     usage metadata, and send you the file.

## Switching production after the sample is confirmed

```bash
TTS_PROVIDER=gemini_tts
GEMINI_TTS_VOICE=Charon
ALLOW_PAID_APIS=true
TTS_MONTHLY_BUDGET_USD=20
```

Everything else is unchanged: Telegram review and approval, manual private-only YouTube upload, and no
automatic publishing or scheduling.

## Implementation notes

- **Whole scenes per request,** for natural cross-sentence rhythm. Sentence timings for captions and animation
  are recovered from the pauses in the audio, with a proportional fallback.
- **Brand respelling:** "Gli-VAR-oh", since prompt-based models don't take IPA.
- **Unverified until the first approved call:** the model IDs `gemini-3.8-flash-tts` and
  `gemini-3.8-flash-lite-tts`. Sources name them inconsistently, so both are configurable. A wrong ID returns
  an error (no charge) and the video falls back to Kokoro.
- Google Chirp 3 HD support stays in the code as an alternative provider (`TTS_PROVIDER=google_chirp`).

## Sources

- Blind rankings: [Artificial Analysis TTS leaderboard](https://artificialanalysis.ai/text-to-speech/leaderboard),
  [provider-voice board](https://artificialanalysis.ai/text-to-speech/leaderboard/provider-voice),
  [benchmarklist snapshot](https://benchmarklist.com/arenas/artificial_analysis_provider_voice/),
  [Speko blind test: "most natural is an eight-way tie"](https://benchmarks.speko.ai/blog/most-natural-is-a-tie/),
  [Speechify on AA Elo](https://speechify.ai/blog/artificial-analysis-tts-leaderboard-elo-explained) (vendor).
- Gemini TTS pricing and voices: [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing),
  [neomanex: 3.8 Flash TTS $9, doubling on 1 January](https://neomanex.com/news/gemini-3-8-flash-tts-flash-lite-tts-api-pricing),
  [mxchat: measured tokens/second](https://mxchat.ai/gemini-tts-pricing-tokens-per-second/),
  [Firebase: Gemini speech generation and style](https://firebase.google.com/docs/ai-logic/generate-speech),
  [Google Cloud: Gemini TTS](https://cloud.google.com/text-to-speech/docs/gemini-tts),
  [VoiceRankings: male professional voices](https://voicerankings.com/voices/styles/professional/male).
- Terms: [Gemini API Additional Terms of Service](https://ai.google.dev/gemini-api/terms).
- Inworld: [pricing](https://inworld.ai/pricing), [voice listings](https://voicerankings.com/voice/inworld-tts-2/male),
  [Cloudflare model page](https://developers.cloudflare.com/ai/models/inworld/tts-2/).
- ElevenLabs and Cartesia plans: [Cartesia: ElevenLabs pricing](https://www.cartesia.ai/learn/elevenlabs-pricing),
  [vsref: Cartesia vs Inworld](https://www.versusref.com/tts/cartesia-vs-inworld-tts/).
