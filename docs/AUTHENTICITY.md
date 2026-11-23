# How GLIVARAO keeps the channel authentic (YouTube "inauthentic content" policy)

YouTube can demonetize channels whose videos are mass-produced, templated or repetitive, whether or not AI is
used. GLIVARAO now builds every video around **your choices and your own words**, with real variety and
checked facts. These are not tricks: they are the human input and editorial standards the policy is asking for.

## Your week, in practice (automatic topics)

| When | What happens | What you do |
|---|---|---|
| **09:00 Tashkent** (when the pace allows a video) | Fresh research picks the next topic and format, then Telegram announces it with **why it was picked and the source links** | Nothing. *Optionally* reply with your take (text or voice note) |
| 13:17 Tashkent (earlier when measured render times need it, for delivery by 20:00) | The long video + 3 Shorts are written, fact-checked and rendered. Your take is included if it arrived within 4 hours (`CREATOR_INPUT_WAIT_HOURS`) | — |
| After rendering | The review arrives. It **starts with the topic and why it was picked**, then the fact check (every claim with its source URL), the originality report and the AI disclosure | Approve, or **reject the whole video** if you don't like the topic |
| After you approve | The **upload pack** arrives: full-quality video file, 3 titles, description (sources, AI note, affiliate disclosure), tags, thumbnail, suggested publish time (New York + Tashkent) | Save the file, upload in the YouTube Studio app and use **Schedule** |

On the announcement you can tap **🔁 Other format** or **⏭ Skip this topic** (another one is picked on the next run).
Send **/queue** to see what's planned.

### How topics are picked (fully automatic)

1. **Fresh sources, every run.** Each signal keeps its link:
   - official news: Federal Reserve press releases, the CFPB newsroom and blog, IRS news releases;
   - Google Trends: daily trending searches in the US and Canada;
   - the questions people type into Google (search suggestions);
   - CFPB complaint trends;
   - Stack Exchange personal-finance questions;
   - Wikipedia reading trends.
   - BLS, FTC and some news sites block automated requests from servers. BLS data series are available through
     FRED when a free `FRED_API_KEY` is set.
2. **Ranking.** Search interest and demand, real questions, freshness (official news in the last 14 days, trending
   today) and **practical value** (saving, debt, credit, taxes, investing basics score highest), with
   high/medium-confidence topics first.
3. **No repeats.**
   - Not a topic from the last 30 videos.
   - Not the same topic family as the last 3 videos.
   - No angle similar to any of the last 30 videos.
4. **Channel focus and rotation** (details: `docs/CHANNEL_FOCUS.md`).
   - Every topic must fit one of the 5 pillars: debt and credit, budgeting and saving, taxes, retirement and
     investing basics, scams and consumer protection. Anything else (crypto, single stocks, general news) is
     rejected.
   - Never the same pillar twice in a row, and at most 2 of the last 5 videos per pillar. Taxes get more room in
     December–April.
   - Each video belongs to a recurring series (for example "Money Traps" or "Tax Season 2027") that links its
     episodes.
   - Formats rotate too, never the same twice in a row.
5. **Sources for every claim.**
   - Every sentence with a number must trace to a source URL: official releases, research data, real questions,
     or an official page that explains or reproduces the calculation (CFPB, Investor.gov).
   - A script with any claim without a URL is rewritten by the Claude writer, or **not rendered**.
   - All URLs go into the YouTube description.

The manual mode with weekly ideas still exists (`TOPIC_MODE=queue`) if you ever want to choose topics yourself.

## The 8 changes

1. **Topics are picked automatically** (see above), and every pick shows its reasons and sources in Telegram.
2. **Your input, whenever you want to give it.**
   - Your text or voice note becomes a **"My take"** scene, with its own on-screen card.
   - Voice notes are transcribed on the server (free, local, via faster-whisper), and you get the transcript back
     to correct.
   - With the Claude writer, your words are woven in faithfully and the rest of the script connects to them.
   - In automatic mode it's optional: without a reply within 10 hours, the video is made without "My take", and
     the review says so.
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
7. **Pace.**
   - Default: 16 long videos a month, spread evenly, and 3 Shorts every day (90 a month).
   - On days without a long video, the Shorts get their own topic. They never reuse the topic of the long video
     waiting for your take, or of the last 3 long videos.
   - Settings: `LONG_VIDEOS_PER_MONTH`, `SHORTS_PER_DAY`, `MIN_DAYS_BETWEEN_LONG`.
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
TOPIC_MODE=auto             # auto = research picks topics (default); queue = you pick from weekly ideas
CREATOR_INPUT_WAIT_HOURS=4  # auto: how long to wait for your optional take
REQUIRE_CREATOR_INPUT=true  # queue mode only: no video without your take
LONG_VIDEOS_PER_MONTH=16
MIN_DAYS_BETWEEN_LONG=1
SHORTS_PER_DAY=3
TOPIC_IDEAS_PER_WEEK=6      # 5-7
SIMILARITY_MAX_PHRASE=0.25
SIMILARITY_MAX_STRUCTURE=0.85
```
