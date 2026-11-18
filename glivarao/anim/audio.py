"""Original music bed, sound effects and the final audio mix — all synthesized in code (no samples, no
licences, no cost).

Mix: narration (lead) + music bed ducked under the voice + SFX at animation cue times. Loudness is then
normalised to -14 LUFS by the renderer (two-pass loudnorm).
"""
from __future__ import annotations

import math

import numpy as np

SR = 24_000
rng_global = np.random.default_rng(7)


def _env(n: int, attack: float, release: float) -> np.ndarray:
    a = max(1, int(attack * SR))
    r = max(1, int(release * SR))
    e = np.ones(n, dtype=np.float32)
    a = min(a, n)
    e[:a] = np.linspace(0, 1, a, dtype=np.float32)
    if r < n:
        e[-r:] *= np.exp(-np.linspace(0, 5, r, dtype=np.float32))
    return e


def _lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    a = math.exp(-2 * math.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):  # one-pole filter (fine for short SFX)
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def _lowpass_fast(x: np.ndarray, cutoff: float) -> np.ndarray:
    """Vectorised low-pass via FFT brick-wall with a soft knee (for long music buffers)."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / (1 + (f / cutoff) ** 4)
    return np.fft.irfft(X, n=len(x)).astype(np.float32)


# ------------------------------------------------------------------ music
NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _hz(name: str, octave: int) -> float:
    return 440.0 * 2 ** ((NOTE[name] + 12 * (octave - 4) - 9) / 12)


def _piano(freq: float, dur: float, vel: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    tone = sum(amp * np.sin(2 * np.pi * freq * k * t) * np.exp(-t * (1.8 + 1.4 * k))
               for k, amp in ((1, 1.0), (2, 0.42), (3, 0.18), (4, 0.08)))
    return (vel * tone * _env(n, 0.006, 0.25)).astype(np.float32)


def _pad(freqs: list[float], dur: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    sig = sum(np.sin(2 * np.pi * f * t) + 0.6 * np.sin(2 * np.pi * f * 1.003 * t + 1.3) for f in freqs)
    return (sig / (len(freqs) * 1.6) * _env(n, dur * 0.35, dur * 0.4)).astype(np.float32)


PROGRESSIONS = [  # calm, slightly hopeful, documentary-friendly
    [("A", "C", "E"), ("F", "A", "C"), ("C", "E", "G"), ("G", "B", "D")],
    [("C", "E", "G"), ("A", "C", "E"), ("F", "A", "C"), ("G", "B", "D")],
    [("D", "F", "A"), ("G", "B", "D"), ("C", "E", "G"), ("A", "C", "E")],
]


def music_bed(seconds: float, seed: int = 0, bpm: int = 84) -> np.ndarray:
    """Soft piano arpeggios over a pad. Seeded, so each video gets its own variation."""
    rng = np.random.default_rng(seed)
    prog = PROGRESSIONS[seed % len(PROGRESSIONS)]
    beat = 60 / bpm
    bar = 4 * beat
    n = int(seconds * SR) + SR
    out = np.zeros(n, dtype=np.float32)
    t, i = 0.0, 0
    patterns = [[0, 1, 2, 1, 0, 2, 1, 2], [0, 2, 1, 2, 0, 1, 2, 1], [0, 1, 2, 2, 1, 0, 1, 2]]
    while t < seconds:
        chord = prog[i % len(prog)]
        pad = _pad([_hz(chord[0], 3), _hz(chord[1], 3), _hz(chord[2], 3)], bar * 1.05)
        s0 = int(t * SR)
        out[s0:s0 + len(pad)] += 0.22 * pad[: max(0, n - s0)]
        bass = _piano(_hz(chord[0], 2), bar, 0.35)
        out[s0:s0 + len(bass)] += bass[: max(0, n - s0)]
        pat = patterns[(i // 4 + seed) % len(patterns)]
        for k, idx in enumerate(pat):
            if rng.random() < 0.12:  # occasional rest keeps it human
                continue
            octave = 4 if idx < 2 else 5
            note = _piano(_hz(chord[idx], octave), beat * 1.6, 0.16 + 0.05 * rng.random())
            st = int((t + k * beat / 2 + rng.normal(0, 0.006)) * SR)
            if 0 <= st < n:
                out[st:st + len(note)] += note[: n - st]
        t += bar
        i += 1
    out = _lowpass_fast(out[: int(seconds * SR)], 3200)
    fade = int(min(2.5, seconds / 4) * SR)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    return out / (np.abs(out).max() or 1)


# ------------------------------------------------------------------ sound effects
SFX_PEAK = {"pencil": 0.45, "whoosh": 0.6, "pop": 0.5, "coin": 0.45, "chime": 0.5}


def sfx(kind: str, seed: int = 0) -> np.ndarray:
    """Each effect normalised to its own fixed peak so none can clip or overpower the voice."""
    x = _sfx_raw(kind, seed)
    return (x / (np.abs(x).max() or 1.0) * SFX_PEAK[kind]).astype(np.float32)


def _sfx_raw(kind: str, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if kind == "pencil":  # graphite scratch: filtered noise bursts
        n = int(0.55 * SR)
        noise = rng.standard_normal(n).astype(np.float32)
        hp = noise - _lowpass(noise, 1800)
        strokes = np.abs(np.sin(np.linspace(0, 7 * np.pi, n))) ** 0.6
        return (0.35 * hp * strokes * _env(n, 0.02, 0.15)).astype(np.float32)
    if kind == "whoosh":  # air sweep
        n = int(0.6 * SR)
        noise = rng.standard_normal(n).astype(np.float32)
        x = np.zeros(n, dtype=np.float32)
        for j, c in enumerate((400, 900, 1800, 3000)):
            seg = slice(j * n // 4, (j + 1) * n // 4)
            x[seg] = _lowpass(noise[seg], c)
        shape = np.sin(np.linspace(0, np.pi, n)) ** 2
        return (0.9 * x * shape).astype(np.float32)
    if kind == "pop":  # paper/note pop
        n = int(0.12 * SR)
        t = np.arange(n) / SR
        f = 900 * np.exp(-t * 18) + 250
        return (0.5 * np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.002, 0.1)).astype(np.float32)
    if kind == "coin":  # metallic ting (inharmonic partials)
        n = int(0.5 * SR)
        t = np.arange(n) / SR
        partials = (2400, 3170, 4230, 5600)
        sig = sum(np.sin(2 * np.pi * (p * (1 + 0.01 * rng.random())) * t) * np.exp(-t * (8 + i * 3))
                  for i, p in enumerate(partials))
        return (0.22 * sig).astype(np.float32)
    if kind == "chime":  # gentle reveal chime
        n = int(1.4 * SR)
        out = np.zeros(n, dtype=np.float32)
        for k, (nm, octv) in enumerate((("C", 5), ("E", 5), ("G", 5))):
            note = _piano(_hz(nm, octv), 1.2, 0.35)
            st = int(k * 0.07 * SR)
            out[st:st + len(note)] += note[: n - st]
        return out
    raise ValueError(kind)


def cue_list(plans, scene_starts: list[float]) -> list[tuple[float, str]]:
    """Map animation events (from the director's plans) to sound effects at absolute times."""
    cues = []
    for plan, t0 in zip(plans, scene_starts):
        if t0 > 0 and plan.transition in ("push", "wipe", "iris"):
            cues.append((t0 + 0.02, "whoosh"))
        cues.append((t0 + 0.3, "pencil"))  # title card being lettered
        if plan.chart_start is not None:
            cues.append((t0 + plan.chart_start, "pencil"))
            cues.append((t0 + plan.chart_start + plan.chart_dur, "chime"))
        if plan.icon_start is not None:
            cues.append((t0 + plan.icon_start + 0.1, "pop"))
        for _, nt in plan.notes:
            cues.append((t0 + nt + 0.15, "pop"))
        for kind, ft in plan.fx:
            if kind == "coins":
                for k in range(6):
                    cues.append((t0 + ft + 0.45 + k * 0.11, "coin"))
            elif kind == "bills":
                cues.append((t0 + ft, "whoosh"))
    return sorted(cues)


# Narrator voice chain (applied to the dry voice before mixing):
# rumble cut -> warmth -> de-box -> presence -> de-ess -> gentle compression.
VOICE_CHAIN = ",".join([
    "highpass=f=75",
    "equalizer=f=160:t=q:w=1.0:g=1.5",     # warmth / chest
    "equalizer=f=380:t=q:w=1.2:g=-1.5",    # reduce boxiness
    "equalizer=f=3200:t=q:w=1.4:g=1.8",    # presence / intelligibility
    "deesser=i=0.35:f=0.5",
    "acompressor=threshold=0.12:ratio=2.5:attack=8:release=140:makeup=1.6:knee=4",
])


def master_voice(voice: np.ndarray, sr: int = SR) -> np.ndarray:
    """Run the narrator through the voice chain with ffmpeg (float32 in/out, same length)."""
    import subprocess

    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "pipe:0",
         "-af", VOICE_CHAIN, "-f", "f32le", "-ar", str(sr), "-ac", "1", "pipe:1"],
        input=voice.astype(np.float32).tobytes(), capture_output=True, check=True)
    out = np.frombuffer(proc.stdout, dtype=np.float32)
    if len(out) < len(voice):
        out = np.pad(out, (0, len(voice) - len(out)))
    return out[: len(voice)].copy()


