# Credentials and infrastructure checklist

Nothing below has been bought or created. Each item needs the channel owner's action.
Put the values in `.env` (copy it from `.env.example`). Never commit `.env` or `secrets/`.

| Need | Variable(s) | Where to get it | Cost (check current pricing) | Required? |
|------|-------------|-----------------|------------------------------|-----------|
| Script writing | `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys | Pay per use. One 17-minute script is roughly 5k input tokens and 8–15k output tokens. | **Yes** |
| Narration voice (option A) | `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | elevenlabs.io → choose a US-English male voice whose license allows commercial YouTube use | Paid subscription, billed by characters. About 75k characters a day for 1 long video + 2 Shorts, so roughly 2.3M a month. | One of A or B |
| Narration voice (option B) | `GOOGLE_TTS_API_KEY`, `GOOGLE_TTS_VOICE` | Google Cloud console → enable Text-to-Speech API → API key restricted to that API | Pay per character, with a free tier | One of A or B |
| Real economic charts | `FRED_API_KEY` | fredaccount.stlouisfed.org → API Keys | Free | Recommended |
| Approval bot | `TELEGRAM_BOT_TOKEN` | Telegram → @BotFather → /newbot | Free | **Yes** |
| Approver identity | `TELEGRAM_APPROVER_CHAT_ID` | Send your bot a message, then call `getUpdates` and read `message.chat.id` | — | **Yes** |
| YouTube upload, captions and analytics | `secrets/client_secret.json` | Google Cloud console → enable *YouTube Data API v3* and *YouTube Analytics API* → OAuth consent screen → create a **Desktop app** OAuth client → download the JSON | Free (quota-limited) | **Yes**, to publish |
| YouTube authorization | `secrets/youtube_token.json` | Run `python -m glivarao youtube-auth` and sign in as the channel owner | — | **Yes**, to publish |
| Publish switch | `YOUTUBE_PUBLISH_ENABLED=true` | Turn on only after you have reviewed test videos | — | Off by default |

## Notes

- **YouTube API audit.** Videos uploaded through an unverified API project are locked to private. To
  publish publicly through the API, the Google Cloud project must pass YouTube's API compliance audit.
  Until then, the pipeline uploads as private and you make videos public in YouTube Studio.
- **Custom thumbnails** require a verified channel (phone verification in YouTube Studio).
- **Server.** Any Linux host with Python 3.11+ and ffmpeg (libx264 and libass) will do. 2–4 vCPUs render a
  17-minute video in about 10 minutes (see `docs/TEST_REPORT.md`). Leave about 2 GB of disk per day of
  output, or prune old files.
- **Voice rights.** Use only stock or licensed voices, or your own voice clone. Never clone a real
  person's voice without written consent.
