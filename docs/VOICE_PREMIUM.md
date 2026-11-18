# Premium narration voice: comparison and recommendation (2026-11-18)

**Constraint:** at most $20/month for the voice. Nothing has been purchased and no paid API call has been made.
Prices come from web research on 2026-11-18, mostly third-party pricing summaries, and are linked below.
**Confirm on each provider's own pricing page before subscribing.**

## Our real monthly volume (MEASURED from GLIVARAO scripts)

| Item | Characters |
|---|---|
| Long video, 16.5 min (2,477 words) | 14,657 |
| Long video, 18 min (2,700 words, upper bound) | ~15,976 |
| Short (average of 24 generated) | 590 (max 701) |
| **30 long + 60 Shorts** | **≈475,000–522,000** |
| Plus 10% for re-renders and edits | **≈575,000** |

## Comparison

| Service | Price | Free allowance | Cost for our ~575k chars | Fits $20? | Notes |
|---|---|---|---|---|---|
| **Google Cloud TTS – Chirp 3 HD** | $30 / 1M chars | **1M chars/month reported**¹ | **$0 if the free tier applies; ≤ $17.25 if not** | **Yes, either way** | Pay as you go, no subscription. About 16 US male voices. Speaking rate 0.25–2×. Custom IPA pronunciations. API key. Output usable in media under the Google Cloud terms (no training of competing TTS)² |
| Azure AI Speech – Neural HD | $22 / 1M | none for HD³ | ≈ $12.65 | Yes | Strong US male HD voices (e.g. the Andrew and Davis families). Pay as you go. Runner-up |
| Azure AI Speech – standard Neural | $15 / 1M | 500k/month³ | ≈ $1.10 | Yes | Cheapest, but standard rather than HD quality |
| OpenAI gpt-4o-mini-tts | ≈ $0.015 / audio-min⁴ | none | ≈ $8–9 (≈ 540 min) | Yes | Takes style instructions (for example "documentary narrator"). **Requires clear disclosure that speech is AI-generated.** Commercial terms for preset voices are not clearly confirmed⁵ |
| Inworld TTS | $15–25 / 1M⁴ | trial | ≈ $9–14 | Yes | Newer provider, high benchmark rankings. Less established |
| **ElevenLabs** | Creator $22 = 121k credits; Pro $99 = 600k credits⁶ | 10k (no commercial licence) | **$99/month (Pro)** | **No** | Excellent quality, but our volume needs the Pro plan. The $22 Creator plan covers only about 7 long videos |

## Recommendation

**Service: Google Cloud Text-to-Speech, Chirp 3 HD.** It's the only top-tier natural voice that covers the
full 90-video month inside $20 even **without** counting the free tier. Billing is pay as you go, so there's
no subscription to cancel.

**Voice: `en-US-Chirp3-HD-Charon`** is the default candidate (Google's style label: "informative"). Three
alternates go into the listening test:

| Voice | Google's style label |
|---|---|
| `en-US-Chirp3-HD-Charon` | informative |
| `en-US-Chirp3-HD-Orus` | firm |
| `en-US-Chirp3-HD-Algenib` | gravelly (likely the deepest) |
| `en-US-Chirp3-HD-Sadaltager` | knowledgeable |

I can't listen to audio. "Deep, natural, documentary" has to be judged by ear from the comparison samples,
and the default switches to whichever voice you pick.

**Monthly character allowance:**
- Google reports the first **1,000,000 Chirp 3 HD characters each month as free**¹. Verify this on your
  billing account.
- GLIVARAO's own hard cap is set to **666,666 characters/month** ($20 at $30/1M, counting no free tier).
- If you confirm the free tier, setting `TTS_FREE_CHARS_PER_MONTH=1000000` raises the cap to 1,666,666.

**Estimated cost for the 90-video target:**
- **$0/month** if the free tier applies to your account;
- **$14.25–$17.25/month** if it doesn't;
- either way, never more than the $20 cap.

## What's built (and tested with a simulated API, no real calls)

- **`TTS_PROVIDER=google_chirp`** uses Chirp 3 HD. It works only when `ALLOW_PAID_APIS=true` and
  `GOOGLE_TTS_API_KEY` is set.
- **One narrator per video.** If the paid voice isn't approved, the key is missing, the month's cap would be
  exceeded, or the API fails part-way, **the whole video uses the Kokoro am_michael backup**. Voices are never
  mixed within a video, and the reason is recorded in the video's metadata and shown in the Telegram review.
- **Same pacing system as today:** sentence-by-sentence synthesis with GLIVARAO's pauses (sentence, question,
  emphasis, paragraph beat). Captions, lip-sync and animation cues stay synchronized.
