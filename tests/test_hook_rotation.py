"""Hook types: assigned before writing (least recently used, never the last 3), a rejected video doesn't count,
and one hook-only retry (scene 0) when VARIETY still fires; other scenes and sources stay unchanged."""
import json

from glivarao.models import JobStatus
from glivarao.studio import variety
from tests.test_e2e_dryrun import fake_claude, world  # noqa: F401  (fixture)


def _rec(store, fmt, hook, status=JobStatus.APPROVED):
    job = store.create(fmt, "t")
    for st in (JobStatus.SCRIPTED, JobStatus.RENDERED, JobStatus.PENDING_APPROVAL):
        store.transition(store.get(job.id), st, "")
    if status != JobStatus.PENDING_APPROVAL:
        store.transition(store.get(job.id), status, "")
    variety.record(store, fmt, {"job": job.id, "hook_type": hook, "structure": "s", "opening": hook,
                                "ending": hook})
    return job.id


def test_rotation_least_recently_used_and_never_the_last_three(store):
    assert variety.required_hook(store, "short") == "number"                 # never used: first in order
    for h in ("number", "mistake", "myth"):
        _rec(store, "short", h)
    assert variety.recent_hooks(store, "short") == ["number", "mistake", "myth"]
    assert variety.required_hook(store, "short") == "story"
    assert variety.required_hook(store, "short", ("story",)) == "comparison"
    _rec(store, "long", "story")                                             # other format: doesn't count
    assert variety.required_hook(store, "short") == "story"


def test_rejected_video_is_not_the_previous_video(store):
    _rec(store, "short", "number")
    _rec(store, "short", "warning", status=JobStatus.REJECTED)
    assert variety.previous(store, "short")["hook_type"] == "number"
    assert "warning" not in variety.recent_hooks(store, "short")


def test_writer_is_told_the_hooks_to_avoid_and_the_one_to_use(world, monkeypatch):  # noqa: F811
    from glivarao import daily_v2
    from glivarao.scriptgen import claude as C

    s, store, calls = world
    for h in ("number", "mistake", "myth"):
        _rec(store, "short", h)
    seen = []
    orig = C._ask

    def spy(settings_, prompt, fmt, client=None, ledger=None):
        seen.append(prompt)
        return orig(settings_, prompt, fmt, client, ledger)

    monkeypatch.setattr(C, "_ask", spy)
    daily_v2.make_now(s, store, 1, short=True, send=False)
    first = seen[0]
    assert "Do NOT use these hook types (used by the last videos): number, mistake, myth" in first
    assert "ASSIGNED HOOK TYPE (rotation, checked by code): STORY" in first


def _number_hook_world(world, monkeypatch, fixed_hook=None):  # noqa: F811
    from glivarao.scriptgen import claude as C

    s, store, calls = world
    _rec(store, "short", "number")
    hook_calls = []

    def ask(settings_, prompt, fmt, client=None, ledger=None):
        d = fake_claude(prompt, fmt, len(calls) + 1)
        calls.append((fmt, prompt[:60]))
        if fmt == "short":
            d["scenes"][0]["narration"] = "Your card could be charging you 22.36% a year. Here's what that means."
        if prompt.startswith("Rewrite ONLY the narration of the FIRST scene"):
            hook_calls.append(prompt)
            draft = json.loads(prompt.split("DRAFT:\n", 1)[1])
            d = {k: draft[k] for k in ("title", "description", "tags", "thumbnail_text", "hook", "scenes")}
            d["scenes"] = [dict(sc) for sc in d["scenes"]]
            if fixed_hook:
                d["scenes"][0]["narration"] = fixed_hook
            d["scenes"][-1]["narration"] = "CHANGED BY THE MODEL"          # must be ignored
        return d

    monkeypatch.setattr(C, "_ask", ask)
    return s, store, hook_calls


def test_hook_only_retry_keeps_other_scenes_and_sources(world, monkeypatch):  # noqa: F811
    from glivarao import daily_v2

    s, store, hook_calls = _number_hook_world(
        world, monkeypatch, fixed_hook="Your card's minimum payment trap costs 22.36% a year. "
                                       "Here's what that means.")
    r = daily_v2.make_now(s, store, 1, short=True, send=False)
    job = r.jobs[-1]
    assert job[2] == "rendered" and len(hook_calls) == 1                     # exactly one retry
    out = s.output_dir / job[0]
    script = json.loads((out / "script.json").read_text())
    assert script["scenes"][0]["narration"].startswith("Your card's minimum payment trap")
    assert script["scenes"][-1]["narration"] != "CHANGED BY THE MODEL"       # other scenes unchanged
    assert "VARIETY" not in (out / "compliance.txt").read_text()
    assert "federalreserve.gov" in (out / "fact_check.md").read_text()      # sources preserved


def test_retry_happens_once_then_the_warning_stays(world, monkeypatch):  # noqa: F811
    from glivarao import daily_v2

    s, store, hook_calls = _number_hook_world(world, monkeypatch)         # the rewrite keeps a number hook
    r = daily_v2.make_now(s, store, 1, short=True, send=False)
    assert r.jobs[-1][2] == "rendered" and len(hook_calls) == 1
    assert "VARIETY" in (s.output_dir / r.jobs[-1][0] / "compliance.txt").read_text()


def test_only_approved_or_uploaded_videos_count(store):
    _rec(store, "short", "number")
    _rec(store, "short", "story", status=JobStatus.PENDING_APPROVAL)    # still in review: doesn't count
    assert variety.recent_hooks(store, "short") == ["number"]
