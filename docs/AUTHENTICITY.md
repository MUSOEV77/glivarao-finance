# How GLIVARAO keeps the channel authentic (YouTube "inauthentic content" policy)

YouTube can demonetize channels whose videos are mass-produced, templated or repetitive, whether or not AI is
used. GLIVARAO now builds every video around **your choices and your own words**, with real variety and
checked facts. These are not tricks: they are the human input and editorial standards the policy is asking for.

## Your week, in practice

| When | What happens | What you do |
|---|---|---|
| **Sunday ~10:07 ET** | Telegram brings 5–7 topic ideas from the week's research, each with ✅ / ✖ | Tap ✅ on the ones you want (about 3) |
| Right after you tap ✅ | GLIVARAO picks a format and asks for **your take** | Reply with a few sentences or a **voice note**: your opinion, a personal experience, or an example. Tap 🔁 for a different format |
| Next morning, 04:17 ET | If the pace allows (3 long videos a week, at least 2 days apart), it writes, checks and renders the long video + 2 Shorts | — |
| After rendering | The review package arrives: video, thumbnail, title, description, **fact check**, **originality report**, **AI disclosure** | Approve or reject. Approving uploads nothing |
| When you choose | — | Upload manually (always private), then publish in YouTube Studio |

Send **/queue** to the bot at any time to see what's waiting.

**Nothing is made without you:**
- no picked topic means no video;
- no input from you means no video;
- the bot reminds you instead.

## The 8 changes

1. **Topics are chosen by you.**
   - Research only *suggests* (`propose-topics`, weekly).
   - A topic is produced only after you tap ✅. Automatic topic picking is switched off (`TOPIC_MODE=queue`).
2. **Your input is in every video.**
   - Your text or voice note becomes a **"My take"** scene, with its own on-screen card.
   - Voice notes are transcribed on the server (free, local, via faster-whisper), and you get the transcript back
     to correct.
   - With the Claude writer, your words are woven in faithfully and the rest of the script connects to them.
   - Any numbers you mention are flagged for you to confirm.
3. **Six formats, rotated.**
   - The formats are: Explainer, Myth vs Fact, Case study (clearly hypothetical person), Viewer question (a real
     public question), Comparison (Option A vs B), and What changed (new consumer-finance data or rules only,
     never politics or market news).
   - Each format has its own structure, its own opening and closing lines (rotated, never reused recently) and its
     own on-screen cards: MYTH / FACT stamps, CASE FILE, A/B badges, VERDICT, WHAT CHANGED, YOU ASKED, MY TAKE.
   - The format is never the same twice in a row.
4. **Anti-repetition check.** Every script is compared with earlier videos:
   - the same topic in the same format (60 days);
   - the same structure;
   - repeated 8-word phrases (more than 25% fails);
   - a near-identical opening.

   If it's too similar, it is **rewritten**: the Claude writer gets the reasons and the repeated phrases; the free
   writer switches wording or format. If it is still too similar, it is **not rendered**, and the report says why.
5. **Fact check.**
   - Every sentence with a number is listed in the review message with its source: 🔗 research link,
     🧮 calculation, 📘 official reference, 🗣 your input. ⚠️ means **no source**.
   - All source links go into the YouTube description.
   - The full list is attached as `fact_check.md`.
6. **Shorts with their own idea.**
   - Each Short gets a different kind (one number, myth, mistake, viewer question, or tip), its own hook, and its
     own single point. It is not a cut of the long video.
   - The two Shorts never share a hook, and never reuse the long video's opening.
7. **Pace: quality over quantity.**
   - Default: 3 long videos a week, at least 2 days apart, plus 2 Shorts each.
   - To change it, set these in `.env` (see the commands below): `LONG_VIDEOS_PER_WEEK`, `MIN_DAYS_BETWEEN_LONG`,
     `SHORTS_PER_LONG` and `TOPIC_IDEAS_PER_WEEK`.
8. **AI disclosure.**
   - **YouTube:** the "altered or synthetic content" setting is **No** for our videos. They are illustrated, show
     no realistic people or events, and use a generic narrator voice that imitates nobody. YouTube's rules target
     realistic content.
   - It switches to **Yes** automatically if realistic AI visuals or a real person's voice are ever used. The
     manual upload sends this setting.
   - **Every description** includes a plain note: AI narration voice, illustrated visuals, AI-assisted research and
     script, reviewed by a person, and "My take" is the host's own view.
   - **TikTok / Instagram:** they ask you to label realistic AI audio. The review message reminds you to switch
     their AI labels ON when you post there.

## Unchanged

- Spending caps: Claude $30/month, voice $20/month. Paid APIs only run with `ALLOW_PAID_APIS=true`.
- Nothing is uploaded, published or scheduled automatically. Manual upload is always private.

## Honest limits

- **Full-length variety needs the Claude writer.**
  - The free writer builds scripts from a reviewed library.
  - Over weeks, the anti-repetition check will start blocking free-writer scripts on topics in the same family.
    That is the check doing its job.
- **Voice notes** need `faster-whisper` on the server. The installer tries to add it; the model downloads once,
  about 150 MB. If it's missing, the bot asks for text.
- **Voice notes and live Telegram** are untested here. The real voice-note transcription and the real Telegram
  were not available in the test environment: the flows were tested with a local stand-in for Telegram and a
  simulated transcriber.

## Settings (`deploy/set-key.sh NAME value`)

```
TOPIC_MODE=queue            # queue = only topics you pick (auto exists for development only)
REQUIRE_CREATOR_INPUT=true  # no video without your take
LONG_VIDEOS_PER_WEEK=3
MIN_DAYS_BETWEEN_LONG=2
SHORTS_PER_LONG=2
TOPIC_IDEAS_PER_WEEK=6      # 5-7
SIMILARITY_MAX_PHRASE=0.25
SIMILARITY_MAX_STRUCTURE=0.85
```
