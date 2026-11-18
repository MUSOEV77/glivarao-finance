"""Script generation: Claude API in production, deterministic offline generator for dry runs."""
from __future__ import annotations

from ..config import Settings
from ..models import Script


def generate_script(topic: str, fmt: str, settings: Settings, minutes: float | None = None,
                    angle: str = "") -> Script:
    if settings.dry_run or not settings.anthropic_api_key:
        from .offline import generate_offline

        return generate_offline(topic, fmt, minutes=minutes, angle=angle)
    from .claude import generate_with_claude

    return generate_with_claude(topic, fmt, settings, minutes=minutes, angle=angle)
