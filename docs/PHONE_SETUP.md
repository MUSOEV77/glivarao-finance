# GLIVARAO on Contabo, from an Android phone (Termius)

How to use this guide:
- Copy one grey block at a time.
- Paste it into Termius (long-press, then Paste) and press Enter.
- Wait until you see the prompt again (`root@...#`) before pasting the next block.

## What to have ready before you start

| # | Item | Where to get it | Used for |
|---|---|---|---|
| 1 | Contabo VPS IP + root password | Contabo email | logging in (Termius) |
| 2 | **Telegram bot token** | @BotFather → /newbot | reviews, alerts, upload packs |
| 3 | **Vertex AI service-account JSON key** for `glivarao-vps@…` (role "Vertex AI User") | Google Cloud Console → IAM & Admin → Service Accounts → Keys (`docs/VERTEX_CLAUDE.md`) | the script writer, Claude Sonnet 5.5 (capped at $30/month in code) |
| 4 | **Gemini API key** on a billing-enabled project + budget alert | aistudio.google.com → API keys; Google Cloud Billing → Budgets | the Charon voice (capped at $20/month, alert at 80%) |
| 5 | **YouTube Data API key** (you have it) | Google Cloud Console → APIs & Services → Credentials | competitor research (read-only, free quota) |
| 6 | Telegram **api_id + api_hash** (optional, for long videos in full quality) | my.telegram.org → API development tools | files up to 2 GB in Telegram |
| 7 | Affiliate links (later, when approved) | each program | `/affiliate <program> <link>` in Telegram |

**Order:** Steps 1 → 3 (server + install, about 20 min) → Step 4 (keys) → Step 5 (switch on paid voice + writer) →
Step 6 (`doctor`: everything must show `[x]`) → Step 7 (first run) → optional: large files
(`docs/TELEGRAM_LARGE_FILES.md`, about 45 min) and competitor research (`competitors` command below).

## Step 0: let Claude push the code (phone browser)

1. Open https://github.com/apps/claude/installations/select_target
2. Choose **MUSOEV77**, then **Only select repositories**, then **glivarao-finance**, then **Install**.
3. Tell Claude "GitHub app installed". Claude pushes the code. Don't continue until Claude confirms the push.

## Step 1: connect

In Termius:
1. Tap **New Host**.
2. Address: your VPS IP. Username: `root`. Password: from the Contabo email.
3. Tap **Connect**.

Then change the root password:

```
passwd
```

## Step 2: prepare the server (≈ 3 min)

```
apt-get update && apt-get -y upgrade && timedatectl set-timezone Asia/Tashkent && ufw allow OpenSSH && ufw --force enable && ([ -f /swapfile ] || (fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab)) && echo READY
```

If a purple screen asks about restarting services, press **Enter**.

## Step 3: download and install GLIVARAO (≈ 10–15 min)

```
git clone -b claude/glivarao-finance-mvp-n153rg https://github.com/MUSOEV77/glivarao-finance.git /root/glivarao-src && cd /root/glivarao-src && bash deploy/install.sh
```

It ends with a list of timers and `Done. Nothing is ever uploaded automatically.`

## Step 4: add your keys (hidden; nothing shows on screen)

Paste one line. When it asks, paste your key and press Enter.

**Telegram bot token** (from @BotFather):

```
bash /opt/glivarao/app/deploy/set-key.sh TELEGRAM_BOT_TOKEN
```

**Your Telegram chat ID:**

1. First open your bot in Telegram and send it any message, for example `hi`.
2. Then paste this. It prints only your chat ID (a number):

```
T=$(grep '^TELEGRAM_BOT_TOKEN=' /opt/glivarao/app/.env | cut -d= -f2-); curl -s "https://api.telegram.org/bot$T/getUpdates" | grep -o '"chat":{"id":-\?[0-9]*' | head -1 | grep -o -- '-\?[0-9]*$'; unset T
```

3. Save that number:

```
bash /opt/glivarao/app/deploy/set-key.sh TELEGRAM_APPROVER_CHAT_ID
```

**Claude on Vertex AI (service-account JSON key).** This is the script writer for the 15–18 min long videos.
Create the key first (`docs/VERTEX_CLAUDE.md`), copy its whole text, then run this and paste. Nothing shows on
screen; press Enter, then Ctrl+D:

```
sudo bash /opt/glivarao/app/deploy/set-vertex-key.sh
```

**Gemini key.** This is the channel voice (Charon).

```
bash /opt/glivarao/app/deploy/set-key.sh GEMINI_API_KEY
```

**YouTube Data API key.** Read-only, for competitor research.

```
bash /opt/glivarao/app/deploy/set-key.sh YOUTUBE_API_KEY
```

## Step 5: switch on paid services (needed: the channel voice is Gemini "Charon")

This line allows Claude and Gemini to be used, and locks the channel voice:
- Spending is capped in code at **$30/month for Claude** and **$20/month for the voice**.
- You get an alert in Telegram at 80% of the voice budget.
- Also set a budget alert in Google Cloud Billing (for Claude on Vertex) and keep the AI Studio spend limit
  (Gemini).

