"""Held videos: one broken held job never stops the daily run (logged, one alert, released, marked failed), and
`drop-held` takes chosen held videos off hold for good. Nothing is uploaded; files are kept."""
import json

import pytest

from glivarao import daily_v2
from glivarao.models import JobStatus

OLD = ["20261122-short-20df1e", "20261122-short-22ec66", "20261122-short-d91d99"]


def _held(store, settings, job_id=None, card=None, brief=True):
    job = store.create("short", "ACA deadline")
    if job_id:                                  # the exact ids from the server
        store.conn.execute("UPDATE jobs SET id=? WHERE id=?", (job_id, job.id))
        store.conn.commit()
        job.id = job_id
        store.save(job)
    out = settings.output_dir / job.id
    out.mkdir(parents=True, exist_ok=True)
    job.script_path = str(out / "script.json")
    (out / "script.json").write_text("{}")
    (out / "held_render.json").write_text(json.dumps({"card": card, "date": "2026-11-22", "creator": "",
                                                       "writer": "claude", "item_id": None, "sim": {}}))
    if brief:
        (out / "brief.json").write_text("not json")          # broken on purpose where used
    store.transition(job, JobStatus.SCRIPTED, "held")
    daily_v2._hold(store, job.id, "voice down")
    return job.id


def test_one_broken_held_job_never_stops_the_others(settings, store, monkeypatch):
    alerts = []
    monkeypatch.setattr(daily_v2, "_notify", lambda st, t: alerts.append(t))
    bad = _held(store, settings, brief=False)                 # no brief, no card -> error
    good = _held(store, settings)
    monkeypatch.setattr("glivarao.content.brief.load_brief", lambda p: type("B", (), {"topic": "ACA"})())
    monkeypatch.setattr(daily_v2, "render_and_review",
                        lambda j, *a, **k: (j.id, "short", "pending_approval", "v", ""))
    monkeypatch.setattr("glivarao.models.Script.model_validate_json", classmethod(lambda c, t: object()))
    monkeypatch.setattr("glivarao.studio.factcheck.check_claims", lambda *a: [])
    got = daily_v2.retry_held_videos(settings, store, send=True)
    assert [g[0] for g in got] == [good]                      # the good one still went through
    assert bad not in daily_v2.held_videos(store)             # released
    assert store.get(bad).status == JobStatus.FAILED          # never sent
    assert sum("could not be made again" in a for a in alerts) == 1
    _held(store, settings, brief=False)
    daily_v2.retry_held_videos(settings, store, send=True)
    assert sum("could not be made again" in a for a in alerts) == 2     # one alert per broken job, not per retry


def test_daily_run_continues_when_held_retry_raises(settings, store, monkeypatch):
    _held(store, settings)
    monkeypatch.setattr(daily_v2, "retry_held_videos", lambda *a, **k: (_ for _ in ()).throw(TypeError("boom")))
    class Reached(Exception):
        pass

    def next_step(s):
        raise Reached()

    monkeypatch.setattr(daily_v2, "paid_writer_allowed", next_step)
    with pytest.raises(Reached):                              # production went on past the held retry
        daily_v2.run_daily_v2(settings, store, send=False)


def test_drop_held_by_id_and_by_date(settings, store, capsys):
    for jid in OLD:
        _held(store, settings, job_id=jid)
    keep = _held(store, settings)                             # made today: kept by --all-before
    got = daily_v2.drop_held(store, [OLD[0]])
    assert got == [(OLD[0], "dropped: marked failed, never sent (files kept)")]
    assert store.get(OLD[0]).status == JobStatus.FAILED and OLD[0] not in daily_v2.held_videos(store)
    from datetime import date

    got = dict(daily_v2.drop_held(store, before=date(2026, 11, 23)))
    assert set(got) == {OLD[1], OLD[2]} and keep in daily_v2.held_videos(store)
    assert (settings.output_dir / OLD[1] / "script.json").exists()               # files kept
    assert daily_v2.drop_held(store, [OLD[0]]) == [(OLD[0], "not on hold (nothing changed)")]


def test_drop_held_cli(settings, store, monkeypatch, capsys):
    from glivarao import __main__ as cli

    for jid in OLD:
        _held(store, settings, job_id=jid)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    cli.main(["drop-held"])
    out = capsys.readouterr().out
    assert all(j in out for j in OLD) and "drop with" in out
    cli.main(["drop-held", *OLD])
    out = capsys.readouterr().out
    assert out.count("dropped: marked failed") == 3 and daily_v2.held_videos(store) == {}
