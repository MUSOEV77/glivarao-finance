# GLIVARAO on Contabo, from an Android phone (Termius)

How to use this guide:
- Copy one grey block at a time.
- Paste it into Termius (long-press, then Paste) and press Enter.
- Wait until you see the prompt again (`root@...#`) before pasting the next block.

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
apt-get update && apt-get -y upgrade && timedatectl set-timezone America/New_York && ufw allow OpenSSH && ufw --force enable && ([ -f /swapfile ] || (fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab)) && echo READY
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

**Anthropic (Claude) key.** This gives 15–18 min long videos.

```
bash /opt/glivarao/app/deploy/set-key.sh ANTHROPIC_API_KEY
```

**Gemini key.** This gives the premium Charon voice.

```
bash /opt/glivarao/app/deploy/set-key.sh GEMINI_API_KEY
```

## Step 5: switch on paid services (only when you're ready to spend)

These two lines allow Claude and Gemini to be used. Spending is capped in code at **$30/month for Claude** and
**$20/month for the voice**. Also set spending limits in the Anthropic Console and in Google Cloud Billing.

```
bash /opt/glivarao/app/deploy/set-key.sh ALLOW_PAID_APIS true && bash /opt/glivarao/app/deploy/set-key.sh TTS_PROVIDER gemini_tts
```

To switch paid services off again at any time:

```
bash /opt/glivarao/app/deploy/set-key.sh ALLOW_PAID_APIS false
```

## Step 6: check the setup

```
cd /opt/glivarao/app && sudo -u glivarao .venv/bin/python -m glivarao doctor
```

Keys show as `set` (never their values). `youtube_publish_enabled` must be `False`.

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
4. Upload manually when you want.

Send `/queue` to the bot any time. Full explanation: `docs/AUTHENTICITY.md`.

To pick and announce the next topic right now:

```
cd /opt/glivarao/app && sudo -u glivarao .venv/bin/python -m glivarao plan-next
```

## Every day after that (automatic)

**What runs by itself:**
- Next topic picked and announced every evening at 17:37 New York time (when the pace allows a video).
- Production at 04:17 New York time (3 long videos a week by default, at least 2 days apart).
- Telegram approval check every 5 minutes.
- Backup at 03:40.

Check the schedule:

```
systemctl list-timers 'glivarao-*' --no-pager
```

## Useful commands

**Free disk space and memory:**

```
df -h / && free -h
```

**Update to the newest version** (after Claude pushes changes):

```
cd /root/glivarao-src && git pull && bash deploy/install.sh
```

**Upload an approved video to YouTube (manual, always private).** Replace `JOB_ID`. It asks you to retype the job ID:

```
cd /opt/glivarao/app && sudo -u glivarao .venv/bin/python -m glivarao publish JOB_ID
```

**List recent jobs:**

```
cd /opt/glivarao/app && sudo -u glivarao .venv/bin/python -m glivarao list --limit 10
```

**Rules:**
- Never paste keys into chats, GitHub, or anywhere except the hidden prompt in Step 4.
- The repository is **public**: it contains code only, no keys.
