# GLIVARAO Finance

Automated production of original US personal-finance videos:

- one 15–18 minute explainer and two YouTube Shorts per day
- American English male narration
- original hand-drawn-style cartoon characters and illustrations
- animated charts, burned-in subtitles and thumbnails
- Telegram approval before anything is published
- YouTube upload and analytics

> **Safe by default.** The pipeline runs in `dry-run` mode with no network calls. A video can be published
> only after a human approves it in Telegram **and** `YOUTUBE_PUBLISH_ENABLED=true`. Uploads are private
> by default.

## Quick start

```bash
# system: Python 3.11+, ffmpeg with libx264 + libass; optional: espeak-ng (dev placeholder voice)
pip install -r requirements.txt
cp .env.example .env               # fill in credentials later — see docs/CREDENTIALS.md
python -m glivarao doctor          # shows what's configured
python -m glivarao produce --format short              # dry-run Short, ~30 s
python -m glivarao produce --format long --minutes 2   # dry-run 2-minute long-form sample
python -m pytest -q                # 19 tests, ~1 minute
```

Output goes to `output/<job_id>/`: `video.mp4`, `thumbnail.jpg`, `captions.srt`, `script.json` and `compliance.txt`.

## Production

Set `GLIVARAO_MODE=production`, add the keys from `docs/CREDENTIALS.md`, then run:

```bash
python -m glivarao daily                       # 1 long + 2 Shorts → Telegram for approval
python -m glivarao poll-approvals --auto-publish
python -m glivarao analytics
```

## Docs
- `docs/IMPLEMENTATION_PLAN.md`: architecture, phases and risks
- `docs/CREDENTIALS.md`: every credential and service needed, and where to get it
- `docs/OPERATIONS.md`: daily runbook and scheduling
- `docs/TEST_REPORT.md`: what was tested, what works, what's incomplete

## Layout
```
glivarao/
  config.py  models.py  storage.py  topics.py  compliance.py  marketdata.py  pipeline.py  __main__.py
  scriptgen/   claude.py (production)  offline.py (dry-run)  prompts.py
  tts/         elevenlabs | google | espeak (dev) | silent
  art/         style.py (hand-drawn ink)  characters.py  illustrations.py  charts.py
  render/      scene.py  subtitles.py  video.py  thumbnail.py
  publish/     telegram.py  youtube.py
assets/fonts/  Patrick Hand (SIL Open Font License, OFL.txt included)
config/topics.yaml
tests/
```

## Originality
The characters (Max and Penny), illustrations and charts are drawn in code from primitive shapes in this
repository. No third-party artwork is used. The only bundled third-party asset is the Patrick Hand font,
licensed under the SIL OFL. The script prompt forbids imitating other channels, and the compliance step
compares every new script against earlier ones to catch repeated narration.
