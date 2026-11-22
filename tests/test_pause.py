"""Production pause: every production entry point refuses while data/PAUSED exists; the CLI exits cleanly (timers
never fail or crash-loop); health shows the pause; install.sh keeps production timers off; nothing is deleted."""
from pathlib import Path

import pytest

from glivarao import __main__ as cli
from glivarao import daily_v2
from glivarao.studio import pause


def test_pause_blocks_every_production_entry_point(settings, store):
    pause.pause(settings, "audit")
    assert pause.status(settings)["reason"] == "audit"
    from glivarao.studio.planner import plan_next
    from glivarao.studio.voice_audition import make_samples

    for call in (lambda: daily_v2.run_daily_v2(settings, store, send=False),
                 lambda: daily_v2.supervised_daily(settings, store, send=False),
                 lambda: daily_v2.retry_held_videos(settings, store, send=False),
                 lambda: daily_v2.remake_video(settings, store, "x", send=False),
                 lambda: plan_next(settings, store),
                 lambda: make_samples(settings, store, settings.output_dir)):
        with pytest.raises(pause.Paused):
            call()
    assert store.list() == []                                    # nothing was created


def test_cli_exits_cleanly_while_paused_and_resume_is_explicit(settings, monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    cli.main(["pause", "--reason", "until approval"])
    cli.main(["daily-v2", "--no-telegram"])                     # no exception, exit 0
    assert "PAUSED" in capsys.readouterr().out
    cli.main(["pause", "--status"])
    assert "until approval" in capsys.readouterr().out
    cli.main(["resume"])
    assert pause.status(settings) is None


def test_health_report_shows_pause(settings, store):
    from glivarao.studio.health import report

    pause.pause(settings, "audit")
    assert "PRODUCTION PAUSED" in report(settings, store)


def test_installer_keeps_production_timers_off_while_paused():
    sh = (Path(__file__).resolve().parents[1] / "deploy" / "install.sh").read_text()
    assert 'if [ -f "$APP_DIR/data/PAUSED" ]' in sh
    paused_branch = sh.split('if [ -f "$APP_DIR/data/PAUSED" ]')[1].split("else")[0]
    assert "disable --now glivarao-daily.timer" in paused_branch and "enable" not in paused_branch.replace(
        "disable", "")
