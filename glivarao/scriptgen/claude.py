"""Generate a structured script with the Claude API (Anthropic Python SDK)."""
from __future__ import annotations

import json
import logging

import anthropic

from ..config import Settings
from ..models import Script
from .prompts import SCRIPT_SCHEMA, SYSTEM_PROMPT, user_prompt

log = logging.getLogger(__name__)

DEFAULT_MINUTES = {"long": 16.5, "short": 0.85}


class ScriptGenerationError(RuntimeError):
    pass


def generate_with_claude(topic: str, fmt: str, settings: Settings, minutes: float | None = None,
                         angle: str = "") -> Script:
    minutes = minutes or DEFAULT_MINUTES[fmt]
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    # Streaming avoids HTTP timeouts on long outputs. Server-side fallback re-runs the request on
    # another model if the primary declines (e.g. a finance topic tripping a classifier).
    with client.beta.messages.stream(
        model=settings.script_model,
        max_tokens=64000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCRIPT_SCHEMA}},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt(topic, fmt, minutes, angle)}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise ScriptGenerationError(f"Model declined topic {topic!r}: {message.stop_details}")
    if message.stop_reason == "max_tokens":
        raise ScriptGenerationError("Script truncated at max_tokens")
    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScriptGenerationError(f"Invalid JSON from model: {exc}") from exc
    log.info("Claude usage: in=%s out=%s", message.usage.input_tokens, message.usage.output_tokens)
    return Script.model_validate({**data, "format": fmt, "topic": topic})