def measure_loudness(path) -> dict:
    """EBU R128 integrated loudness (LUFS) and true peak (dBTP) via ffmpeg."""
    import json
    import subprocess

    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af",
                          "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
    return {"lufs": float(m["input_i"]), "true_peak": float(m["input_tp"]), "lra": float(m["input_lra"])}


def master_to_lufs(src, dst, target: float = -14.0, ceiling_db: float = -1.5) -> dict:
    """Final master: exact make-up gain to the target loudness, then a fast true-peak limiter at the ceiling.
    Returns the measured result (re-measured after processing)."""
    import subprocess

    before = measure_loudness(src)
    gain = target - before["lufs"]
    limit = 10 ** (ceiling_db / 20)
    for _ in range(3):  # limiting lowers loudness slightly; nudge until within 0.3 LU
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-af",
                        # float processing (no integer clipping before the limiter); limit 0.5 dB under the
                        # ceiling and oversample 4x so inter-sample (true) peaks also stay below it
                        f"aformat=sample_fmts=fltp,aresample=192000,volume={gain:.2f}dB,"
                        f"alimiter=limit={limit * 10 ** (-0.5 / 20):.4f}:attack=1:release=60:level=false,"
                        f"aresample=48000",
                        "-ar", "48000", "-c:a", "pcm_s16le", str(dst)], check=True)
        after = measure_loudness(dst)
        if abs(after["lufs"] - target) <= 0.3 and after["true_peak"] <= ceiling_db + 0.05:
            break
        gain += target - after["lufs"]
    return {"before": before, "after": after, "gain_db": round(gain, 2)}


