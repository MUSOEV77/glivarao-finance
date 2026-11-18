# GLIVARAO narration voice

**Primary narrator (owner-approved 2026-11-18): Kokoro `am_michael`.** An American English male voice that
runs locally on the server: free, no API key, Apache-2.0 licence. It narrates every long video and every
Short, so the channel always has the same voice.

| Setting | Value | Where |
|---|---|---|
| Provider | `TTS_PROVIDER=kokoro` (default) | `.env` |
| Voice | `KOKORO_VOICE=am_michael` (default) | `.env` |
| Approved backups | `am_fenrir`, `am_puck` (backup only; any other voice is refused in code) | `glivarao/tts/kokoro.py` → `APPROVED_VOICES` |
| Pace | speed 0.98 (≈133 wpm average including pauses; faster within sentences) | `DEFAULT_SPEED` |
| Pauses | sentence 0.42 s · question 0.55 s · emphasis +0.12 s · paragraph break +0.30 s | `KokoroEngine.narrate` |
| Emphasis | wrap words in `*asterisks*` in scripts: slightly slower delivery and a longer pause | scripts |
| Paid voices | ElevenLabs / Google refused unless `ALLOW_PAID_APIS=true` (owner approval) | `glivarao/tts/__init__.py` |
| Placeholder voices | espeak and silent refused in production mode | `glivarao/tts/__init__.py` |

## Pronunciation

Pronunciation comes from misaki, Kokoro's own dictionary (espeak is not used). It is backed by:
- a **finance text normalizer**: 401(k), 403(b), 529, S&P 500, W-2, 1099, YoY, fractions, US, $K/$M/$B, and
  number ranges;
- an **explicit lexicon** for words the dictionary misses or misreads: GLIVARAO, Roth, FICO, HELOC, FINRA,
  Equifax, Experian, Zelle, Venmo, Interac, Klarna, Afterpay, Schwab, Wealthsimple, Questrade, Robinhood,
  Nasdaq, Vanguard, annuity and amortization.

An audit of about 60 finance terms (acronyms, brands, dollar amounts, percentages, years, ranges) showed no
words falling back to guesswork. Any new word the dictionary doesn't know is listed in each video's
`metadata.json` (`pronunciation_misses`) for review.

**Brand name.** "GLIVARAO" is currently pronounced **"gli-VAR-oh"** (`ɡlɪvˈɑɹO`). This awaits owner
confirmation. To change it, edit `LEXICON["glivarao"]`.

## Audio chain

1. **Narrator voice processing:**
   - 75 Hz high-pass (removes rumble);
   - +1.5 dB at 160 Hz (warmth);
   - −1.5 dB at 380 Hz (less boxy);
   - +1.8 dB at 3.2 kHz (presence);
   - a de-esser;
   - gentle 2.5:1 compression.
2. **Music bed:** original, synthesized in code. It sits about 14 dB under the voice and ducks a further
   ~8 dB while the narrator speaks.
3. **Sound effects:** synthesized in code, cued to animation events.
4. **Master:** −14 LUFS integrated, true peak capped at −1.5 dBTP. Float processing with 4× oversampled
   limiting means nothing clips.

## Approval sample

`python -m glivarao voice-sample` renders `config/samples/voice_sample_60s.txt`, a real finance script whose
claims are sourced in `config/samples/voice_sample_60s.sources.md`.

Result: 62.6 s · −14.2 LUFS · −2.0 dBTP · 0 clipped samples · voice 14.2 dB above the music · 0
pronunciation misses.
