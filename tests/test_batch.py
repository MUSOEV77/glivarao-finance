"""Batch testing: 5 topics x 3 long parts (how it works / biggest mistakes / step-by-step plan, each with its own
lead fact) + 3-5 single-idea Shorts; never two parts of one topic in a row; ACA before December 15; a ranking
report with the winner and 5 proposals close to it, approved in Telegram. Nothing paid, nothing uploaded."""
import json
from datetime import date

import pytest

from glivarao.studio import batch
from tests.test_e2e_dryrun import world  # noqa: F401  (fixture)


@pytest.fixture
def bstore(store):
    store.kv_set("batch_mode", "on")
    return store


def test_batch_1_plan_follows_every_rule():
    entries = batch.plan(batch.BATCH1)
    assert batch.plan_issues(batch.BATCH1, entries) == []
    assert len(entries) == 14                                            # card-debt Part 1 is already made
    assert all(a["topic"] != b["topic"] for a, b in zip(entries, entries[1:]))
    aca = [e for e in entries if e["topic"] == "aca-dec-15"]
    assert [e["part"] for e in aca] == [1, 2, 3] and max(e["publish"] for e in aca) < "2026-12-15"
    assert entries[-1]["publish"] <= "2026-12-22"                         # 4 weeks
    for t in batch.BATCH1:
        mine = [e for e in entries if e["topic"] == t.slug]
        assert len({e["lead"] for e in mine}) == len(mine)                 # different lead fact per part
        assert 3 <= sum(len(e["shorts"]) for e in mine) <= 5 or t.done_parts
        assert [e["part"] for e in mine] == sorted(e["part"] for e in mine)
    assert not [e for e in entries if e["id"] == "get-out-of-card-debt:p1"]


def test_plan_text_shows_four_weeks():
    class KV:
        def kv_get(self, k, d=None):
            return d
    text = batch.plan_text(KV())
    assert "WEEK 1" in text and "WEEK 4" in text and "Checks: all rules OK" in text
    assert "Part 1 (already made)" in text


def test_planner_takes_the_next_batch_part(bstore, settings, monkeypatch):
    from glivarao.studio import launch_plan, planner

    monkeypatch.setattr(launch_plan, "verify_fact_list", lambda facts, session=None: (facts, []))
    item = planner.plan_next(settings, bstore, date(2026, 11, 23), send=False)
    assert item.card["batch"]["entry"] == "aca-dec-15:p1" and item.format == "explainer"
    assert item.card["launch_facts"][0]["text"].startswith("With income between 100% and 400%")   # lead fact first
    assert "PART 1 of 3" in item.card["angle"]
    assert batch.next_long(bstore)["id"] == "how-credit-scores-work:p1"


def test_part_and_shorts_angles(bstore):
    e = next(x for x in batch.plan(batch.BATCH1) if x["id"] == "aca-dec-15:p1")
    card = batch.card_for(bstore, e)
    angles = batch.short_angles(bstore, card)
    assert len(angles) == 2 and all(a.startswith("ONE single idea only") for a in angles)
    assert card["batch"]["series"] == "ACA 2027 Checklist"


def test_record_jobs_and_previous_part_matching(bstore, settings, tmp_path):
    e = next(x for x in batch.plan(batch.BATCH1) if x["id"] == "how-credit-scores-work:p1")
    card = batch.card_for(bstore, e)
    out = tmp_path / "out"
    (out / "j-long").mkdir(parents=True)
    (out / "j-long" / "variety.json").write_text(json.dumps({"fingerprint": {"opening": "Your score dropped?"}}))
    batch.record_jobs(bstore, card, [("j-long", "long", "pending_approval", "v", ""),
                                     ("j-s1", "short", "pending_approval", "v", ""),
                                     ("j-bad", "short", "rejected_compliance", None, "")], out)
    assert [j["job"] for j in batch.topic_jobs(bstore, "how-credit-scores-work")] == ["j-long", "j-s1"]
    e2 = next(x for x in batch.plan(batch.BATCH1) if x["id"] == "how-credit-scores-work:p2")
    assert '"Your score dropped?"' in batch.card_for(bstore, e2)["angle"]        # a different hook next time
    # card-debt Part 1 (made before the batch) is found by its launch-list title
    job = bstore.create("long", "How to get out of credit card debt (a plan that works)")
    assert job.id in [j["job"] for j in batch.topic_jobs(bstore, "get-out-of-card-debt")]


class FakeAnalytics:
    def __init__(self, data):
        self.data = data

    def reports(self):
        return self

    def query(self, metrics, filters, **k):
        vid = filters.split("==")[1]
        self._r = {"columnHeaders": [{"name": n} for n in metrics.split(",")],
                   "rows": [[self.data[vid].get(n, 0) for n in metrics.split(",")]]}
        return self

    def execute(self):
        return self._r


