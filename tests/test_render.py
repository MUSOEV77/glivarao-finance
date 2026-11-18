"""Real rendering through ffmpeg (low fps + silent voice to keep it quick)."""
import shutil

import pytest
from PIL import Image

from glivarao.models import JobStatus
from glivarao.pipeline import produce
from glivarao.render.video import probe

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def test_produce_short_end_to_end(settings, store):
    res = produce(settings, store, "short", topic="Dollar-cost averaging explained")
    job = res.job
    assert job.status == JobStatus.RENDERED  # stops before approval; nothing is sent or published
    info = probe(job.video_path)
    assert (info["width"], info["height"]) == (1080, 1920)
    assert info["video_codec"] == "h264" and info["audio_codec"] == "aac"
    assert abs(info["duration"] - job.duration_sec) < 0.6
    assert Image.open(job.thumbnail_path).size == (720, 1280)
    assert "-->" in open(job.subtitles_path).read()


def test_produce_long_landscape(settings, store):
    res = produce(settings, store, "long", topic="How mortgages and amortization work", minutes=1.5)
    info = probe(res.job.video_path)
    assert (info["width"], info["height"]) == (1920, 1080)
    assert info["duration"] > 60
    thumb = Image.open(res.job.thumbnail_path)
    assert thumb.size == (1280, 720)
