"""Gemini TTS narrator (Google Gemini API; paid, owner approval required). THE channel voice (locked, see
tts/voice_lock.py): pinned model `gemini-3.8-flash-tts`, prebuilt voice "Charon", fixed pace and style.

* Whole scenes are synthesized as one paragraph so the model controls natural rhythm across sentences.
  Sentence timings (for captions and animation cues) are recovered from the pauses in the returned audio.
* Billing is per audio token. Spend is recorded in USD from the API's own usage metadata, and a hard monthly
  cap is enforced before every scene. Scenes are cached on disk, so re-renders never pay twice.
* The API key goes in a header, never the URL.
* Temporary errors (network, 429 rate limit, 5xx) are retried with exponential backoff. Permanent errors (bad key,
  retired model, refused request) are not. Either way the result is VoiceUnavailable: the video is HELD and
  re-rendered later. There is no fallback voice or fallback model.
"""
from __future__ import annotations

import base64
import logging
import hashlib
import json
import random
import time
from datetime import date
from pathlib import Path

import numpy as np
import requests

from .kokoro import KOKORO_SR, Narration, Sentence, normalize_text, split_sentences
from .voice_lock import PINNED_MODEL, VoiceUnavailable, check_model

log = logging.getLogger(__name__)
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = PINNED_MODEL
DEFAULT_VOICE = "Charon"
DEFAULT_STYLE = ("Narrate as a warm, deep, confident American male documentary narrator explaining personal "
                 "finance. Clear numbers and money amounts; subtle emphasis on key figures; trustworthy, never "
                 "theatrical.")
RETRYABLE = {408, 429, 500, 502, 503, 504}
MIN_SANE_WPM = 90   # real narration is 140-190 wpm; far below means repeated/stretched audio
PERMANENT = {402: "Gemini prepay balance is empty (buy credits on the AI Studio Billing page)",
             400: "the request was refused", 401: "the API key was rejected", 403: "the API key has no access "
             "(check billing / API enabled)", 404: "the pinned model was not found (retired?)"}
BRAND_RESPELL = {"GLIVARAO": "Gli-VAR-oh"}     # prompt-based models take respellings, not IPA


class _Retryable(Exception):
    pass


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


def apply_tempo(audio: np.ndarray, factor: float, sr: int = KOKORO_SR) -> np.ndarray:
    """Pitch-preserving speed change (ffmpeg atempo). factor 1.15 = 15% faster. 1.0 returns the input."""
    import subprocess

    if abs(factor - 1.0) < 0.005 or not len(audio):
        return audio
    factor = max(0.5, min(2.0, factor))
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "pipe:0",
                        "-filter:a", f"atempo={factor:.4f}", "-f", "f32le", "-ar", str(sr), "-ac", "1", "pipe:1"],
                       input=audio.astype(np.float32).tobytes(), capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def speech_seconds(audio: np.ndarray, sr: int = KOKORO_SR) -> float:
    """Duration between the first and last audible sample (leading/trailing silence excluded)."""
    idx = np.where(np.abs(audio) > 0.004)[0]
    return (idx[-1] - idx[0]) / sr if len(idx) else 0.0


def words_per_minute(text: str, audio: np.ndarray, sr: int = KOKORO_SR) -> float:
    sec = speech_seconds(audio, sr)
    return len(text.split()) / sec * 60 if sec else 0.0


def active_speech_seconds(audio: np.ndarray, sr: int = KOKORO_SR, pause: float = 0.6) -> float:
    """Speech time without leading/trailing silence AND without pauses longer than `pause` seconds."""
    if not len(audio):
        return 0.0
    win = max(1, int(sr * 0.02))
    n = len(audio) // win
    if n == 0:
        return 0.0
    rms = np.sqrt((audio[: n * win].reshape(n, win) ** 2).mean(axis=1))
    loud = rms > 0.006
    if not loud.any():
        return 0.0
    first, last = np.argmax(loud), n - 1 - np.argmax(loud[::-1])
    seg = loud[first:last + 1]
    total, run = 0, 0
    max_gap = int(pause / 0.02)
    for v in seg:
        if v:
            total += 1 + (run if run <= max_gap else 0)
            run = 0
        else:
            run += 1
    return total * 0.02


def spoken_words(text: str) -> int:
    """Roughly how many words the narrator SAYS: '$1,368.5 billion' is about 9 spoken words, '22.36%' about 5."""
    import re as _re

    n = 0
    for tok in text.replace("*", "").split():
        m = _re.search(r"\d[\d,]*(?:\.\d+)?", tok)
        if not m:
            n += 1
            continue
        num = m.group(0).replace(",", "")
        whole, _, frac = num.partition(".")
        digits = len(whole.lstrip("0")) or 1
        n += {1: 1, 2: 2, 3: 4, 4: 5, 5: 6, 6: 8}.get(digits, 9) + (1 + len(frac) if frac else 0)
        n += ("$" in tok) + ("%" in tok)
    return n


