# Full-quality videos in Telegram (files up to 2 GB)

**Why this is needed.**
- Telegram's normal bot server lets bots send files up to **50 MB**.
- A 15–18 minute 1080p long video is usually 300–450 MB.
- Shorts (about 20 MB) fit already; long videos need this one-time setup.

**The option chosen: Telegram's own local Bot API server, on the VPS.**

| | Local Bot API server (chosen) | Temporary download link |
|---|---|---|
| File size | up to 2,000 MB | any |
| Open ports, domain, HTTPS certificate | **none** (listens on 127.0.0.1 only) | needs an open port, plus a domain and certificate to be safe |
| Where the file arrives | in the same Telegram chat, next to the upload pack | a browser download |
| Who can get the file | only your approver chat | anyone who obtains the link before it expires |
| Software | Telegram's official open-source server | a web server you'd have to maintain |

It is simpler *and* safer: nothing on the VPS becomes reachable from the internet.

## One-time setup (about 30–45 minutes, mostly waiting)

1. **On your phone,** open https://my.telegram.org and log in with your Telegram number. Then:
   1. tap **API development tools**;
   2. create an app (any name, for example "glivarao");
   3. note the **api_id** (a number) and the **api_hash**.

   They're free. Never share them.
2. **In Termius on the VPS,** after GLIVARAO is installed and your bot token is set:

   ```
   sudo bash /opt/glivarao/app/deploy/telegram-local-api.sh
   ```

   - It asks for the api_id and the api_hash; the hash is hidden as you type.
   - It builds the official server from Telegram's GitHub, which takes 20–40 minutes. You can leave Termius in the
     background.
   - It starts the server on 127.0.0.1:8081 as a service that restarts by itself.
   - It moves your bot to the local server (Telegram requires a one-time `logOut` from its cloud server), then sets
     `TELEGRAM_API_BASE` and `TELEGRAM_MAX_UPLOAD_MB=1900`.
   - It ends with a check like `bot: yourbot via http://127.0.0.1:8081`.

That's it. From then on, every approved long video arrives as a full-quality file.

## Saving the file on Android

1. In the upload pack, tap the video file to download it.
2. Then tap ⋮ → **Save to Downloads** (or **Save to gallery**).
3. In the YouTube Studio app: ＋ → pick the file → paste title, description and tags → thumbnail →
   **Visibility → Schedule** → the date and time from the pack.

## If something goes wrong

**Check the server:**

```
systemctl status telegram-bot-api --no-pager
```

**Go back to the normal cloud server** (files up to 50 MB):

```
bash /opt/glivarao/app/deploy/set-key.sh TELEGRAM_API_BASE https://api.telegram.org && bash /opt/glivarao/app/deploy/set-key.sh TELEGRAM_MAX_UPLOAD_MB 50 && systemctl disable --now telegram-bot-api
```

Telegram lets the bot return to the cloud server about 10 minutes after it moved.

**Without this setup,** the upload pack still arrives. Shorts come in full quality; for long videos the pack says
the file is too large and where it is on the server, and the review message keeps the compressed 720p copy.
