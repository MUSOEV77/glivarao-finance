# Script writer: Claude through OpenRouter (default)

`WRITER=claude_openrouter` — Claude Sonnet 5.5 (`OPENROUTER_MODEL=anthropic/claude-sonnet-5.5`, the latest Claude
Sonnet on openrouter.ai/models when checked on 2026-11-22; list price $2 in / $10 out per 1M tokens).

- **Claude only.** Same prompts, JSON-schema structured output, fact-check and originality rules as before. The
  request is routed only to providers that honour the JSON schema, and an answer from any non-`anthropic/` model
  is discarded. There is no other writer: if Claude can't write (credits used up, outage, refusal, bad JSON), the
  job is held, you get one Telegram alert a day, and it retries every hour.
- **Cap:** `CLAUDE_MONTHLY_BUDGET_USD=30`, checked in code before every request; the real cost OpenRouter
  reports is recorded in `data/claude_spend.json`. Telegram alert at 80% and at the cap.
- **Key:** `OPENROUTER_API_KEY` in `/opt/glivarao/app/.env` (owner-only). Set or replace it with
  `sudo bash deploy/set-key.sh OPENROUTER_API_KEY` (hidden input). It is sent only in the Authorization header to
  openrouter.ai and is masked in every error message.
- **Check:** `python -m glivarao doctor --live` makes one tiny real call (a few tokens, a tiny fraction of a cent,
  counted in the cap) and shows the key's usage. `python -m glivarao claude-quota` does the same call alone.
  Both skip the call while production is paused.
- **Estimated cost** at 16 long videos + 90 Shorts a month: roughly $0.25-0.35 per long script and $0.05-0.08 per
  Short, about $10-15 a month including revisions; the $30 cap stops it in any case.

Vertex stays available as an optional switch (`docs/VERTEX_CLAUDE.md`): `deploy/set-vertex-key.sh` sets
`WRITER=claude_vertex`; switch back with `sudo bash deploy/set-key.sh WRITER claude_openrouter`.
