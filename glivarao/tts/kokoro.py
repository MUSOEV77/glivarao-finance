"""Kokoro-82M neural narration (Apache-2.0, runs locally on CPU, no API key, commercial use allowed).

Presenter voice: an American English male documentary narrator (default `am_michael`).

Pipeline per scene:
  1. finance-aware text normalization (401(k), Roth, FICO, S&P, $ and % amounts ...)
  2. grapheme-to-phoneme with misaki (Kokoro's own dictionary-based G2P; espeak-ng is NOT used)
  3. synthesis sentence by sentence, with natural pauses between sentences / clauses and
     slightly slower delivery for questions and emphasized lines
  4. returns exact per-sentence timings so captions and animation cues are synchronized

Words missing from the pronunciation dictionary are collected in `unknown_words` for human review.
Model files: models/kokoro/kokoro-v1.0.onnx and voices-v1.0.bin (see docs/DEPLOYMENT.md).
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "models/kokoro/kokoro-v1.0.onnx"
VOICES = ROOT / "models/kokoro/voices-v1.0.bin"
KOKORO_SR = 24_000

DEFAULT_VOICE = "am_michael"
AMERICAN_MALE_VOICES = ["am_michael", "am_fenrir", "am_puck", "am_echo", "am_eric", "am_liam", "am_onyx",
                        "am_adam", "am_santa"]

# Explicit pronunciations (misaki phoneme alphabet) for finance words its dictionary misses or misreads.
LEXICON = {
    "roth": "ɹˈɔθ",
    "fico": "fˈIkO",
    "nasdaq": "nˈæzdæk",
    "vanguard": "vˈæŋɡɑɹd",
    "annuity": "ənˈuɪɾi",
    "amortization": "ˌæməɹtəzˈAʃən",
}

TEXT_RULES = [  # applied in order before G2P
    (r"\b401\(k\)s?", "four-oh-one-K"),
    (r"\b403\(b\)s?", "four-oh-three-B"),
    (r"\b457\(b\)s?", "four-fifty-seven-B"),
    (r"\b529 plan", "five-twenty-nine plan"),
    (r"\bS&P\s*500\b", "S and P five hundred"),
    (r"\bS&P\b", "S and P"),
    (r"\bW-2\b", "W-two"),
    (r"\b1099\b", "ten ninety-nine"),
    (r"\bvs\.?\s", "versus "),
    (r"\be\.g\.,?", "for example,"),
    (r"\bi\.e\.,?", "that is,"),
    (r"(\d)\s*-\s*(\d)", r"\1 to \2"),            # 5-10 years -> 5 to 10 years
    (r"\$(\d+(?:\.\d+)?)\s*([KkMmBb])\b",          # $5K / $2.5M / $1B
     lambda m: f"{m.group(1)} {dict(k='thousand', m='million', b='billion')[m.group(2).lower()]} dollars"),
    (r"&", " and "),
]


def normalize_text(text: str) -> str:
    t = text.replace("’", "'").replace("“", '"').replace("”", '"').replace("—", ", ").replace("–", " to ")
    for pat, rep in TEXT_RULES:
        t = re.sub(pat, rep, t)
    return re.sub(r"\s+", " ", t).strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?*])\s+(?=[*A-Z0-9\"'$])", text.strip())
    return [p.strip() for p in parts if p.strip()]


@dataclass
class Sentence:
    text: str          # original (display) text
    start: float       # seconds from scene start
    end: float
    emphasis: bool = False
    question: bool = False


@dataclass
class Narration:
    audio: np.ndarray  # float32 mono at KOKORO_SR
    sentences: list[Sentence]
    unknown_words: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return len(self.audio) / KOKORO_SR


class KokoroEngine:
    _lock = threading.Lock()
    _instance: "KokoroEngine | None" = None

    def __init__(self, voice: str = DEFAULT_VOICE, speed: float = 0.94):
        if not MODEL.exists() or not VOICES.exists():
            raise FileNotFoundError(f"Kokoro model files missing in {MODEL.parent} (see docs/DEPLOYMENT.md)")
        from kokoro_onnx import Kokoro
        from misaki import en

        self.kokoro = Kokoro(str(MODEL), str(VOICES))
        self.unknown: list[str] = []
        self.g2p = en.G2P(trf=False, british=False, fallback=self._fallback)
        self.voice = voice
        self.speed = speed

    @classmethod
    def get(cls, voice: str = DEFAULT_VOICE) -> "KokoroEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(voice)
            cls._instance.voice = voice
            return cls._instance

    # -- G2P -------------------------------------------------------------------------------
    def _fallback(self, token):
        """Called by misaki for out-of-dictionary words. Never uses espeak."""
        word = token.text
        low = word.lower().strip("'")
        if low in LEXICON:
            return LEXICON[low], 4
        self.unknown.append(word)
        if word.isupper() and len(word) <= 6:  # unknown acronym: spell it
            ph, _ = self.g2p(". ".join(word) + ".")
            return ph.replace(".", "").strip(), 3
        if "-" in word:
            ph, _ = self.g2p(word.replace("-", " "))
            return ph, 2
        ph, _ = self.g2p(" ".join(word.upper()))  # last resort: letters
        return ph, 1

    def phonemize(self, text: str) -> str:
        words = []
        for w in text.split(" "):  # apply explicit lexicon via misaki's [word](/phonemes/) syntax
            core = re.sub(r"[^\w']", "", w).lower()
            if core in LEXICON:
                w = w.replace(re.sub(r"[^\w']", "", w), f"[{re.sub(r'[^\w]', '', w)}](/{LEXICON[core]}/)")
            words.append(w)
        ph, _ = self.g2p(" ".join(words))
        return ph

    # -- synthesis ---------------------------------------------------------------------------
    def _say(self, text: str, speed: float) -> np.ndarray:
        ph = self.phonemize(normalize_text(text))
        audio, sr = self.kokoro.create(ph, voice=self.voice, speed=speed, is_phonemes=True)
        assert sr == KOKORO_SR
        return _trim(audio.astype(np.float32))

    def narrate(self, text: str, lead_in: float = 0.15, tail: float = 0.45) -> Narration:
        """Synthesize a scene. *word* marks emphasis (slight pause + slower delivery)."""
        self.unknown = []
        chunks, sentences, t = [_silence(lead_in)], [], lead_in
        for raw in split_sentences(text):
            emph = "*" in raw
            display = raw.replace("*", "")
            question = display.rstrip().endswith("?")
            speed = self.speed * (0.93 if emph else 1.0) * (0.97 if question else 1.0)
            audio = self._say(display, speed)
            chunks.append(audio)
            dur = len(audio) / KOKORO_SR
            sentences.append(Sentence(display, t, t + dur, emph, question))
            t += dur
            pause = 0.55 if question else (0.42 if display.endswith((".", "!")) else 0.3)
            if emph:
                pause += 0.12
            chunks.append(_silence(pause))
            t += pause
        chunks[-1] = _silence(tail)
        audio = np.concatenate(chunks)
        peak = float(np.abs(audio).max()) or 1.0
        return Narration(audio * (0.89 / peak), sentences, sorted(set(self.unknown)))


def _silence(sec: float) -> np.ndarray:
    return np.zeros(int(sec * KOKORO_SR), dtype=np.float32)


def _trim(audio: np.ndarray, thresh: float = 0.004) -> np.ndarray:
    idx = np.where(np.abs(audio) > thresh)[0]
    if not len(idx):
        return audio
    pad = int(0.03 * KOKORO_SR)
    return audio[max(0, idx[0] - pad): idx[-1] + pad]
