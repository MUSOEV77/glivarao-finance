"""Google Cloud Text-to-Speech: Chirp 3 HD narrator (paid, owner approval required).

Same contract as KokoroEngine.narrate(): sentence-by-sentence synthesis with GLIVARAO's own pauses, so
captions, lip-sync and animation cues stay exactly in sync regardless of which voice is used.

Safety:
  * refuses to run unless ALLOW_PAID_APIS=true and an API key is configured;
  * every sentence is cached on disk (voice + rate + text), so re-renders never pay twice;
  * a monthly character ledger enforces a hard cap derived from TTS_MONTHLY_BUDGET_USD.
The API key is sent in a header (never in the URL) so it cannot leak through error messages.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from datetime import date
from pathlib import Path

import numpy as np
import requests

from .kokoro import KOKORO_SR, Narration, Sentence, _silence, normalize_text, split_sentences

API = "https://texttospeech.googleapis.com/v1/text:synthesize"
DEFAULT_VOICE = "en-US-Chirp3-HD-Charon"
# Shortlist for the owner's listening test (Google's own style labels in brackets). Final pick by ear.
CANDIDATE_VOICES = {
    "en-US-Chirp3-HD-Charon": "informative",
    "en-US-Chirp3-HD-Orus": "firm",
    "en-US-Chirp3-HD-Algenib": "gravelly",
    "en-US-Chirp3-HD-Sadaltager": "knowledgeable",
}
# Words Chirp may misread: IPA overrides via the API's custom-pronunciation field.
CUSTOM_PRONUNCIATIONS = {"GLIVARAO": "ɡlɪˈvɑɹoʊ", "HELOC": "ˈhilɑk", "FINRA": "ˈfɪnɹə"}


class PaidTTSError(RuntimeError):
    pass


class BudgetExceeded(PaidTTSError):
    pass


class UsageLedger:
    """Characters billed per calendar month (JSON file; survives restarts)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def used(self, month: str | None = None) -> int:
        return int(self._load().get(month or date.today().strftime("%Y-%m"), 0))

    def add(self, chars: int, month: str | None = None) -> None:
        data = self._load()
        m = month or date.today().strftime("%Y-%m")
        data[m] = int(data.get(m, 0)) + chars
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))


def monthly_char_limit(budget_usd: float, price_per_million: float, free_chars: int) -> int:
    return int(free_chars + budget_usd / price_per_million * 1_000_000)


def billable_text(text: str) -> list[str]:
    """Exactly the sentence strings that will be sent to the API (used for estimates and billing)."""
    out = []
    for para in [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]:
        out += [normalize_text(s.replace("*", "")) for s in split_sentences(" ".join(para.split()))]
    return out


class GoogleChirpNarrator:
    provider = "google_chirp"

    def __init__(self, api_key: str, voice: str = DEFAULT_VOICE, rate: float = 1.0, cache_dir: Path = Path("data/tts_cache"),
                 ledger: UsageLedger | None = None, char_limit: int = 0, session=None):
        if not api_key:
            raise PaidTTSError("GOOGLE_TTS_API_KEY is not set")
        self._key, self.voice, self.rate = api_key, voice, rate
        self.cache = Path(cache_dir)
        self.ledger = ledger or UsageLedger(Path("data/tts_usage.json"))
        self.char_limit = char_limit
        self.http = session or requests.Session()
        self.unknown: list[str] = []
        self.billed_chars = 0

    # -- budget ---------------------------------------------------------------------------------------
    def _cache_path(self, text: str) -> Path:
        h = hashlib.sha256(f"{self.voice}|{self.rate}|{text}".encode()).hexdigest()[:24]
        return self.cache / f"{h}.npy"

    def uncached_chars(self, text: str) -> int:
        return sum(len(s) for s in billable_text(text) if not self._cache_path(s).exists())

    def check_budget(self, chars_needed: int) -> None:
        if self.char_limit and self.ledger.used() + chars_needed > self.char_limit:
            raise BudgetExceeded(f"monthly TTS cap reached: {self.ledger.used():,} used + {chars_needed:,} needed "
                                 f"> {self.char_limit:,} characters")

    # -- synthesis ---------------------------------------------------------------------------------------
    def _request(self, text: str, with_pronunciations: bool = True) -> np.ndarray:
        body = {"input": {"text": text}, "voice": {"languageCode": "en-US", "name": self.voice},
                "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": KOKORO_SR,
                                "speakingRate": self.rate}}
        prons = [{"phrase": w, "phoneticEncoding": "PHONETIC_ENCODING_IPA", "pronunciation": ipa}
                 for w, ipa in CUSTOM_PRONUNCIATIONS.items() if w.lower() in text.lower()]
        if prons and with_pronunciations:
            body["input"]["customPronunciations"] = {"pronunciations": prons}
        try:
            r = self.http.post(API, headers={"X-Goog-Api-Key": self._key}, json=body, timeout=90)
        except requests.RequestException as exc:
            raise PaidTTSError(f"Google TTS request failed: {type(exc).__name__}") from None
        if r.status_code == 400 and prons and with_pronunciations:
            return self._request(text, with_pronunciations=False)  # API rejected overrides: plain text instead
        if r.status_code != 200:
            raise PaidTTSError(f"Google TTS HTTP {r.status_code}")
        import soundfile as sf

        audio, sr = sf.read(io.BytesIO(base64.b64decode(r.json()["audioContent"])), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != KOKORO_SR:  # keep the pipeline's sample rate
            idx = np.linspace(0, len(audio) - 1, int(len(audio) * KOKORO_SR / sr))
            audio = np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
        return audio

    def _say(self, text: str) -> np.ndarray:
        p = self._cache_path(text)
        if p.exists():
            return np.load(p)
        self.check_budget(len(text))
        audio = self._request(text)
        self.ledger.add(len(text))  # Google bills characters sent
        self.billed_chars += len(text)
        p.parent.mkdir(parents=True, exist_ok=True)
        np.save(p, audio)
        return audio

    def narrate(self, text: str, lead_in: float = 0.15, tail: float = 0.45) -> Narration:
        """Same pause rules as KokoroEngine.narrate (sentence 0.42 s, question 0.55 s, emphasis, paragraph beat)."""
        chunks, sentences, t = [_silence(lead_in)], [], lead_in
        paragraph_ends, flat = set(), []
        for para in [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]:
            flat += split_sentences(" ".join(para.split()))
            paragraph_ends.add(len(flat) - 1)
        for idx, raw in enumerate(flat):
            emph = "*" in raw
            display = raw.replace("*", "")
            question = display.rstrip().endswith("?")
            audio = self._say(normalize_text(display))
            chunks.append(audio)
            dur = len(audio) / KOKORO_SR
            sentences.append(Sentence(display, t, t + dur, emph, question))
            t += dur
            pause = 0.55 if question else (0.42 if display.endswith((".", "!")) else 0.3)
            pause += 0.12 if emph else 0
            pause += 0.3 if idx in paragraph_ends else 0
            chunks.append(_silence(pause))
            t += pause
        chunks[-1] = _silence(tail)
        audio = np.concatenate(chunks)
        peak = float(np.abs(audio).max()) or 1.0
        return Narration(audio * (0.89 / peak), sentences, [])
