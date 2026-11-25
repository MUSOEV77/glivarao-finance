"""A video made by render-draft (no series) can still get its YouTube link saved; backfill and set-link."""
from glivarao.models import JobStatus
from glivarao.studio import series as S


def _approved(store, settings):
    job = store.create("long", "ACA Open Enrollment")
    for st in (JobStatus.SCRIPTED, JobStatus.RENDERED, JobStatus.PENDING_APPROVAL, JobStatus.APPROVED):
        store.transition(job, st, "")
    return job


def test_set_link_registers_a_missing_episode(store, settings):
    job = _approved(store, settings)
    assert S.episodes(store) == []
    ep = S.set_link(store, job.id, "https://youtu.be/OifqlJEAhKg")
    assert ep and ep["url"] == "https://youtu.be/OifqlJEAhKg" and ep["series"] == "Single videos"
    assert S.set_link(store, "nope", "https://youtu.be/OifqlJEAhKg") is None


def test_backfill_and_cli(store, settings, monkeypatch, capsys):
    from glivarao import __main__ as cli

    job = _approved(store, settings)
    assert S.backfill_episodes(store) == [job.id] and S.backfill_episodes(store) == []
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    cli.main(["set-link", job.id, "https://youtu.be/OifqlJEAhKg"])
    assert "saved" in capsys.readouterr().out
    assert S.episodes(store)[0]["url"] == "https://youtu.be/OifqlJEAhKg"
