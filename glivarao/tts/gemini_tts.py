"""Gemini TTS narrator (Google Gemini API; paid, owner approval required). GLIVARAO's selected premium voice:
model `gemini-3.8-flash-tts`, prebuilt voice "Charon", directed as a warm, confident documentary narrator.

* Whole scenes are synthesized as one paragraph so the model controls natural rhythm across sentences.
  Sentence timings (for captions and animation cues) are recovered from the pauses in the returned audio.
* Billing is per audio token. Spend is recorded in USD from the API's own usage metadata, and a hard monthly
  cap is enforced before every scene. Scenes are cached on disk, so re-renders never pay twice.
* The API key goes in a header, never the URL.
NOTE: model IDs and prices vary between Google's pages; both are configurable and must be confirmed on the
first approved call. A wrong model ID fails with an error (no charge) and the video falls back to Kokoro.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import requests

from .google_chirp import BudgetExceeded, PaidTTSError
from .kokoro import KOKORO_SR, Narration, Sentence, normalize_text, split_sentences

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.8-flash-tts"
FALLBACK_MODEL = "gemini-3.8-flash-lite-tts"   # same prebuilt voices -> the channel keeps the same narrator
DEFAULT_VOICE = "Charon"
DEFAULT_STYLE = ("Narrate as a warm, deep, confident American male documentary narrator explaining personal "
                 "finance. Natural, measured pace with real pauses between sentences; clear numbers and money "
                 "amounts; subtle emphasis on key figures; trustworthy, never theatrical.")
BRAND_RESPELL = {"GLIVARAO": "Gli-VAR-oh"}     # prompt-based models take respellings, not IPA


class SpendLedger:
    """USD spent per calendar month on paid TTS (JSON file)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def spent(self, month: str | None = None) -> float:
        return float(self._load().get(month or date.today().strftime("%Y-%m"), {}).get("usd", 0.0))

    def add(self, usd: float, tokens: int, month: str | None = None) -> None:
        data = self._load()
        m = month or date.today().strftime("%Y-%m")
        row = data.setdefault(m, {"usd": 0.0, "audio_tokens": 0})
        row["usd"] = round(row["usd"] + usd, 6)
        row["audio_tokens"] += tokens
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))


def estimate_usd(text: str, price_per_m_audio: float, tokens_per_sec: float, chars_per_sec: float = 14.7) -> float:
    """Conservative pre-flight estimate (speech seconds from measured GLIVARAO narration rate)."""
    return len(text) / chars_per_sec * tokens_per_sec * price_per_m_audio / 1e6


def split_by_pauses(audio: np.ndarray, sentences: list[str], sr: int = KOKORO_SR) -> list[tuple[float, float]]:
    """Return (start, end) per sentence by placing boundaries in the n-1 longest silent gaps (≥120 ms),
    falling back to character-proportional timing when there aren't enough clear gaps."""
    n = len(sentences)
    total = len(audio) / sr
    if n <= 1:
        return [(0.0, total)]
    hop = int(0.01 * sr)
    frames = len(audio) // hop
    rms = np.sqrt(np.mean(audio[: frames * hop].reshape(frames, hop) ** 2, axis=1)) if frames else np.zeros(0)
    quiet = rms < max(0.01, 0.08 * (np.percentile(rms, 95) if len(rms) else 0))
    gaps, i = [], 0
    while i < frames:
        if quiet[i]:
            j = i
            while j < frames and quiet[j]:
                j += 1
            if (j - i) >= 12 and i > 0 and j < frames:  # interior gap of at least 120 ms
                gaps.append((j - i, i * hop / sr, j * hop / sr))
            i = j
        else:
            i += 1
    if len(gaps) >= n - 1:
        chosen = sorted(sorted(gaps, reverse=True)[: n - 1], key=lambda g: g[1])
        bounds = [(0.0, chosen[0][1])]
        bounds += [(chosen[k - 1][2], chosen[k][1]) for k in range(1, n - 1)]
        bounds.append((chosen[-1][2], total))
        return bounds
    weights = np.cumsum([0] + [len(s) for s in sentences]) / max(1, sum(len(s) for s in sentences))
    return [(float(weights[k] * total), float(weights[k + 1] * total)) for k in range(n)]


