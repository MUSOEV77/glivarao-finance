import pytest

from glivarao.art.charts import compound_series, fmt_value
from glivarao.compliance import check_script, overlap_ratio
from glivarao.config import Settings
from glivarao.models import JobStatus
from glivarao.render.subtitles import chunk_text, scene_cues, write_srt
from glivarao.scriptgen.offline import generate_offline
from glivarao.storage import InvalidTransition
from glivarao.topics import pick_topic


def test_settings_redacts_secrets():
    s = Settings(anthropic_api_key="sk-secret", telegram_bot_token="123:abc")
    red = s.redacted()
    assert red["anthropic_api_key"] == "set" and red["telegram_bot_token"] == "set"
    assert "sk-secret" not in str(red) and "123:abc" not in str(red)
    assert Settings(mode="dry-run").dry_run and not Settings(mode="production").dry_run


def test_status_machine_blocks_skipping_approval(store):
    job = store.create("short", "x")
    store.transition(job, JobStatus.SCRIPTED)
    store.transition(job, JobStatus.RENDERED)
    with pytest.raises(InvalidTransition):
        store.transition(job, JobStatus.PUBLISHED)
    with pytest.raises(InvalidTransition):
        store.transition(job, JobStatus.APPROVED)  # must go through PENDING_APPROVAL
    store.transition(job, JobStatus.PENDING_APPROVAL)
    store.transition(job, JobStatus.APPROVED)
    assert store.get(job.id).status == JobStatus.APPROVED
    assert [e["to_status"] for e in store.events(job.id)][-1] == "approved"


def test_topic_selection_skips_recent():
    topics = ["A", "B", "C"]
    for seed in range(20):
        assert pick_topic(["A", "B"], seed=seed, topics=topics) == "C"


def test_compound_series_matches_closed_form():
    yrs, bal, contrib = compound_series(1000, 0.07, 30, 100)
    r, n = 0.07 / 12, 360
    expected = 1000 * (1 + r) ** n + 100 * ((1 + r) ** n - 1) / r
    assert yrs[-1] == 30 and abs(bal[-1] - expected) < 0.01
    assert contrib[-1] == 1000 + 100 * 360
    assert fmt_value(122_000, "$") == "$122K" and fmt_value(7, "%") == "7%"


def test_offline_scripts_pass_compliance():
    for fmt in ("long", "short"):
        script = generate_offline("How compound interest really works", fmt)
        report = check_script(script, enforce_length=False)
        assert report.ok, report.summary()


def test_offline_long_hits_production_length():
    script = generate_offline("Index funds explained", "long", minutes=16.5)
    from glivarao.compliance import LENGTH_RULES

    assert LENGTH_RULES["long"][0] <= script.word_count <= LENGTH_RULES["long"][1]
    report = check_script(script, enforce_length=True)
    assert not any("Word count" in e for e in report.errors)  # length OK; repetition is flagged separately


def test_compliance_flags_guarantees_and_missing_disclaimer():
    script = generate_offline("Test", "short")
    script.scenes[1].narration = "This is a risk-free way to double your money, guaranteed."
    script.scenes[-1].narration = "Bye."
    report = check_script(script, enforce_length=False)
    joined = " ".join(report.errors)
    assert "risk-free" in joined and "double your money" in joined and "guaranteed" in joined
    assert "disclaimer" in joined


def test_compliance_flags_copied_narration():
    a = generate_offline("Topic one", "long", minutes=3).full_narration
    assert overlap_ratio(a, a) == 1.0
    script = generate_offline("Topic one", "long", minutes=3)
    assert not check_script(script, enforce_length=False, previous_scripts=[a]).ok


def test_subtitle_chunking_and_srt(tmp_path):
    chunks = chunk_text("One two three four five six seven eight nine ten eleven. Short one.", 5)
    assert all(len(c.split()) <= 5 for c in chunks) and chunks[-1] == "Short one."
    cues = scene_cues("Hello there, friend. How are you today?", 1.0, 4.0, 3)
    assert cues[0].start == 1.0 and abs(cues[-1].end - 5.0) < 1e-6
    srt = write_srt(cues, tmp_path / "c.srt").read_text()
    assert srt.startswith("1\n00:00:01,000 --> ")


def test_compliance_flags_self_repeating_script():
    script = generate_offline("Index funds explained", "long", minutes=16.5)  # offline pads with filler
    assert any("repeat narration" in e for e in check_script(script, enforce_length=True).errors)
    assert any("repeat narration" in w for w in check_script(script, enforce_length=False).warnings)