def spoken_wpm(text: str, audio: np.ndarray, sr: int = KOKORO_SR) -> float:
    sec = active_speech_seconds(audio, sr)
    return spoken_words(text) / sec * 60 if sec else 0.0


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
                 cache_dir: Path = Path("data/tts_cache"), ledger: SpendLedger | None = None, session=None,
                 retries: int = 5, backoff_sec: float = 5.0, sleep=time.sleep, speed: float = 1.0):
        if not api_key:
            raise VoiceUnavailable("GEMINI_API_KEY is not set")
        check_model(model)
        self._key, self.model, self.voice, self.style = api_key, model, voice, style
        self.retries, self.backoff, self._sleep = retries, backoff_sec, sleep
        self.speed = speed
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
            raise VoiceUnavailable(f"monthly voice budget: ${self.ledger.spent():.2f} spent + ~${usd_needed:.2f} needed "
                                 f"> ${self.budget:.2f}")

    # -- synthesis ---------------------------------------------------------------------------------------
    @staticmethod
    def _prep(text: str) -> str:
        t = normalize_text(text.replace("*", ""))
        for w, r in BRAND_RESPELL.items():
            t = t.replace(w, r)
        return t

    def _request(self, text: str) -> tuple[np.ndarray, int]:
        """One synthesis with retries and exponential backoff (5, 10, 20, 40, 80 s + jitter; honours Retry-After)."""
        last = ""
        for attempt in range(self.retries + 1):
            if attempt:
                self._sleep(min(120.0, self._wait or self.backoff * 2 ** (attempt - 1)) + random.uniform(0, 1))
            self._wait = 0.0
            try:
                return self._request_once(text)
            except _Retryable as exc:
                last = str(exc)
        raise VoiceUnavailable(f"Gemini TTS unavailable after {self.retries + 1} attempts ({last})")

    _wait = 0.0

    STRICT = ("{style}\n\nRead ONLY the transcript below aloud, word for word. Do not read these instructions, do "
              "not add anything.\nTRANSCRIPT:\n{text}")

    def _request_once(self, text: str) -> tuple[np.ndarray, int]:
        prompt = (self.STRICT.format(style=self.style, text=text) if getattr(self, "_strict", False)
                  else f"{self.style}\n\n{text}")
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["AUDIO"],
                                     "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": self.voice}}}}}
        try:
            r = self.http.post(API.format(model=self.model), headers={"x-goog-api-key": self._key}, json=body, timeout=180)
        except requests.RequestException as exc:
            raise _Retryable(f"network error: {type(exc).__name__}") from None
        if r.status_code in PERMANENT:
            raise VoiceUnavailable(f"Gemini TTS HTTP {r.status_code}: {PERMANENT[r.status_code]}")
        if r.status_code != 200:
            try:
                self._wait = float(r.headers.get("Retry-After", 0) or 0) if hasattr(r, "headers") else 0.0
            except ValueError:
                self._wait = 0.0
            raise _Retryable(f"HTTP {r.status_code}")
        data = r.json()
        try:
            part = data["candidates"][0]["content"]["parts"][0]["inlineData"]
        except (KeyError, IndexError, TypeError):
            raise _Retryable("no audio in the response") from None
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

    def _save_debug(self, prepped: str, audio: np.ndarray, tag: str) -> None:
        """Keep the rejected clip and its text for inspection (data/voice_debug/)."""
        try:
            import soundfile as sf

            d = self.cache.parent / "voice_debug"
            d.mkdir(parents=True, exist_ok=True)
            stem = self._key_for(prepped).stem + f"_{tag}"
            sf.write(d / f"{stem}.wav", audio, KOKORO_SR)
            (d / f"{stem}.txt").write_text(prepped)
        except Exception:  # noqa: BLE001  debugging aid only
            pass

    def narrate(self, text: str, lead_in: float = 0.15, tail: float = 0.45) -> Narration:
        display = [s.replace("*", "") for s in split_sentences(" ".join(text.split()))]
        prepped = self._prep(text)
        audio = apply_tempo(self._scene_audio(prepped), self.speed)  # raw audio cached; tempo after
        n_words = len(text.split())
        if n_words >= 8 and spoken_wpm(text, audio) < MIN_SANE_WPM:
            # far too much audio for the words: usually the model read the style instruction aloud too, or repeated
            # itself. Ask again with the transcript clearly marked as the ONLY thing to read (same voice + style).
            log.warning("scene audio abnormally slow (%.0f spoken wpm) for: %r; requesting it again (strict)",
                        spoken_wpm(text, audio), text[:120])
            self._save_debug(prepped, audio, "first")
            self._key_for(prepped).unlink(missing_ok=True)
            self._strict = True
            try:
                audio = apply_tempo(self._scene_audio(prepped), self.speed)
            finally:
                self._strict = False
            if spoken_wpm(text, audio) < MIN_SANE_WPM:
                self._save_debug(prepped, audio, "strict")
                self._key_for(prepped).unlink(missing_ok=True)
                raise VoiceUnavailable(
                    f"speech came back abnormally slow twice ({spoken_wpm(text, audio):.0f} spoken words/min, "
                    f"{active_speech_seconds(audio):.1f} s for {n_words} words) in the scene: \"{text[:160]}\"; "
                    "the video is held instead of using it")
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
