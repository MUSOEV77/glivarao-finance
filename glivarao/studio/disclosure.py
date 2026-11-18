"""AI disclosure, following each platform's rules where they apply.

YouTube ("altered or synthetic content", Help article 14328491): disclosure is required for REALISTIC content a
viewer could mistake for a real person, place or event (for example a cloned real voice, realistic AI people or
altered footage of real events). Clearly unrealistic content such as animation is exempt.
* GLIVARAO's videos are illustrated, show no realistic people and use a generic narrator voice that imitates no
  one, so by default the YouTube setting is "No", with a plain-language transparency note in every description.
* If realistic AI imagery or video is ever added, or a real person's voice is used, the flag switches to "Yes".

TikTok and Instagram/Facebook ask creators to label realistic AI-generated audio or video. A natural-sounding AI
narration voice counts as realistic AI audio, so the review message reminds you to switch those labels ON.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Disclosure:
    youtube_altered_content: bool
    reasons: list[str] = field(default_factory=list)
    description_note: str = ""
    platform_notes: list[str] = field(default_factory=list)

    def review_text(self) -> str:
        yt = "YES" if self.youtube_altered_content else "No"
        return ("AI DISCLOSURE\n"
                f"- YouTube Studio → Altered or synthetic content: {yt} ({'; '.join(self.reasons)})\n"
                + "\n".join(f"- {n}" for n in self.platform_notes))


def disclosure_for(voice_label: str, realistic_ai_visuals: bool = False, real_person_voice: bool = False,
                   creator_voice_used: bool = False) -> Disclosure:
    synthetic_voice = not creator_voice_used
    reasons = []
    flag = realistic_ai_visuals or real_person_voice
    if realistic_ai_visuals:
        reasons.append("contains realistic AI-generated visuals")
    if real_person_voice:
        reasons.append("uses a synthetic version of a real person's voice")
    if not flag:
        reasons.append("illustrated visuals, no realistic people or events, generic narrator voice")
    note = ("About this video: the narration is an AI-generated voice and the visuals are illustrated. Research, "
            "script and numbers were prepared with AI assistance and the exact calculations shown, then reviewed and "
            "approved by a person before publishing. The \"My take\" section is the channel host's own view.")
    platform = []
    if synthetic_voice:
        platform += ["TikTok: turn ON the \"AI-generated content\" label (realistic AI voice).",
                     "Instagram/Facebook Reels: add the \"AI info\" label (realistic AI voice)."]
    return Disclosure(flag, reasons, note, platform)


def add_note(description: str, d: Disclosure) -> str:
    if d.description_note in description:
        return description
    return description.rstrip() + "\n\n" + d.description_note + "\n"


__all__ = ["Disclosure", "disclosure_for", "add_note"]
