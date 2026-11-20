# Claude on Vertex AI (the script writer)

The long-script writer is **Claude Sonnet 5.5 on Google Vertex AI** (`WRITER=claude_vertex`, region `global`). It
signs in with your service account `glivarao-vps@…`, not an Anthropic Console key.

- **If Claude fails** (key problem, quota, outage, refusal, cap reached), **Gemini Pro takes over automatically**
  with the same `GEMINI_API_KEY`. You get one Telegram alert per day when that happens.
- **Claude cap:** $30/month, alert at 80%.
- **Gemini Pro fallback cap:** $5/month.
- **Billing:**
  - The $300 Google trial credit does **not** cover Claude on Vertex or the AI Studio Gemini API.
  - Claude on Vertex is billed to your Google Cloud billing account.
  - Gemini goes against your AI Studio limit.

## AI Studio limit vs. the Gemini caps

| Gemini cap | per month |
|---|---|
| Voice (Charon) | $20 |
| Images (Nano Banana) | $15 |
| Fallback writer (Gemini Pro) | $5 |
| **Total** | **$40** |

Your AI Studio limit is $35. Expected real use is about $20–25 a month, but if all three caps were reached,
AI Studio would stop at $35 and **the voice could stop for the rest of that month**.

**Recommended:** raise the AI Studio limit to **$40**, then run
`bash /opt/glivarao/app/deploy/set-key.sh AI_STUDIO_LIMIT_USD 40`. Otherwise `doctor` keeps showing a warning.

## Phone steps: create the JSON key

You've already given the service account the **Vertex AI User** role. Now, in your phone's browser
(console.cloud.google.com, signed in as the project owner):

1. Open ☰ → **IAM & Admin** → **Service Accounts**. Make sure project `project-ca5f1248-…` is selected at the top.
2. Tap **glivarao-vps@…** → **Keys** tab → **Add key** → **Create new key** → **JSON** → **Create**.
3. The phone downloads a file such as `project-ca5f1248-…-abc123.json`. **Treat it like a password.**

**If you see "Service account key creation is disabled":** your organization blocks keys by default.
1. Go to ☰ → **IAM & Admin** → **Organization Policies**.
2. Search **"Disable service account key creation"** (`iam.disableServiceAccountKeyCreation`).
3. Tap **Manage policy** → **Override parent's policy** → **Enforcement: Off** → **Set policy**.
4. Retry step 2.

This needs the "Organization Policy Administrator" role. If you can't change the policy, tell me.

## Put the key on the VPS (two ways)

**A. Paste (easiest on a phone)**
1. Open the downloaded JSON in a text viewer (Files app → tap the file), select all and copy.
2. In Termius, run:

   ```
   sudo bash /opt/glivarao/app/deploy/set-vertex-key.sh
   ```

3. Paste. Nothing shows on screen. Press **Enter**, then **Ctrl+D**.

**B. Upload with Termius SFTP**
1. In Termius, open **SFTP** and upload the file to `/root/`.
2. Run (with your file name):

   ```
   sudo bash /opt/glivarao/app/deploy/set-vertex-key.sh /root/YOUR-KEY-FILE.json
   ```

   The uploaded copy is deleted afterwards.

**What the script does:**
- Checks that it's a real service-account key.
- Saves it as `/opt/glivarao/app/secrets/vertex-sa.json`, readable only by the `glivarao` user (file `600`,
  folder `700`). It's never shown, never logged, and never in Git (`secrets/` is excluded).
- Sets `WRITER=claude_vertex`, `VERTEX_PROJECT_ID` (taken from the key), `VERTEX_REGION=global` and
  `VERTEX_MODEL=claude-sonnet-5-5`.

**After it's saved,** clean up your phone:
- Delete the downloaded JSON from the phone (Files → Downloads → delete, and empty the trash).
- Copy something harmless to clear the clipboard.

## Test it

```
cd /opt/glivarao/app && sudo -u glivarao .venv/bin/python -m glivarao doctor --live
```

`Claude (Vertex AI) … answered 'OK'` means it works (the test costs a fraction of a cent).

## Quota (HTTP 429 "Quota exceeded … global_online_predict")

New projects often start with **0 quota** for Claude, even with the model enabled.
- Sonnet 5.5 uses one shared bucket, `base_model=anthropic-claude-sonnet`, with three limits: requests per minute,
  input tokens per minute and output tokens per minute.
- It runs only on the **global**, **us** and **eu** endpoints; each has its own quota. There's no single-region
  endpoint such as us-east5 for Sonnet 5.5.

**In Google Cloud Shell** (console.cloud.google.com → the `>_` icon at the top), with your project ID:

```
curl -fsSL https://raw.githubusercontent.com/MUSOEV77/glivarao-finance/claude/glivarao-finance-mvp-n153rg/deploy/vertex-quota.sh -o vq.sh && bash vq.sh request project-ca5f1248-f0b8-49cb-8fa global
```

This asks for 10 requests/min, 100,000 input tokens/min and 20,000 output tokens/min. Check the status later
(it also shows current limits for global, us and eu):

```
bash vq.sh status project-ca5f1248-f0b8-49cb-8fa
```

If `us` or `eu` already shows non-zero values, use that region right away on the VPS:

```
bash /opt/glivarao/app/deploy/set-key.sh VERTEX_REGION us
```

Until Claude has quota, the Gemini Pro fallback writes the scripts automatically.

**Common errors:**
- **403 / PermissionDenied:** the role hasn't spread yet (wait 2–5 minutes), or Claude Sonnet 5.5 isn't enabled in
  **Vertex AI → Model Garden** for this project.
- **404 / NotFound:** the model isn't enabled for region `global`. Open Model Garden → Claude Sonnet 5.5 →
  Enable.
- **Gemini fallback runs instead:** the review shows "Writer: Gemini … (fallback)". `doctor --live` shows why.

## If you ever need to replace the key

1. Create a new key (steps above).
2. Run `set-vertex-key.sh` again; it overwrites the old file.
3. In Google Cloud → Service account → Keys, **delete the old key**.
