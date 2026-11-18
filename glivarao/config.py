"""Runtime configuration loaded exclusively from environment variables.

Secrets are never hard-coded, logged or written to output files. `Settings.redacted()`
is the only representation that may be printed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

try:  # optional: load a local .env during development
    from dotenv import load_dotenv

    load_dotenv(override=False)
except ImportError:  # pragma: no cover
    pass

SECRET_FIELDS = {
    "anthropic_api_key",
    "elevenlabs_api_key",
    "google_tts_api_key",
    "fred_api_key",
    "telegram_bot_token",
}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _bool(name: str, default: bool = False) -> bool:
    return _env(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    mode: str = field(default_factory=lambda: _env("GLIVARAO_MODE", "dry-run"))
    output_dir: Path = field(default_factory=lambda: Path(_env("GLIVARAO_OUTPUT_DIR", "output")))
    db_path: Path = field(default_factory=lambda: Path(_env("GLIVARAO_DB_PATH", "data/glivarao.sqlite3")))
    fps: int = field(default_factory=lambda: int(_env("GLIVARAO_FPS", "12")))
    timezone: str = field(default_factory=lambda: _env("GLIVARAO_TIMEZONE", "America/New_York"))

    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    script_model: str = field(default_factory=lambda: _env("GLIVARAO_SCRIPT_MODEL", "claude-opus-5-5"))

    tts_provider: str = field(default_factory=lambda: _env("TTS_PROVIDER", "espeak"))
    elevenlabs_api_key: str = field(default_factory=lambda: _env("ELEVENLABS_API_KEY"))
    elevenlabs_voice_id: str = field(default_factory=lambda: _env("ELEVENLABS_VOICE_ID"))
    elevenlabs_model_id: str = field(default_factory=lambda: _env("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"))
    google_tts_api_key: str = field(default_factory=lambda: _env("GOOGLE_TTS_API_KEY"))
    google_tts_voice: str = field(default_factory=lambda: _env("GOOGLE_TTS_VOICE", "en-US-Neural2-D"))

    fred_api_key: str = field(default_factory=lambda: _env("FRED_API_KEY"))

    telegram_bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    telegram_approver_chat_id: str = field(default_factory=lambda: _env("TELEGRAM_APPROVER_CHAT_ID"))

    youtube_client_secrets_file: Path = field(
        default_factory=lambda: Path(_env("YOUTUBE_CLIENT_SECRETS_FILE", "secrets/client_secret.json"))
    )
    youtube_token_file: Path = field(default_factory=lambda: Path(_env("YOUTUBE_TOKEN_FILE", "secrets/youtube_token.json")))
    youtube_publish_enabled: bool = field(default_factory=lambda: _bool("YOUTUBE_PUBLISH_ENABLED", False))
    youtube_default_privacy: str = field(default_factory=lambda: _env("YOUTUBE_DEFAULT_PRIVACY", "private"))
    youtube_category_id: str = field(default_factory=lambda: _env("YOUTUBE_CATEGORY_ID", "27"))

    @property
    def dry_run(self) -> bool:
        return self.mode != "production"

    def redacted(self) -> dict:
        out = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name in SECRET_FIELDS:
                out[f.name] = "set" if value else "MISSING"
            else:
                out[f.name] = str(value)
        return out

    def readiness(self) -> dict[str, tuple[bool, str]]:
        """Which integrations are configured. Values: (ready, explanation)."""
        tts_ready = {
            "elevenlabs": bool(self.elevenlabs_api_key and self.elevenlabs_voice_id),
            "google": bool(self.google_tts_api_key),
            "espeak": True,
            "silent": True,
        }.get(self.tts_provider, False)
        return {
            "script_generation (Claude)": (bool(self.anthropic_api_key), "ANTHROPIC_API_KEY"),
            f"narration ({self.tts_provider})": (
                tts_ready,
                "ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID or GOOGLE_TTS_API_KEY",
            ),
            "production voice": (
                self.tts_provider in {"elevenlabs", "google"} and tts_ready,
                "espeak/silent are dev placeholders only",
            ),
            "market data (FRED)": (bool(self.fred_api_key), "FRED_API_KEY (optional)"),
            "telegram approval": (
                bool(self.telegram_bot_token and self.telegram_approver_chat_id),
                "TELEGRAM_BOT_TOKEN + TELEGRAM_APPROVER_CHAT_ID",
            ),
            "youtube oauth client": (self.youtube_client_secrets_file.exists(), str(self.youtube_client_secrets_file)),
            "youtube authorized token": (self.youtube_token_file.exists(), "run: python -m glivarao youtube-auth"),
            "youtube publishing switch": (self.youtube_publish_enabled, "YOUTUBE_PUBLISH_ENABLED=true"),
        }


def get_settings() -> Settings:
    return Settings()
