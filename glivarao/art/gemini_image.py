"""Nano Banana 2.1 (Gemini image API, same GEMINI_API_KEY): thumbnails and scene illustrations for long videos.

* Model pinned to `gemini-nano-banana-2.1` (Google's stable ID, Oct 2026); "latest"/"preview"/"exp" refused.
* One consistent ORIGINAL channel character: every request that shows him includes the reference sheet
  (art/character_ref.py) as an input image.
* Separate monthly cap (IMAGE_MONTHLY_BUDGET_USD, default $15) checked before every call; alert at 80%.
* Images are cached on disk by prompt + settings, so re-renders never pay twice.
* Any failure (no key, paid use off, cap reached, API error after retries) raises ImageUnavailable and the caller
  uses the existing code-drawn visuals. The key goes in a header, never the URL.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import random
import re
import time
from datetime import date
from pathlib import Path

import requests
from PIL import Image

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
PINNED_MODEL = "gemini-nano-banana-2.1"
RETRYABLE = {408, 429, 500, 502, 503, 504}
UNPINNED = re.compile(r"latest|preview|\bexp\b|-exp", re.I)
STYLE = ("Style: original hand-drawn editorial documentary illustration, warm cream paper texture, confident ink "
         "linework, flat muted colors (navy, crimson, forest green, ochre), generous negative space. Not "
         "photorealistic. No real people, no celebrities, no brand logos, no watermarks.")


class ImageUnavailable(RuntimeError):
    """The image API can't be used right now: callers fall back to code-drawn visuals."""


class ImageLedger:
    """USD spent per calendar month on images (JSON file)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def spent(self, month: str | None = None) -> float:
        return float(self._load().get(month or date.today().strftime("%Y-%m"), {}).get("usd", 0.0))

    def add(self, usd: float, size: str) -> None:
        data = self._load()
        row = data.setdefault(date.today().strftime("%Y-%m"), {"usd": 0.0, "images": 0, "by_size": {}})
        row["usd"] = round(row["usd"] + usd, 6)
        row["images"] += 1
        row["by_size"][size] = row["by_size"].get(size, 0) + 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))


class GeminiImage:
    def __init__(self, settings, session=None, sleep=time.sleep):
        if not (settings.allow_paid_apis and settings.gemini_api_key):
            raise ImageUnavailable("paid APIs are off or GEMINI_API_KEY is not set")
        if settings.image_provider != "gemini":
            raise ImageUnavailable(f"IMAGE_PROVIDER={settings.image_provider}")
        if not settings.image_model or UNPINNED.search(settings.image_model):
            raise ImageUnavailable(f"IMAGE_MODEL={settings.image_model!r} is not a pinned model version")
        self.s, self._key, self.model = settings, settings.gemini_api_key, settings.image_model
        self.http, self._sleep = session or requests.Session(), sleep
        self.ledger = ImageLedger(Path(settings.image_spend_ledger_path))
        self.cache = Path(settings.image_cache_dir)
        self.spent_usd, self.made = 0.0, 0

    def price(self, size: str) -> float:
        return self.s.image_price_2k if size.upper() == "2K" else self.s.image_price_1k

    def check_budget(self, usd: float) -> None:
        if self.ledger.spent() + usd > self.s.image_monthly_budget_usd:
            raise ImageUnavailable(f"monthly image budget: ${self.ledger.spent():.2f} spent + ${usd:.3f} > "
                                   f"${self.s.image_monthly_budget_usd:.2f}")

    def _cache_path(self, prompt: str, size: str, aspect: str, refs: list[bytes]) -> Path:
        h = hashlib.sha256("|".join([self.model, prompt, size, aspect] +
                                    [hashlib.sha256(r).hexdigest() for r in refs]).encode()).hexdigest()[:24]
        return self.cache / f"img_{h}.png"

    def generate(self, prompt: str, size: str = "1K", aspect: str = "1:1",
                 refs: list[bytes] | None = None) -> Image.Image:
        refs = refs or []
        path = self._cache_path(prompt, size, aspect, refs)
        if path.exists():
            return Image.open(path).convert("RGB")
        self.check_budget(self.price(size))
        parts = [{"text": prompt}] + [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(r).decode()}}
                                      for r in refs]
        body = {"contents": [{"parts": parts}],
                "generationConfig": {"responseModalities": ["IMAGE"],
                                     "imageConfig": {"aspectRatio": aspect, "imageSize": size}}}
        last = ""
        for attempt in range(self.s.image_retries + 1):
            if attempt:
                self._sleep(min(60.0, self.s.image_backoff_sec * 2 ** (attempt - 1)) + random.uniform(0, 1))
            try:
                r = self.http.post(API.format(model=self.model), headers={"x-goog-api-key": self._key}, json=body,
                                   timeout=180)
            except requests.RequestException as exc:
                last = f"network error: {type(exc).__name__}"
                continue
            if r.status_code in RETRYABLE:
                last = f"HTTP {r.status_code}"
                continue
            if r.status_code != 200:
                raise ImageUnavailable(f"image API HTTP {r.status_code}")
            img = _first_image(r.json())
            if img is None:  # e.g. blocked by a safety filter: no charge for an empty answer is assumed
                last = "no image in the response"
                continue
            usd = self.price(size)
            self.ledger.add(usd, size)
            self.spent_usd += usd
            self.made += 1
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(path, "PNG")
            return img
        raise ImageUnavailable(f"image API unavailable after {self.s.image_retries + 1} attempts ({last})")


def _first_image(data: dict) -> Image.Image | None:
    for cand in data.get("candidates", []):
        for part in (cand.get("content") or {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and str(inline.get("mimeType", inline.get("mime_type", ""))).startswith("image/"):
                return Image.open(io.BytesIO(base64.b64decode(inline["data"]))).convert("RGB")
    return None


__all__ = ["GeminiImage", "ImageUnavailable", "ImageLedger", "STYLE", "PINNED_MODEL"]
