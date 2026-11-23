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
    "gemini_api_key",
    "fred_api_key",
    "telegram_bot_token",
    "youtube_api_key",
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
    # Output frame rate. The production renderer (render/animated.py) always encodes 24 fps; this setting is
    # kept equal to it so doctor and reports show the real value (GLIVARAO_FPS in an old .env is ignored).
    fps: int = 24

    # Owner approval switch for anything that costs money (Claude API). Default: off.
    allow_paid_apis: bool = field(default_factory=lambda: _bool("ALLOW_PAID_APIS", False))
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    script_model: str = field(default_factory=lambda: _env("GLIVARAO_SCRIPT_MODEL", "claude-opus-5-5"))
    # Claude script-writing spend guard (USD per calendar month), enforced in code before every request.
    # Prices are per 1M tokens for the script model (Claude Opus 5.5: $4 in / $20 out).
    claude_monthly_budget_usd: float = field(default_factory=lambda: float(_env("CLAUDE_MONTHLY_BUDGET_USD", "30")))
    claude_price_in: float = field(default_factory=lambda: float(_env("CLAUDE_PRICE_IN_PER_M", "4")))
    claude_price_out: float = field(default_factory=lambda: float(_env("CLAUDE_PRICE_OUT_PER_M", "20")))
    claude_spend_ledger_path: str = field(default_factory=lambda: _env("CLAUDE_SPEND_LEDGER_PATH",
                                                                       "data/claude_spend.json"))
    # Script writer, Claude ONLY (no other writer, no fallback): claude_openrouter (default; OPENROUTER_API_KEY)
    # | claude_vertex (Claude on Google Vertex AI; optional switch) | claude_api (Anthropic Console key)
    # | free (offline templates, development only). One shared Claude cap (CLAUDE_MONTHLY_BUDGET_USD) covers all.
    # If Claude can't write, production is held, you get one alert a day, and it retries hourly.
    writer: str = field(default_factory=lambda: _env("WRITER", "claude_openrouter"))
    openrouter_api_key: str = field(default_factory=lambda: _env("OPENROUTER_API_KEY"))
    openrouter_model: str = field(default_factory=lambda: _env("OPENROUTER_MODEL", "anthropic/claude-sonnet-5.5"))
    # OpenRouter list price for Claude Sonnet 5.5: $2 in / $10 out per 1M tokens (checked 2026-11-22). The real
    # cost reported by OpenRouter is recorded when present; these prices are for the pre-flight cap check.
    openrouter_price_in: float = field(default_factory=lambda: float(_env("OPENROUTER_PRICE_IN_PER_M", "2")))
    openrouter_price_out: float = field(default_factory=lambda: float(_env("OPENROUTER_PRICE_OUT_PER_M", "10")))
    openrouter_effort: str = field(default_factory=lambda: _env("OPENROUTER_EFFORT", "high"))
    vertex_project_id: str = field(default_factory=lambda: _env("VERTEX_PROJECT_ID"))
    vertex_region: str = field(default_factory=lambda: _env("VERTEX_REGION", "global"))
    vertex_model: str = field(default_factory=lambda: _env("VERTEX_MODEL", "claude-sonnet-5-5"))
    vertex_credentials_file: str = field(default_factory=lambda: _env("VERTEX_CREDENTIALS_FILE",
                                                                      "secrets/vertex-sa.json"))
    vertex_price_in: float = field(default_factory=lambda: float(_env("VERTEX_PRICE_IN_PER_M", "2")))
    vertex_price_out: float = field(default_factory=lambda: float(_env("VERTEX_PRICE_OUT_PER_M", "10")))
    ai_studio_limit_usd: float = field(default_factory=lambda: float(_env("AI_STUDIO_LIMIT_USD", "35")))

    tts_provider: str = field(default_factory=lambda: _env("TTS_PROVIDER", "gemini_tts"))
    kokoro_voice: str = field(default_factory=lambda: _env("KOKORO_VOICE", "am_michael"))
    renderer: str = field(default_factory=lambda: _env("GLIVARAO_RENDERER", "v1"))
    # Visual theme of the animated (v2) renderer: "editorial" (premium documentary, default), "cartoon", or
    # "doodle" (GLIVARAO hand-drawn explainer; switched on only when you approve the style samples in Telegram).
    theme: str = field(default_factory=lambda: _env("GLIVARAO_THEME", "editorial"))
    # Human-in-the-loop production (YouTube "inauthentic content" safety). See docs/AUTHENTICITY.md.
    # auto = research picks topics (default); queue = only topics you pick from weekly ideas
    topic_mode: str = field(default_factory=lambda: _env("TOPIC_MODE", "auto"))
    # Auto mode: after a topic is announced, wait this long for your take before producing without it
    creator_input_wait_hours: float = field(default_factory=lambda: float(_env("CREATOR_INPUT_WAIT_HOURS", "4")))
    # Daily delivery: the day's videos are in Telegram by DELIVERY_DEADLINE (Tashkent). The run normally starts at
    # DAILY_START and earlier when measured durations x DELIVERY_MARGIN + DELIVERY_BUFFER_MIN say so.
    delivery_deadline: str = field(default_factory=lambda: _env("DELIVERY_DEADLINE", "20:00"))
    daily_start: str = field(default_factory=lambda: _env("DAILY_START", "13:17"))
    delivery_margin: float = field(default_factory=lambda: float(_env("DELIVERY_MARGIN", "1.3")))
    delivery_buffer_min: float = field(default_factory=lambda: float(_env("DELIVERY_BUFFER_MIN", "20")))
    require_creator_input: bool = field(default_factory=lambda: _bool("REQUIRE_CREATOR_INPUT", True))
    long_videos_per_month: int = field(default_factory=lambda: int(_env("LONG_VIDEOS_PER_MONTH", "16")))
    shorts_per_day: int = field(default_factory=lambda: int(_env("SHORTS_PER_DAY", "3")))  # 3 x 30 = 90 a month
    min_days_between_long: int = field(default_factory=lambda: int(_env("MIN_DAYS_BETWEEN_LONG", "1")))
    topic_ideas_per_week: int = field(default_factory=lambda: int(_env("TOPIC_IDEAS_PER_WEEK", "6")))
    # Upload pack (sent to Telegram after you approve; you upload and schedule in YouTube Studio yourself)
    publish_times_long_weekday: str = field(default_factory=lambda: _env("PUBLISH_TIMES_LONG_WEEKDAY", "14:00"))
    publish_times_long_weekend: str = field(default_factory=lambda: _env("PUBLISH_TIMES_LONG_WEEKEND", "11:00"))
    publish_times_shorts: str = field(default_factory=lambda: _env("PUBLISH_TIMES_SHORTS", "11:00,15:00,19:30"))
    # extra Short slots (New York) used only while a week is catching up to WEEK_SHORTS
    publish_times_shorts_catchup: str = field(default_factory=lambda: _env("PUBLISH_TIMES_SHORTS_CATCHUP",
                                                                             "09:00,13:00,17:00"))
    # weekly pace (Mon-Sun, Tashkent): exactly WEEK_LONG long + WEEK_SHORTS Shorts a week (studio/week.py)
    pace_mode: str = field(default_factory=lambda: _env("PACE_MODE", "weekly"))
    week_long: int = field(default_factory=lambda: int(_env("WEEK_LONG", "4")))
    week_shorts: int = field(default_factory=lambda: int(_env("WEEK_SHORTS", "21")))
    publish_lead_hours: float = field(default_factory=lambda: float(_env("PUBLISH_LEAD_HOURS", "2")))
    # Buffer: approved videos ready ahead of their publish slot; production runs PRODUCTION_LEAD_DAYS ahead
    buffer_long: int = field(default_factory=lambda: int(_env("BUFFER_LONG", "2")))
    buffer_shorts: int = field(default_factory=lambda: int(_env("BUFFER_SHORTS", "6")))
    production_lead_days: int = field(default_factory=lambda: int(_env("PRODUCTION_LEAD_DAYS", "3")))
    shorts_per_month: int = field(default_factory=lambda: int(_env("SHORTS_PER_MONTH", "90")))
    # Your time zone: no Telegram messages during quiet hours (they are delivered at QUIET_END)
    local_tz: str = field(default_factory=lambda: _env("LOCAL_TZ", "Asia/Tashkent"))
    quiet_start: str = field(default_factory=lambda: _env("QUIET_START", "23:00"))
    quiet_end: str = field(default_factory=lambda: _env("QUIET_END", "08:00"))
    # Stability alerts
    spend_alert_ratio: float = field(default_factory=lambda: float(_env("SPEND_ALERT_RATIO", "0.8")))
    disk_alert_gb: float = field(default_factory=lambda: float(_env("DISK_ALERT_GB", "10")))
    # Competitor research (YouTube Data API, read-only)
    youtube_api_key: str = field(default_factory=lambda: _env("YOUTUBE_API_KEY"))
    competitor_channels: str = field(default_factory=lambda: _env(
        "COMPETITOR_CHANNELS", "Casual Finance,How Money Works,Economics Explained,Money & Macro,The Plain Bagel,"
        "Two Cents"))
    competitor_days: int = field(default_factory=lambda: int(_env("COMPETITOR_DAYS", "90")))
    affiliate_disclosure: str = field(default_factory=lambda: _env(
        "AFFILIATE_DISCLOSURE",
        "Disclosure: some links on this channel may be affiliate links. If you sign up or buy through them, "
        "GLIVARAO Finance may earn a commission at no extra cost to you. This never affects what we cover or "
        "how; there are no paid sponsorships in this video."))
    similarity_max_phrase: float = field(default_factory=lambda: float(_env("SIMILARITY_MAX_PHRASE", "0.25")))
    similarity_max_structure: float = field(default_factory=lambda: float(_env("SIMILARITY_MAX_STRUCTURE", "0.85")))
    elevenlabs_api_key: str = field(default_factory=lambda: _env("ELEVENLABS_API_KEY"))
    elevenlabs_voice_id: str = field(default_factory=lambda: _env("ELEVENLABS_VOICE_ID"))
    elevenlabs_model_id: str = field(default_factory=lambda: _env("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"))
    google_tts_api_key: str = field(default_factory=lambda: _env("GOOGLE_TTS_API_KEY"))
    google_tts_voice: str = field(default_factory=lambda: _env("GOOGLE_TTS_VOICE", "en-US-Chirp3-HD-Charon"))
    google_tts_rate: float = field(default_factory=lambda: float(_env("GOOGLE_TTS_RATE", "1.0")))
    # Paid-TTS spending cap: hard monthly character limit = free allowance + budget / price
    tts_monthly_budget_usd: float = field(default_factory=lambda: float(_env("TTS_MONTHLY_BUDGET_USD", "20")))
    tts_price_per_million: float = field(default_factory=lambda: float(_env("TTS_PRICE_PER_MILLION", "30")))
    tts_free_chars_per_month: int = field(default_factory=lambda: int(_env("TTS_FREE_CHARS_PER_MONTH", "0")))
    # Gemini TTS (selected premium voice). Prices default to the HIGHER reported rates (conservative cap).
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    # The channel voice is LOCKED (tts/voice_lock.py): pinned model, Charon, fixed pace and style. No fallback.
    gemini_tts_model: str = field(default_factory=lambda: _env("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts"))
    gemini_tts_voice: str = field(default_factory=lambda: _env("GEMINI_TTS_VOICE", "Charon"))
    gemini_tts_pace: str = field(default_factory=lambda: _env("GEMINI_TTS_PACE", "measured"))
    gemini_tts_style: str = field(default_factory=lambda: _env(
        "GEMINI_TTS_STYLE", "Narrate as a warm, deep, confident American male documentary narrator explaining "
        "personal finance. Clear numbers and money amounts; subtle emphasis on key figures; trustworthy, never "
        "theatrical."))
    # Speaking speed: pitch-preserving tempo applied after synthesis (1.0 = as generated). Chosen in the voice
    # audition so the narrator lands at TTS_TARGET_WPM; locked with the voice.
    gemini_tts_speed: float = field(default_factory=lambda: float(_env("GEMINI_TTS_SPEED", "1.0")))
    # The few words of direction sent before every scene ("<direction>: <text>"). At most 10 words: a long style
    # paragraph in the prompt gets read aloud by the model.
    gemini_tts_direction: str = field(default_factory=lambda: _env("GEMINI_TTS_DIRECTION",
                                                                   "Say in a warm, confident, upbeat voice"))
    tts_target_wpm: int = field(default_factory=lambda: int(_env("TTS_TARGET_WPM", "170")))
    # Same pace for every scene: each scene is measured and atempo-corrected to this many spoken words/min
    # (acceptable 152-164; correction factor 0.85-1.20, pitch preserved).
    tts_pace_wpm: float = field(default_factory=lambda: float(_env("TTS_PACE_WPM", "158")))
    # Shorts length: script capped before voicing; real audio measured after; never sent over SHORT_MAX_SECONDS
    # Shorts must be 30-55 s: <=120 words; voiced and measured BEFORE rendering; over 55 s -> trim + re-voice (2x);
    # over 58 s -> atempo up to 1.15x; over 59 s -> held (never rendered or sent). The final file is checked again.
    short_max_words: int = field(default_factory=lambda: int(_env("SHORT_MAX_WORDS", "120")))
    short_redo_seconds: float = field(default_factory=lambda: float(_env("SHORT_REDO_SECONDS", "55")))
    short_target_seconds: float = field(default_factory=lambda: float(_env("SHORT_TARGET_SECONDS", "48")))
    short_tempo_seconds: float = field(default_factory=lambda: float(_env("SHORT_TEMPO_SECONDS", "58")))
    short_max_tempo: float = field(default_factory=lambda: float(_env("SHORT_MAX_TEMPO", "1.15")))
    short_max_seconds: float = field(default_factory=lambda: float(_env("SHORT_MAX_SECONDS", "59")))
    gemini_tts_retries: int = field(default_factory=lambda: int(_env("GEMINI_TTS_RETRIES", "5")))
    gemini_tts_backoff_sec: float = field(default_factory=lambda: float(_env("GEMINI_TTS_BACKOFF_SEC", "5")))
    tts_alert_ratio: float = field(default_factory=lambda: float(_env("TTS_ALERT_RATIO", "0.8")))
    gemini_tts_price: float = field(default_factory=lambda: float(_env("GEMINI_TTS_PRICE_PER_M_AUDIO", "18")))
    # AI images (Nano Banana 2.1, same GEMINI_API_KEY): long videos only; code-drawn visuals if anything fails
    image_provider: str = field(default_factory=lambda: _env("IMAGE_PROVIDER", "gemini"))   # gemini | none
    image_model: str = field(default_factory=lambda: _env("IMAGE_MODEL", "gemini-nano-banana-2.1"))
    image_monthly_budget_usd: float = field(default_factory=lambda: float(_env("IMAGE_MONTHLY_BUDGET_USD", "15")))
    image_price_1k: float = field(default_factory=lambda: float(_env("IMAGE_PRICE_1K", "0.0336")))
    image_price_2k: float = field(default_factory=lambda: float(_env("IMAGE_PRICE_2K", "0.0504")))
    image_scene_size: str = field(default_factory=lambda: _env("IMAGE_SCENE_SIZE", "1K"))
    image_thumb_size: str = field(default_factory=lambda: _env("IMAGE_THUMB_SIZE", "2K"))
    image_scenes_max: int = field(default_factory=lambda: int(_env("IMAGE_SCENES_MAX", "20")))
    image_retries: int = field(default_factory=lambda: int(_env("IMAGE_RETRIES", "3")))
    image_backoff_sec: float = field(default_factory=lambda: float(_env("IMAGE_BACKOFF_SEC", "5")))
    image_spend_ledger_path: str = field(default_factory=lambda: _env("IMAGE_SPEND_LEDGER_PATH", "data/image_spend.json"))
    image_cache_dir: str = field(default_factory=lambda: _env("IMAGE_CACHE_DIR", "data/image_cache"))
    character_ref_path: str = field(default_factory=lambda: _env("CHARACTER_REF_PATH", "data/character/reference.png"))
    doodle_ref_path: str = field(default_factory=lambda: _env("DOODLE_REF_PATH",
                                                              "data/character/doodle_reference.png"))
    doodle_library_dir: str = field(default_factory=lambda: _env("DOODLE_LIBRARY_DIR", "data/scene_library"))
    # Nano Banana key scenes per video in the doodle style (Max acting in the scene); every other shot uses a
    # reusable place from the scene library with a Max cutout. Long: 2K 16:9; Shorts: 1K 9:16.
    doodle_key_scenes_long: int = field(default_factory=lambda: int(_env("DOODLE_KEY_SCENES_LONG", "6")))
    doodle_key_scenes_short: int = field(default_factory=lambda: int(_env("DOODLE_KEY_SCENES_SHORT", "1")))
    gemini_tts_tokens_per_sec: float = field(default_factory=lambda: float(_env("GEMINI_TTS_TOKENS_PER_SEC", "32")))
    tts_spend_ledger_path: str = field(default_factory=lambda: _env("TTS_SPEND_LEDGER_PATH", "data/tts_spend.json"))
    tts_cache_dir: str = field(default_factory=lambda: _env("TTS_CACHE_DIR", "data/tts_cache"))
    tts_ledger_path: str = field(default_factory=lambda: _env("TTS_LEDGER_PATH", "data/tts_usage.json"))

    fred_api_key: str = field(default_factory=lambda: _env("FRED_API_KEY"))

    telegram_bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    telegram_approver_chat_id: str = field(default_factory=lambda: _env("TELEGRAM_APPROVER_CHAT_ID"))
    # Cloud Bot API accepts uploads up to 50 MB. A self-hosted Bot API server
    # (github.com/tdlib/telegram-bot-api) raises this to 2000 MB so the full master MP4 can be sent.
    telegram_api_base: str = field(default_factory=lambda: _env("TELEGRAM_API_BASE", "https://api.telegram.org"))
    telegram_max_upload_mb: int = field(default_factory=lambda: int(_env("TELEGRAM_MAX_UPLOAD_MB", "50")))

    youtube_client_secrets_file: Path = field(
        default_factory=lambda: Path(_env("YOUTUBE_CLIENT_SECRETS_FILE", "secrets/client_secret.json"))
    )
    youtube_token_file: Path = field(default_factory=lambda: Path(_env("YOUTUBE_TOKEN_FILE", "secrets/youtube_token.json")))
    youtube_publish_enabled: bool = field(default_factory=lambda: _bool("YOUTUBE_PUBLISH_ENABLED", False))
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


def get_settings() -> Settings:
    return Settings()
