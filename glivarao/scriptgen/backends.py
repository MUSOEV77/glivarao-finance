"""Script-writer backends. Scripts are written ONLY by Claude; there is no other writer and no fallback.

WRITER=claude_openrouter (default): Claude Sonnet 5.5 through OpenRouter (OPENROUTER_API_KEY), model
    OPENROUTER_MODEL=anthropic/claude-sonnet-5.5. Structured output (JSON schema), routed only to providers that
    support it, never to another model. The answer's model is checked to be an anthropic/ model.
WRITER=claude_vertex: Claude Sonnet 5.5 on Google Vertex AI (optional switch; service-account JSON in
    VERTEX_CREDENTIALS_FILE, owner-only, never in Git or logs).
WRITER=claude_api: Claude through an Anthropic Console key (ANTHROPIC_API_KEY).
WRITER=free: offline template writer (development only; production never uses it).

All Claude backends share one monthly cap (CLAUDE_MONTHLY_BUDGET_USD, $30) and one spend ledger. If Claude can't
write (key, credits, quota, outage, refusal, bad JSON), production is held, you get one alert a day, and it
retries hourly.
"""
from __future__ import annotations

import logging
import random
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"
CLAUDE_BACKENDS = ("claude_openrouter", "claude_vertex", "claude_api")


class WriterUnavailable(RuntimeError):
    pass


# ------------------------------------------------------------------------------------------- Anthropic SDK clients
def vertex_credentials(settings):
    """Service-account credentials from the owner-only JSON file. Errors never include the file contents."""
    from google.oauth2 import service_account

    path = Path(settings.vertex_credentials_file)
    if not path.exists():
        raise WriterUnavailable(f"Vertex service-account key not found at {path} (see docs/VERTEX_CLAUDE.md)")
    try:
        return service_account.Credentials.from_service_account_file(str(path), scopes=SCOPES)
    except Exception as exc:  # noqa: BLE001  never echo the key file
        raise WriterUnavailable(f"Vertex service-account key could not be read ({type(exc).__name__})") from None


def claude_client(settings):
    """(client, platform, model, price_in, price_out) for the Anthropic-SDK Claude backends (Vertex, API)."""
    import anthropic

    if settings.writer == "claude_vertex":
        if not settings.vertex_project_id:
            raise WriterUnavailable("VERTEX_PROJECT_ID is not set")
        client = anthropic.AnthropicVertex(project_id=settings.vertex_project_id, region=settings.vertex_region,
                                           credentials=vertex_credentials(settings), max_retries=3, timeout=600)
        return client, "vertex", settings.vertex_model, settings.vertex_price_in, settings.vertex_price_out
    if settings.writer == "claude_api":
        if not settings.anthropic_api_key:
            raise WriterUnavailable("ANTHROPIC_API_KEY is not set")
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=3, timeout=600)
        return client, "api", settings.script_model, settings.claude_price_in, settings.claude_price_out
    raise WriterUnavailable(f"WRITER={settings.writer} has no Anthropic-SDK backend")


def claude_configured(settings) -> bool:
    if settings.writer == "claude_openrouter":
        return bool(settings.openrouter_api_key)
    if settings.writer == "claude_vertex":
        return bool(settings.vertex_project_id and Path(settings.vertex_credentials_file).exists())
    if settings.writer == "claude_api":
        return bool(settings.anthropic_api_key)
    return False


# ------------------------------------------------------------------------------------------- OpenRouter
HINTS = {401: "OPENROUTER_API_KEY is invalid or revoked (set it again: deploy/set-key.sh OPENROUTER_API_KEY)",
         402: "OpenRouter credits are used up (add credits at openrouter.ai/settings/credits)",
         403: "the request was blocked by OpenRouter moderation or the key's limits",
         404: "model not found on OpenRouter (check OPENROUTER_MODEL)"}


def openrouter_chat(settings, system: str, prompt: str, max_tokens: int, schema: dict | None = None,
                    effort: str | None = None, session=None, sleep=time.sleep, attempts: int = 4,
                    model: str | None = None) -> tuple[str, dict]:
    """One Claude answer through OpenRouter: (text, usage). usage has prompt/completion tokens and OpenRouter's
    own cost in USD when it reports it. Retries 408/429/5xx with backoff; anything else raises WriterUnavailable.
    The key goes only in the Authorization header and never appears in errors or logs."""
    if not settings.openrouter_api_key:
        raise WriterUnavailable("OPENROUTER_API_KEY is not set (deploy/set-key.sh OPENROUTER_API_KEY)")
    model = model or settings.openrouter_model
    if not model.startswith("anthropic/"):
        raise WriterUnavailable(f"OPENROUTER_MODEL={model!r} is not a Claude model (Claude only)")
    body: dict = {"model": model, "max_tokens": max_tokens,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                  "usage": {"include": True},
                  # never silently route to a provider that would ignore the JSON schema
                  "provider": {"require_parameters": True, "allow_fallbacks": True}}
    if schema is not None:
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": "script", "strict": True, "schema": schema}}
    if effort:
        body["reasoning"] = {"effort": effort}
    http = session or requests.Session()
    last = ""
    for attempt in range(attempts):
        if attempt:
            sleep(min(60.0, 5.0 * 2 ** (attempt - 1)) + random.uniform(0, 1))
        try:
            r = http.post(OPENROUTER_API, headers={"Authorization": f"Bearer {settings.openrouter_api_key}",
                                                   "Content-Type": "application/json"},
                          json=body, timeout=(30, 900))
        except requests.RequestException as exc:
            last = f"network error: {type(exc).__name__}"
            continue
        if r.status_code in (408, 429, 500, 502, 503, 504):
            last = f"HTTP {r.status_code}"
            continue
        if r.status_code != 200:
            msg = ""
            try:
                msg = str(r.json().get("error", {}).get("message", ""))[:200]
            except Exception:  # noqa: BLE001
                pass
            msg = msg.replace(settings.openrouter_api_key, "***")
            raise WriterUnavailable(f"OpenRouter HTTP {r.status_code}"
                                    + (f": {HINTS[r.status_code]}" if r.status_code in HINTS else "")
                                    + (f" ({msg})" if msg else ""))
        try:
            data = r.json()
        except ValueError:
            last = "unreadable answer"
            continue
        if "error" in data and not data.get("choices"):  # some upstream errors arrive with HTTP 200
            last = f"upstream error {str(data['error'].get('code', ''))}".strip()
            continue
        served = str(data.get("model", model))
        if not served.startswith("anthropic/"):
            raise WriterUnavailable(f"OpenRouter answered with {served!r}, not Claude; answer discarded")
        u = data.get("usage") or {}
        usage = {"prompt_tokens": int(u.get("prompt_tokens") or 0),
                 "completion_tokens": int(u.get("completion_tokens") or 0),
                 "cost": u.get("cost"), "model": served}
        try:
            choice = data["choices"][0]
        except (KeyError, IndexError):
            last = "answer without choices"
            continue
        usage["finish_reason"] = choice.get("finish_reason") or choice.get("native_finish_reason") or ""
        msg = choice.get("message") or {}
        if msg.get("refusal"):
            usage["finish_reason"] = "refusal"
        return str(msg.get("content") or ""), usage
    raise WriterUnavailable(f"OpenRouter unavailable after {attempts} attempts ({last})")


__all__ = ["claude_client", "claude_configured", "openrouter_chat", "vertex_credentials", "WriterUnavailable",
           "CLAUDE_BACKENDS", "OPENROUTER_API"]
