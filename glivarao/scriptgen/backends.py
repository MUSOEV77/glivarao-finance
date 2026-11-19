"""Script-writer backends and automatic fallback.

WRITER=claude_vertex (default): Claude Sonnet 5.5 on Google Vertex AI (region global), authenticated with the
    service-account JSON in VERTEX_CREDENTIALS_FILE (owner-only file, never in Git or logs).
WRITER=claude_api: Claude through an Anthropic Console key (ANTHROPIC_API_KEY).
WRITER=free: offline template writer only (no paid calls).

If the Claude writer fails for any reason (credentials, quota, outage after the SDK's retries, budget cap,
refusal, invalid JSON) the same request goes to Gemini Pro (GEMINI_API_KEY) automatically. Both have their own
monthly caps; the Claude cap is shared by both Claude backends.
Vertex does not support Anthropic's server-side `fallbacks`, so a refusal there is handled by this Gemini
fallback instead.
"""
from __future__ import annotations

import json
import logging
import random
import time
from datetime import date
from pathlib import Path

import requests

log = logging.getLogger(__name__)
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


class WriterUnavailable(RuntimeError):
    pass


# ------------------------------------------------------------------------------------------- Claude clients
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
    """(client, platform, model, price_in, price_out) for the configured Claude backend."""
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
    raise WriterUnavailable(f"WRITER={settings.writer} has no Claude backend")


def claude_configured(settings) -> bool:
    if settings.writer == "claude_vertex":
        return bool(settings.vertex_project_id and Path(settings.vertex_credentials_file).exists())
    if settings.writer == "claude_api":
        return bool(settings.anthropic_api_key)
    return False


# ------------------------------------------------------------------------------------------- Gemini writer
class GeminiWriterLedger:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def spent(self, month: str | None = None) -> float:
        return float(self._load().get(month or date.today().strftime("%Y-%m"), {}).get("usd", 0.0))

    def add(self, usd: float, tin: int, tout: int) -> None:
        data = self._load()
        row = data.setdefault(date.today().strftime("%Y-%m"), {"usd": 0.0, "input_tokens": 0, "output_tokens": 0,
                                                              "requests": 0})
        row["usd"] = round(row["usd"] + usd, 6)
        row["input_tokens"] += tin
        row["output_tokens"] += tout
        row["requests"] += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))


def gemini_write(settings, system: str, prompt: str, schema: dict, fmt: str, session=None,
                 sleep=time.sleep) -> dict:
    """One JSON script from Gemini Pro (structured output), with retries and its own monthly cap."""
    if not (settings.allow_paid_apis and settings.gemini_api_key):
        raise WriterUnavailable("Gemini fallback needs ALLOW_PAID_APIS=true and GEMINI_API_KEY")
    ledger = GeminiWriterLedger(Path(settings.gemini_writer_ledger_path))
    est_out = 24000 if fmt == "long" else 6000
    est = (len(prompt) + len(system)) / 3.5 * settings.gemini_writer_price_in / 1e6 + \
        est_out * settings.gemini_writer_price_out / 1e6
    if ledger.spent() + est > settings.gemini_writer_monthly_budget_usd:
        raise WriterUnavailable(f"Gemini writer monthly budget: ${ledger.spent():.2f} spent + ~${est:.2f} > "
                                f"${settings.gemini_writer_monthly_budget_usd:.2f}")
    http = session or requests.Session()
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema,
                                 "maxOutputTokens": 32768}}
    last = ""
    for attempt in range(4):
        if attempt:
            sleep(min(60.0, 5.0 * 2 ** (attempt - 1)) + random.uniform(0, 1))
        try:
            r = http.post(GEMINI_API.format(model=settings.gemini_writer_model),
                          headers={"x-goog-api-key": settings.gemini_api_key}, json=body, timeout=600)
        except requests.RequestException as exc:
            last = f"network error: {type(exc).__name__}"
            continue
        if r.status_code == 400 and "responseJsonSchema" in body["generationConfig"]:
            # older Pro models: plain JSON mode, schema described in the prompt instead
            body["generationConfig"].pop("responseJsonSchema")
            body["contents"][0]["parts"][0]["text"] = (prompt + "\n\nReturn ONLY JSON that matches this JSON "
                                                       "schema:\n" + json.dumps(schema))
            last = "HTTP 400 (retrying without the schema field)"
            continue
        if r.status_code in (408, 429, 500, 502, 503, 504):
            last = f"HTTP {r.status_code}"
            continue
        if r.status_code != 200:
            raise WriterUnavailable(f"Gemini writer HTTP {r.status_code}")
        data = r.json()
        u = data.get("usageMetadata", {})
        tin = int(u.get("promptTokenCount", 0))
        tout = int(u.get("candidatesTokenCount", 0)) + int(u.get("thoughtsTokenCount", 0))
        ledger.add(tin * settings.gemini_writer_price_in / 1e6 + tout * settings.gemini_writer_price_out / 1e6,
                   tin, tout)
        try:
            cand = data["candidates"][0]
            if cand.get("finishReason") not in (None, "STOP"):
                raise WriterUnavailable(f"Gemini writer stopped early ({cand.get('finishReason')})")
            text = "".join(p.get("text", "") for p in cand["content"]["parts"] if not p.get("thought"))
            return json.loads(text)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            last = f"unusable answer ({type(exc).__name__})"
            continue
    raise WriterUnavailable(f"Gemini writer unavailable after 4 attempts ({last})")


__all__ = ["claude_client", "claude_configured", "gemini_write", "vertex_credentials", "WriterUnavailable",
           "GeminiWriterLedger"]