def test_report_ranks_names_winner_and_proposes_close_topics(bstore, settings):
    from glivarao.studio import series as S

    data, k = {}, 0
    for t in batch.BATCH1:
        for part in (1, 2):
            k += 1
            jid = f"{t.slug}-l{part}"
            bstore.kv_set("x", "1")
            st = json.loads(bstore.kv_get("batch_state", "{}"))
            st.setdefault("jobs", {}).setdefault(t.slug, []).append({"job": jid, "format": "long", "part": part})
            st["jobs"][t.slug].append({"job": jid + "s", "format": "short", "part": part})
            bstore.kv_set("batch_state", json.dumps(st))
            vid, svid = f"{k:011d}", f"s{k:010d}"
            S.record_episode(bstore, jid, "x", "", "t", "long", date(2026, 11, 25))
            S.set_link(bstore, jid, f"https://www.youtube.com/watch?v={vid}")
            S.record_episode(bstore, jid + "s", "x", "", "t", "short", date(2026, 11, 25))
            S.set_link(bstore, jid + "s", f"https://youtube.com/shorts/{svid}")
            win = t.slug == "get-out-of-card-debt"
            data[vid] = {"views": 900 if win else 300, "averageViewPercentage": 55 if win else 40,
                         "subscribersGained": 12 if win else 3, "videoThumbnailImpressions": 10000,
                         "videoThumbnailImpressionsClickRate": 7.5 if win else 4.0}
            data[svid] = {"views": 2000 if win else 800, "subscribersGained": 9 if win else 2}
    metrics = batch.fetch_metrics(settings, bstore, FakeAnalytics(data))
    ranking = batch.rank(bstore, metrics)
    w = ranking[0]
    assert w["topic"] == "get-out-of-card-debt" and w["views"] == 2 * 900 + 2 * 2000 and w["subs"] == 42
    assert w["ctr"] == pytest.approx(7.5) and w["avp"] == pytest.approx(55)
    props = batch.propose_next(bstore, w["topic"])
    assert len(props) == 5 and all(v.slug not in {t.slug for t in batch.BATCH1} for v in props)
    assert props[0].slug == "snowball-vs-avalanche"                       # closest to card debt first
    assert all(batch.ready(v) for v in props)                            # 3 different official lead facts each

    sent = []

    class C:
        def call(self, method, **kw):
            sent.append((method, kw))
            return {}
    r = batch.send_report(settings, bstore, C(), metrics=metrics)
    text = sent[0][1]["text"]
    assert "Winner: How to get out of credit card debt" in text and "Proposed next 5" in text
    assert "Buy Now, Pay Later" in text and "needs 1 more official fact" in text
    pv = sent[0][1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split(":", 1)[1]
    assert batch.approve_next(bstore, "old") is None
    got = batch.approve_next(bstore, pv)
    assert got == r["proposals"] or set(got) == set(r["proposals"])
    assert {t.slug for t in batch.topics(bstore)} == set(got) and batch.next_long(bstore)["part"] == 1
    assert batch.plan_issues(batch.topics(bstore), batch.plan(batch.topics(bstore))) == []


def test_report_waits_for_the_batch_to_finish(bstore):
    assert not batch.due_for_report(bstore, date(2027, 1, 30))            # parts still unplanned
    for e in batch.plan(batch.BATCH1):
        batch.mark_planned(bstore, e["id"])
    assert not batch.due_for_report(bstore, date(2026, 12, 25))
    assert batch.due_for_report(bstore, date(2026, 12, 28))


def test_series_mode_is_replaced(bstore):
    from glivarao.daily_v2 import _series_name
    from types import SimpleNamespace

    b = SimpleNamespace(topic_key="credit_card")
    assert _series_name(bstore, {"card": {"batch": {"series": "Card Debt Escape"}}}, b, date(2026, 11, 25)) == \
        "Card Debt Escape"
    assert _series_name(bstore, {"card": {}}, b, date(2026, 11, 25)) is None
    bstore.kv_set("batch_mode", "off")
    assert _series_name(bstore, {"card": {}}, b, date(2026, 11, 25)) == "Money Traps"


def test_video_id_from_links():
    assert batch.video_id("https://www.youtube.com/watch?v=abcdefghijk") == "abcdefghijk"
    assert batch.video_id("https://youtu.be/abcdefghijk") == "abcdefghijk"
    assert batch.video_id("https://youtube.com/shorts/abcdefghijk") == "abcdefghijk"


def test_batch_day_makes_the_part_and_its_single_idea_shorts(world, monkeypatch):  # noqa: F811
    """A batch long day (simulated Claude, voice and render): ACA Part 1 + its 2 single-idea Shorts, recorded for
    the report; the 3rd daily Short slot goes to research (none today here)."""
    from glivarao import daily_v2
    from glivarao.studio import launch_plan

    s, store, calls = world
    store.kv_set("batch_mode", "on")
    monkeypatch.setattr(launch_plan, "verify_fact_list", lambda facts, session=None: (facts, []))
    monkeypatch.setattr("glivarao.research.run.run_research", lambda *a, **k: {"ranked": []})
    r = daily_v2.run_daily_v2(s, store, today=date(2026, 11, 23), send=False, shorts=3, ignore_input_wait=True)
    made = [j for j in r.jobs if j[2] == "rendered"]
    assert [j[1] for j in made].count("long") == 1 and [j[1] for j in made].count("short") == 2, r.jobs
    recorded = batch.topic_jobs(store, "aca-dec-15")
    assert {j["format"] for j in recorded} == {"long", "short"} and len(recorded) == 3
    meta = json.loads((s.output_dir / made[0][0] / "metadata.json").read_text())
    assert meta["series"] == "ACA 2027 Checklist"
    assert "no Shorts topic" in r.note                                    # the research fill-in ran


def test_manual_videos_count_and_free_their_slot(bstore, settings, capsys, monkeypatch):
    """Nov 23 by hand (make-now): credit scores Part 1 + Shorts for the Fed and houses. Part 1 is never made
    again, the next part takes its slot, the Shorts count for their topics; snowball isn't in batch 1."""
    from glivarao import __main__ as cli

    long_ = bstore.create("long", "How credit scores really work")
    fed, houses, snow = (bstore.create("short", t) for t in ("How the Fed affects your money",
                                                            "Why houses got so expensive", "Debt snowball"))
    before = batch.plan(batch.topics(bstore))
    assert any(e["id"] == "how-credit-scores-work:p1" for e in before)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    cli.main(["batch-mark-done", "how-credit-scores-work", "1", long_.id])
    cli.main(["batch-mark-done", "how-the-fed-affects-you", "short", fed.id])
    cli.main(["batch-mark-done", "why-houses-expensive", "short", houses.id])
    out = capsys.readouterr().out
    assert "won't be made again" in out and out.count("counted as") == 3
    with pytest.raises(SystemExit, match="not in the current batch"):
        cli.main(["batch-mark-done", "snowball-vs-avalanche", "short", snow.id])
    with pytest.raises(SystemExit, match="is a short video"):
        cli.main(["batch-mark-done", "how-credit-scores-work", "2", fed.id])

    after = batch.plan(batch.topics(bstore))
    assert not any(e["id"] == "how-credit-scores-work:p1" for e in after)
    assert len(after) == len(before) - 1 and batch.plan_issues(batch.topics(bstore), after) == []
    assert after[1]["publish"] == "2026-11-27"                         # the freed slot is used, nothing left empty
    assert batch.next_long(bstore)["id"] != "how-credit-scores-work:p1"
    jobs = {j["job"] for j in batch.topic_jobs(bstore, "how-the-fed-affects-you")}
    assert fed.id in jobs
    scores = [j for j in batch.topic_jobs(bstore, "how-credit-scores-work") if j["job"] == long_.id]
    assert scores and scores[0]["part"] == 1
    text = batch.plan_text(bstore)
    assert f"Part 1 (already made, {long_.id})" in text and f"Short {fed.id} (made by you)" in text
    assert "Checks: all rules OK" in text


def test_batch_make_makes_exactly_that_part_and_counts_it(world, monkeypatch):  # noqa: F811
    from glivarao import daily_v2
    from glivarao.studio import launch_plan

    s, store, calls = world
    store.kv_set("batch_mode", "on")
    monkeypatch.setattr(launch_plan, "verify_fact_list", lambda facts, session=None: (facts, []))
    r = daily_v2.batch_make(s, store, "aca-dec-15", 1, send=False, with_shorts=True)
    made = [j for j in r.jobs if j[2] == "rendered"]
    assert [j[1] for j in made].count("long") == 1 and [j[1] for j in made].count("short") == 2, r.jobs
    brief = json.loads((s.output_dir / made[0][0] / "brief.json").read_text())
    assert "100% and 400%" in brief["facts"][0]["text"]                 # Part 1's lead fact = hook + thumbnail
    meta = json.loads((s.output_dir / made[0][0] / "metadata.json").read_text())
    assert meta["series"] == "ACA 2027 Checklist"
    assert {j["job"] for j in batch.topic_jobs(store, "aca-dec-15")} >= {j[0] for j in made}
    assert batch.next_long(store)["id"] != "aca-dec-15:p1"                # counted: never made again
    with pytest.raises(ValueError, match="already planned"):
        daily_v2.batch_make(s, store, "aca-dec-15", 1, send=False)
    with pytest.raises(ValueError, match="not in the current batch"):
        daily_v2.batch_make(s, store, "snowball-vs-avalanche", 1, send=False)