- **Cache:** each sentence is stored by voice, rate and text, so re-rendering never bills twice.
- **Ledger:** `data/tts_usage.json` counts billed characters per month and enforces the cap.
- **Pronunciation:** IPA overrides for GLIVARAO, HELOC and FINRA. If the API rejects them, the request is
  retried as plain text.
- **Security:** the API key goes in a header, never in the URL or in error messages.

## To produce the comparison sample (needs your explicit approval)

```bash
python -m glivarao voice-sample --provider google_chirp --compare   # shows plan + cost; refuses without approval
```

The plan is 4 voices × 774 characters = **3,096 characters ≈ $0.09** (or $0 inside the free tier). Steps:
1. Create a Google Cloud project with billing enabled, enable the **Cloud Text-to-Speech API**, and create an
   API key restricted to that API.
2. Approve the run. I'll then:
   - enable `ALLOW_PAID_APIS` for the sample only;
   - save the key through the secure credential form (host `texttospeech.googleapis.com`, header
     `X-Goog-Api-Key`);
   - allow that host in this environment's network;
   - run the command and send you 4 files to compare with the Kokoro am_michael sample.

## To switch production after you pick a voice

```bash
TTS_PROVIDER=google_chirp
GOOGLE_TTS_VOICE=en-US-Chirp3-HD-<your pick>
ALLOW_PAID_APIS=true
TTS_MONTHLY_BUDGET_USD=20
```

Kokoro am_michael stays the automatic free backup. Uploading to YouTube remains manual and private-only; this
change doesn't affect that.

## Sources

1. Google Cloud TTS pricing (Chirp 3 HD $30/1M, first 1M free/month), third-party summaries:
   [developersdigest](https://www.developersdigest.tech/models/speech/google-cloud),
   [costbench](https://costbench.com/software/ai-voice-tools/google-cloud-text-to-speech/),
   [openapipricing](https://openapipricing.com/blog/tts/google-cloud-text-to-speech).
   Voices and controls: [Google Cloud docs: Chirp 3 HD](https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd),
   [release notes](https://docs.cloud.google.com/text-to-speech/docs/release-notes).
2. Usage of generated audio:
   [Google Developer forum: commercial usage of Cloud TTS](https://discuss.google.dev/t/commercial-usage-of-google-cloud-tts/91316),
   [Text-to-Speech API licence thread](https://discuss.google.dev/t/text-to-speech-api-license/187973).
3. Azure: [texttolab](https://texttolab.com/blog/azure-text-to-speech-pricing),
   [Microsoft Tech Community: Neural HD updates](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/azure-speech-%E2%80%93-neural-hd-text-to-speech-recent-voice-updates/4505380),
   [Cartesia summary](https://www.cartesia.ai/learn/top-microsoft-azure-text-to-speech-alternatives).
4. Inworld, Cartesia, OpenAI: [texttolab Inworld](https://texttolab.com/blog/inworld-pricing),
   [texttolab OpenAI](https://texttolab.com/blog/openai-tts-pricing),
   [vsref Cartesia vs Inworld](https://www.versusref.com/tts/cartesia-vs-inworld-tts/).
5. OpenAI disclosure requirement: [OpenAI service terms](https://openai.com/policies/service-terms/),
   [developer forum](https://community.openai.com/t/where-is-the-usage-policy-for-ai-voiceovers/679737).
6. ElevenLabs plans: [Cartesia: ElevenLabs pricing](https://www.cartesia.ai/learn/elevenlabs-pricing),
   [flexprice](https://flexprice.io/blog/elevenlabs-pricing-breakdown),
   [felloai](https://felloai.com/elevenlabs-pricing/).
