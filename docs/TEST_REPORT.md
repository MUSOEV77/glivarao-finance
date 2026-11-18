# Test report — 2026-11-18

**Environment:** cloud Linux container, 4 vCPU, Python 3.13, ffmpeg (libx264, libass), espeak-ng 1.51.
No API keys were available, so every external service was tested with mocks. Nothing was sent to
Telegram or YouTube, and nothing was purchased.

## Verdict: NOT production-ready yet

The rendering pipeline, review workflow and safety gates are built and tested. Production use is blocked on
two things that cannot be verified without the owner's credentials:

1. **Original long-form scripts.** These come from the Claude API, which has not been called for real.
   The offline generator pads to length with repeated paragraphs. It is a render and length test, not
   original content, and the compliance check now flags it as an error in production mode.
2. **Natural narration.** The only voice exercised here is **espeak-ng**, a robotic development placeholder.
   The production providers (**ElevenLabs** or **Google Cloud TTS `en-US-Neural2-D`**, both US-English
   male) are implemented but have not been called.

## 1. Full-length render benchmark (16.5-minute target)

Command:
`python -m glivarao produce --format long --minutes 16.5 --tts espeak --no-approval`

| Metric | Result |
|--------|--------|
| Script | 2,483 words, 63 scenes (offline generator, repeated filler) |
| Output duration | **962.96 s (16.05 min)**, inside the 15–18 min target |
| Output format | 1920×1080, H.264 + AAC, 30 fps, 126.8 MB |
| Wall-clock render time | **398 s (6.6 min)**, 0.41× real time on 4 vCPU |
| Errors | None. Exit code 0; a full decode (`ffmpeg -f null`) found no stream errors |
| Peak memory | ffmpeg 746 MB. The Python figure from this run is invalid (see note) |

**Measurement note:** the first memory sampler matched the bash wrapper instead of the Python process
and reported 3 MB for Python, which is wrong. It was fixed and re-measured on the daily batch below:
**peak 1,110 MB total (Python 394 MB + ffmpeg 746 MB).**

## 2. Daily batch: 1 long video + 2 Shorts

Command: `python -m glivarao daily --long-minutes 16.5 --tts espeak`

| Job | Format | Duration | Size | Decode check |
|-----|--------|----------|------|--------------|
| `20261118-long-e0dab5` | 1920×1080 | 961.6 s (16.0 min) | 126.5 MB | OK |
| `20261118-short-f15564` ("one number" angle) | 1080×1920 | 36.9 s | 5.3 MB | OK |
| `20261118-short-a0312c` ("common mistake" angle) | 1080×1920 | 38.3 s | 5.9 MB | OK |

- Total wall time **441 s (7.4 min)**. Exit code 0.
- The two Shorts are different scripts: 3% 8-word overlap, 98 and 108 words, both inside the 90–160 word
  target. All dollar figures in them were checked against the compound-interest formula.
- Loudness measured **−16 LUFS** against a −14 target, because single-pass loudnorm undershoots.
  YouTube normalizes downward, so this is acceptable. A two-pass loudnorm is a listed improvement.
- This batch started before the self-repetition check was added, so its logged "warnings=0" does not
  include that check. The offline long script **would** now be flagged.

## 3. Telegram review copy (finished MP4 under the 50 MB Bot API limit)

`fit_to_size` was run on the real 126.8 MB master. Result: **46.18 MB**, 1280×720, full 962.9 s length,
quality checked visually. Encode time **186 s**.

## 4. Automated test suite: 24 passed (67 s)

| Area | Tests |
|------|-------|
| Config, secrets | Secrets are redacted in `doctor` output |
| Status machine | Approval cannot be skipped; the audit log records every change |
| Topics | Recent topics are skipped |
| Charts | Compound growth matches the closed-form formula to $0.01 |
| Compliance | Guarantee language, missing disclaimer, copied narration and self-repeating scripts are all flagged |
| Subtitles | Chunking and SRT format |
| TTS | Silent-track timing; espeak produces real speech |
| Claude | Structured-output parsing and request parameters (mocked SDK) |
| FRED | Year-over-year math; charts filled from data (mocked HTTP) |
| Telegram | Full review package in order (thumbnail → title/description → preview → finished MP4 → SRT → checks + buttons); oversized master → review copy; approval only from the approver chat; reject path; approval never uploads |
| YouTube | Upload refused without approval, without typed operator confirmation, or with the kill-switch off; uploads are always private with no `publishAt` |
| CLI | `--auto-publish` and `--privacy public` no longer exist; `publish` refuses to run without an interactive terminal |
| Security | Network errors never include bot tokens or API keys |
| Render | Real ffmpeg render of a Short (1080×1920) and a long video (1920×1080), with duration, codecs and thumbnail sizes checked |

## 5. Security review

- The working tree and the existing commit were scanned for Anthropic, Google and Telegram keys, GitHub
  tokens, private keys, OAuth secrets, email addresses, local paths and IP addresses. **Nothing found.**
  The only match was the `127.0.0.1` example in a comment in `.env.example`.
- Commit author and committer are `Claude <noreply@anthropic.com>`. No personal data appears in the git
  metadata.
- `.env`, `secrets/`, `output/` and `data/` are git-ignored (verified with `git check-ignore`).
- Fixed during review: `requests` error messages contain the request URL, which would have exposed the
  Telegram bot token, the Google key and the FRED key on a network failure. Telegram and FRED errors are
  now sanitized, the Google key moved to a header, and a test covers this.

## 6. Publishing safety (requirement: no automatic upload, publish or schedule)

- There is no code path from approval to upload. `poll-approvals` only records decisions.
- `publish <job_id>` requires all of the following:
  - an interactive terminal;
  - the job ID retyped by a person;
  - `status=approved`;
  - `YOUTUBE_PUBLISH_ENABLED=true` (default false);
  - an OAuth token.
- Uploads are always `private`, and `publishAt` is never set, so YouTube cannot schedule them.
- No cron jobs, scheduled tasks or triggers were created.

## 7. Not verified here (needs credentials)

- Real Claude script quality and length for 15–18 minutes
- Production voice quality (ElevenLabs or Google)
- Real Telegram delivery, including large uploads through a self-hosted Bot API server
- YouTube OAuth, upload, captions and thumbnail
- YouTube Analytics with real data
- FRED with a real key
