"""Data models shared across the pipeline."""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

VideoFormat = Literal["long", "short"]

# Illustration ids the renderer knows how to draw (see glivarao/art/illustrations.py).
ILLUSTRATIONS = [
    "piggy_bank", "house", "coin_stack", "credit_card", "dollar_bill", "growth_arrow",
    "shield", "calendar", "shopping_cart", "paycheck", "bank", "scale", "hourglass",
    "warning", "lightbulb", "target",
]
CHARACTERS = ["max", "penny", "duo"]
CHART_KINDS = ["compound_growth", "bar_compare", "line_series", "pie_split", "none"]


class ChartSpec(BaseModel):
    kind: Literal["compound_growth", "bar_compare", "line_series", "pie_split", "none"] = "none"
    title: str = ""
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
    unit: str = ""  # "$", "%", ""
    # Parameters for computed charts (compound_growth): principal, rate (decimal), years, monthly
    params: dict[str, float] = Field(default_factory=dict)
    source: str = "Illustrative example"  # shown on screen; real data must cite its source


class Scene(BaseModel):
    heading: str = Field(description="Short on-screen title, max ~6 words")
    narration: str = Field(description="Exact words the narrator speaks in this scene")
    character: Literal["max", "penny", "duo"] = "max"
    pose: Literal["talk", "point", "think", "cheer", "worry"] = "talk"
    illustration: str = "coin_stack"
    chart: ChartSpec = Field(default_factory=ChartSpec)
    key_points: list[str] = Field(default_factory=list, description="0-3 short bullet callouts")
    # Optional direction for the animated (v2) renderer; the director chooses automatically when unset.
    set: Optional[Literal["studio", "home", "city", "bank", "board"]] = None
    entrance: Optional[Literal["walk_in", "hop_in", "none"]] = None
    transition: Optional[Literal["push", "iris", "fade", "wipe", "cut"]] = None
    money_fx: Optional[Literal["coins", "bills", "none"]] = None
    # Format beat for the editorial renderer: myth, fact, question, case, option_a, option_b, verdict, update,
    # creator (the host's own take). None = ordinary scene.
    beat: Optional[str] = None
    # AI scene illustration (long videos; set by art/ai_visuals.py). None/missing file = code-drawn plate.
    art_path: Optional[str] = None


class Script(BaseModel):
    format: VideoFormat
    topic: str
    title: str = Field(description="YouTube title, <= 90 chars, no clickbait promises")
    description: str
    tags: list[str] = Field(default_factory=list)
    thumbnail_text: str = Field(description="2-5 punchy words for the thumbnail")
    hook: str = ""
    scenes: list[Scene]
    style: Optional[str] = None  # video format: explainer, myth_vs_fact, case_study, viewer_question, comparison, ...

    @property
    def full_narration(self) -> str:
        return "\n".join(s.narration for s in self.scenes)

    @property
    def word_count(self) -> int:
        return len(self.full_narration.split())


class JobStatus(str, Enum):
    PLANNED = "planned"
    SCRIPTED = "scripted"
    REJECTED_COMPLIANCE = "rejected_compliance"
    RENDERED = "rendered"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    FAILED = "failed"


class Job(BaseModel):
    id: str
    format: VideoFormat
    topic: str
    status: JobStatus = JobStatus.PLANNED
    created_at: str
    updated_at: str
    script_path: Optional[str] = None
    video_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    subtitles_path: Optional[str] = None
    duration_sec: Optional[float] = None
    youtube_video_id: Optional[str] = None
    telegram_message_id: Optional[int] = None
    notes: str = ""