class GeminiTTSNarrator:
    provider = "gemini_tts"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, voice: str = DEFAULT_VOICE, style: str = DEFAULT_STYLE,
                 price_per_m_audio: float = 18.0, tokens_per_sec: float = 32.0, monthly_budget_usd: float = 20.0,
                 cache_dir: Path = Path("data/tts_cache"), ledger: SpendLedger | None = None, session=None):
        if not api_key:
            raise PaidTTSError("GEMINI_API_KEY is not set")
        self._key, self.model, self.voice, self.style = api_key, model, voice, style
        self.price, self.tps, self.budget = price_per_m_audio, tokens_per_sec, monthly_budget_usd
        self.cache = Path(cache_dir)
        self.ledger = ledger or SpendLedger(Path("data/tts_spend.json"))
        self.http = session or requests.Session()
        self.spent_usd = 0.0

    # -- budget ------------------------------------------------------------------------------------------
    def _key_for(self, text: str) -> Path:
        h = hashlib.sha256(f"{self.model}|{self.voice}|{self.style}|{text}".encode()).hexdigest()[:24]
        return self.cache / f"gem_{h}.npy"

    def uncached_estimate_usd(self, texts: list[str]) -> float:
        return sum(estimate_usd(self._prep(t), self.price, self.tps) for t in texts if not self._key_for(self._prep(t)).exists())

    def check_budget(self, usd_needed: float) -> None:
        if self.ledger.spent() + usd_needed > self.budget:
            raise BudgetExceeded(f"monthly TTS budget: ${self.ledger.spent():.2f} spent + ~${usd_needed:.2f} needed "
                                 f"> ${self.budget:.2f}")

    # -- synthesis ---------------------------------------------------------------------------------------
    @staticmethod
    def _prep(text: str) -> str:
        t = normalize_text(text.replace("*", ""))
        for w, r in BRAND_RESPELL.items():
            t = t.replace(w, r)
        return t

    def _request(self, text: str) -> tuple[np.ndarray, int]:
        body = {"contents": [{"parts": [{"text": f"{self.style}\n\n{text}"}]}],
                "generationConfig": {"responseModalities": ["AUDIO"],
                                     "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": self.voice}}}}}
        try:
            r = self.http.post(API.format(model=self.model), headers={"x-goog-api-key": self._key}, json=body, timeout=180)
        except requests.RequestException as exc:
            raise PaidTTSError(f"Gemini TTS request failed: {type(exc).__name__}") from None
        if r.status_code != 200:
            raise PaidTTSError(f"Gemini TTS HTTP {r.status_code}")
        data = r.json()
        try:
            part = data["candidates"][0]["content"]["parts"][0]["inlineData"]
        except (KeyError, IndexError):
            raise PaidTTSError("Gemini TTS returned no audio") from None
        pcm = np.frombuffer(base64.b64decode(part["data"]), dtype="<i2").astype(np.float32) / 32768.0
        rate = KOKORO_SR
        mime = part.get("mimeType", "")
        if "rate=" in mime:
            rate = int(mime.split("rate=")[1].split(";")[0])
        if rate != KOKORO_SR:
            idx = np.linspace(0, len(pcm) - 1, int(len(pcm) * KOKORO_SR / rate))
            pcm = np.interp(idx, np.arange(len(pcm)), pcm).astype(np.float32)
        usage = data.get("usageMetadata", {})
        tokens = int(usage.get("candidatesTokenCount") or round(len(pcm) / KOKORO_SR * self.tps))
        return pcm, tokens

    def _scene_audio(self, text: str) -> np.ndarray:
        p = self._key_for(text)
        if p.exists():
            return np.load(p)
        self.check_budget(estimate_usd(text, self.price, self.tps))
        audio, tokens = self._request(text)
        usd = tokens * self.price / 1e6
        self.ledger.add(usd, tokens)
        self.spent_usd += usd
        p.parent.mkdir(parents=True, exist_ok=True)
        np.save(p, audio)
        return audio

    def narrate(self, text: str, lead_in: float = 0.15, tail: float = 0.45) -> Narration:
        display = [s.replace("*", "") for s in split_sentences(" ".join(text.split()))]
        audio = self._scene_audio(self._prep(text))
        idx = np.where(np.abs(audio) > 0.004)[0]  # trim leading/trailing silence, keep GLIVARAO lead-in/tail
        if len(idx):
            audio = audio[max(0, idx[0] - 480): idx[-1] + 720]
        spans = split_by_pauses(audio, display)
        sentences = [Sentence(d, lead_in + a, lead_in + b, "*" in raw, d.rstrip().endswith("?"))
                     for d, raw, (a, b) in zip(display, split_sentences(" ".join(text.split())), spans)]
        full = np.concatenate([np.zeros(int(lead_in * KOKORO_SR), np.float32), audio,
                               np.zeros(int(tail * KOKORO_SR), np.float32)])
        peak = float(np.abs(full).max()) or 1.0
        return Narration(full * (0.89 / peak), sentences, [])