```
bash /opt/glivarao/app/deploy/set-key.sh ALLOW_PAID_APIS true && bash /opt/glivarao/app/deploy/set-key.sh TTS_PROVIDER gemini_tts && bash /opt/glivarao/app/deploy/set-key.sh GEMINI_TTS_MODEL gemini-3.8-flash-tts && bash /opt/glivarao/app/deploy/set-key.sh GEMINI_TTS_VOICE Charon && bash /opt/glivarao/app/deploy/set-key.sh GEMINI_TTS_PACE measured
```

**Switching paid services off** stops new videos until you switch them back on. Videos are put on hold, never made
with another voice:

```
bash /opt/glivarao/app/deploy/set-key.sh ALLOW_PAID_APIS false
```

**Check the voice lock, this month's voice spending and any videos on hold:**

```
cd /opt/glivarao/app && sudo -u glivarao .venv/bin/python -m glivarao voice-lock
```

## Step 6: check the setup

```
cd /opt/glivarao/app && sudo -u glivarao .venv/bin/python -m glivarao doctor --live
```

**How to read it:**
- Every key and setting shows `ok`, `MISSING` or `INVALID` (values are never shown).
- `--live` tests Telegram, YouTube, Gemini and Claude on Vertex with tiny real calls; together they cost less than
  one cent.
- Fix every `MISSING` or `INVALID` line before the first run. `warn` lines are advice.

**If Ubuntu says "System restart required":** reboot safely. This waits until no video is rendering, and missed
jobs run after the restart:

```
sudo bash /opt/glivarao/app/deploy/safe-reboot.sh
```

## Step 7: first real run (≈ 30–90 min; safe to close Termius)

```
systemctl start --no-block glivarao-daily.service && echo STARTED
```

Check progress any time:

```
tail -n 15 /opt/glivarao/app/logs/daily.log
```

When it finishes, Telegram shows the review package for 1 long video and 2 Shorts. Use **Approve** or **Reject**.
Approving uploads nothing.

## How it works now (topics are picked automatically)

1. **Evening:** Telegram announces the next video's topic and format, with **why it was picked** and the source
   links. Optionally reply with your own take (text or voice note).
2. **Next morning:** the video is written, fact-checked (every number with its source URL) and rendered.
3. **Review:** the message starts with the topic and why it was picked. Approve, or reject the whole video.
4. After you approve, the **upload pack** arrives:
   - the full-quality video file;
   - three titles, the description and the tags (tap to copy);
   - the thumbnail;
   - the suggested publish time in New York and Tashkent time.

   Save the video and upload it from the YouTube Studio app with **Schedule**. For long videos, set up large files
   once: `docs/TELEGRAM_LARGE_FILES.md`.

After uploading, **reply to the upload pack with the video's YouTube link**, so the next episodes of the series
can link to it.

Send `/help` to the bot for all commands: `/queue`, `/series`, `/playlist`, `/affiliate`.
Affiliate programs start as placeholders: when you're approved, send for example
`/affiliate rocketmoney https://your-link`. Full explanations:
`docs/AUTHENTICITY.md` and `docs/CHANNEL_FOCUS.md` (the 5 pillars, series and affiliate links).

To pick and announce the next topic right now:

```
cd /opt/glivarao/app && sudo -u glivarao .venv/bin/python -m glivarao plan-next
```

## Every day after that (automatic)

**What runs by itself (Tashkent time):**
- **09:00:** the next topic is announced. The first 16 come from your launch list, then automatic research picks.
- **09:05:** health report.
- **13:17:** production, 2–3 days ahead of publishing:
  - 16 long videos a month and 3 Shorts a day;
  - extra Shorts (up to 6) or an early long video when the buffer of 2 approved long + 6 Shorts is low.
- **Every 5 minutes:** approvals are checked, and messages held during quiet hours are delivered.
- **Every hour:** videos on hold (voice unavailable) are retried.
- **Mondays 08:31:** competitor research.
- **03:40:** backup.
- **Quiet hours 23:00–08:00:** no messages; anything that comes up is delivered at 08:00.
- **If a service fails:** it restarts automatically, and you get a Telegram alert.

Check the schedule:

```
systemctl list-timers 'glivarao-*' --no-pager
```

## Useful commands

**Free disk space and memory:**

```
df -h / && free -h
```

**Update to the newest version** (after Claude pushes changes). This is a safe update: it waits for any running
production to finish, takes a snapshot, installs, runs a self-test, and **rolls back automatically** (with a
Telegram alert) if anything fails:

```
sudo bash /root/glivarao-src/deploy/update.sh
```

**Health report now** (it also arrives every day at 09:05):

```
cd /opt/glivarao/app && sudo -u glivarao .venv/bin/python -m glivarao health
```

**Competitor research now** (it also runs every Monday):

```
cd /opt/glivarao/app && sudo -u glivarao .venv/bin/python -m glivarao competitors
```

**Re-check the launch list's numbers on the official pages:**

```
cd /opt/glivarao/app && sudo -u glivarao .venv/bin/python -m glivarao verify-facts
```

**Resend the upload pack of an approved video** (full-quality file, titles, description, tags, thumbnail, publish
time). Replace `JOB_ID`:

```
cd /opt/glivarao/app && sudo -u glivarao .venv/bin/python -m glivarao pack JOB_ID
```

**List recent jobs:**

```
cd /opt/glivarao/app && sudo -u glivarao .venv/bin/python -m glivarao list --limit 10
```

**Rules:**
- Never paste keys into chats, GitHub, or anywhere except the hidden prompt in Step 4.
- The repository is **public**: it contains code only, no keys.
