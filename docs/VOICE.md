# The channel voice (locked): Gemini TTS "Charon"

Every GLIVARAO video, long and Short, is narrated by **one voice**: Google Gemini TTS, prebuilt voice
**Charon**. There is **no fallback voice**: if Charon can't be used, the video waits instead.

## What is locked (in `.env` on the VPS)

| Setting | Value | Why |
|---|---|---|
| `TTS_PROVIDER` | `gemini_tts` | the only channel voice |
| `GEMINI_TTS_MODEL` | `gemini-3.8-flash-tts` | Google's **stable** TTS model ID, pinned. Names containing "latest", "preview" or "exp" are refused, because those aliases can point to a new model (and a different sound) without notice |
| `GEMINI_TTS_VOICE` | `Charon` | the narrator |
| `GEMINI_TTS_PACE` | `measured` | Gemini has no numeric speed setting; the pace is part of the fixed direction prompt (`slow`, `measured`, `brisk`) |
| `GEMINI_TTS_STYLE` | warm, deep, confident documentary narrator (built-in default) | the delivery style |

**Changes are blocked.** The first narration records a fingerprint of these settings. If any of them changes
later, nothing is narrated: the videos go on hold, and Telegram tells you what changed. If you really mean to
change the voice settings, confirm on the server:

```
cd /opt/glivarao/app && sudo -u glivarao .venv/bin/python -m glivarao voice-lock --reset
```

## Choosing (or changing) the voice: the audition

```
cd /opt/glivarao/app && sudo -u glivarao .venv/bin/python -m glivarao voice-audition
```

**How it works:**
- The same 30-second script is voiced by **Puck, Sadachbia, Fenrir, Achird and Charon (+15%)**, all with an
  energetic YouTube-explainer style prompt.
- Gemini has no numeric speed setting, so each sample is measured, then sped up or slowed down without changing
  pitch so it lands at about **170 words per minute** (`TTS_TARGET_WPM`).
- Each sample arrives in Telegram as audio, labelled with its words per minute, with a **✅ Use …** button.

**Tapping a button:**
- locks that voice in `.env`: `GEMINI_TTS_VOICE`, `GEMINI_TTS_PACE=energetic`, `GEMINI_TTS_STYLE` and
  `GEMINI_TTS_SPEED` (the speed factor measured for that voice);
- resets the voice lock on purpose;
- lets the hourly retry re-voice every video on hold with the new voice.

You can also do it from the server: `python -m glivarao voice-pick Puck`.

**Scripts are sized for 170 words per minute:** long videos are 2,550–3,100 words (15–18 minutes) and Shorts
85–170 words.

**Cost:** about 2–3 cents for all five samples, counted in the $20 voice budget. Re-voicing the held videos with a
new voice costs that voice's normal audio price once.

## If Gemini fails

1. **Temporary errors** (network, rate limit, Google server errors) are retried with backoff: 5, 10, 20, 40 and
   80 seconds. When Google says how long to wait, that wait is used.
2. **Still failing,** or a permanent error (key rejected, model retired, billing off), or the monthly cap is
   reached: the video is **put on hold**.
   - It stays scripted and checked.
   - You get one Telegram alert (⏸ ON HOLD) with the reason.
   - Nothing is made with another voice.
3. Videos on hold are **retried every hour**, and before every daily run. When Charon works again, the review
   arrives as usual, with a ▶️ message.
4. Scenes already narrated are cached, so a retry never pays twice for the same audio.
5. Your buffer of approved, scheduled videos covers the schedule while a video is on hold.

## Budget: $20 a month, alert at 80%

- **Before every video,** the whole video's cost is estimated at conservative rates ($18 per 1M audio tokens and
  32 tokens per second). If it would pass $20 this month, the video goes on hold.
- **Actual spend** is recorded from Google's own usage numbers.
- **Telegram alerts:** one at **80%** ($16), and one when the cap is reached. At the cap, videos stay on hold until
  the next month starts.
- **Expected spend at 16 long + 90 Shorts a month:** about 5.5 hours of narration, roughly $9–11 a month at the
  2027 price. That leaves room for re-renders.
- **Prices:** third-party sources report $9 per 1M audio tokens in 2026 and $18 from January 2027. The cap
  already uses $18. Check Google's pricing page once and update `GEMINI_TTS_PRICE_PER_M_AUDIO` if it differs.

`voice-lock` (command above) shows the lock, this month's spending and any videos on hold.