def duck_gain(voice: np.ndarray, music_level: float = 0.16, duck_to: float = 0.35) -> np.ndarray:
    """Music gain per sample: full level in pauses, `duck_to` x level while the narrator speaks."""
    win = int(0.05 * SR)
    env = np.sqrt(np.convolve(voice ** 2, np.ones(win) / win, mode="same"))
    env = env / (np.percentile(env[env > 1e-4], 90) if np.any(env > 1e-4) else 1.0)
    speaking = np.clip(env * 3, 0, 1)
    smooth = int(0.3 * SR)
    speaking = np.convolve(speaking, np.ones(smooth) / smooth, mode="same")
    return (music_level * (1 - (1 - duck_to) * np.clip(speaking, 0, 1))).astype(np.float32)


def mix(voice: np.ndarray, cues: list[tuple[float, str]], seed: int = 0, music_level: float = 0.09,
        duck_to: float = 0.4, sfx_level: float = 0.45) -> np.ndarray:
    """voice: float32 mono at SR. Returns the mixed track (same length)."""
    voice = master_voice(voice)
    n = len(voice)
    music = music_bed(n / SR, seed=seed)[:n]
    if len(music) < n:
        music = np.pad(music, (0, n - len(music)))
    out = voice + music * duck_gain(voice, music_level, duck_to)
    cache: dict[str, np.ndarray] = {}
    for k, (t, kind) in enumerate(cues):
        s = cache.setdefault(kind, sfx(kind, seed + k))
        i = int(t * SR)
        if 0 <= i < n:
            seg = s[: n - i]
            out[i:i + len(seg)] += sfx_level * seg
    peak = np.abs(out).max() or 1.0
    return (out / peak * 0.95).astype(np.float32)
