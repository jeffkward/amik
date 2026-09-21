"""Every closed card owes a merge now, so landing has to be one gesture.

`amik_finalise` has always reported cards owed a merge; it reported two.
Under every-card-branches it reports all of them, and a queue growing
faster than a person clears it by hand is the new friction this must not
create.
"""

import json
import os
import subprocess

import pytest

from amik import loop
from amik.core import git


def _rows(root):
    return {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(root, "amik", "board.jsonl"))
            if l.strip()}


@pytest.fixture()
def landing(instance):
    """Two done cards, each with a branch carrying one commit."""
    from conftest import write_board
    root = str(instance)
    write_board(root, [
        {"id": "one", "title": "One", "status": "done", "planning": None,
         "rank": 1, "created_at": "2026-01-01T00:00:00",
         "updated_at": "2026-01-01T00:00:00", "branch": "card/one"},
        {"id": "two", "title": "Two", "status": "done", "planning": None,
         "rank": 2, "created_at": "2026-01-01T00:00:00",
         "updated_at": "2026-01-01T00:00:00", "branch": "card/two"}])
    with open(os.path.join(root, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\ntrunk = "main"\n')
    subprocess.run(["git", "init", "-q", "-b", "main", root], check=True)
    for a in (["config", "user.email", "t@t"], ["config", "user.name", "t"],
              ["add", "-A"], ["commit", "-qm", "first"]):
        subprocess.run(["git", "-C", root, *a], check=True)
    for cid in ("one", "two"):
        git.start(root, cid, "main", [])
        with open(os.path.join(root, cid + ".py"), "w") as f:
            f.write("x = 1\n")
        subprocess.run(["git", "-C", root, "add", "-A"], check=True)
        subprocess.run(["git", "-C", root, "commit", "-qm", cid], check=True)
        git.finish(root, "main", [])
    return root


def _verify(root, command):
    with open(os.path.join(root, "amik", "amik.toml"), "w") as f:
        f.write('verify = "{}"\ntrunk = "main"\n'.format(command))


def test_it_merges_every_clean_card(landing):
    res = loop.land(landing)
    assert res["ok"], res
    assert sorted(res["data"]["landed"]) == ["one", "two"]
    for cid in ("one", "two"):
        assert os.path.exists(os.path.join(landing, cid + ".py"))


def test_a_landed_card_loses_its_branch_and_its_field(landing):
    loop.land(landing)
    for cid in ("one", "two"):
        assert not git.branch_exists(landing, "card/" + cid)
        assert not _rows(landing)[cid].get("branch")


def test_it_sweeps_the_prototype(landing):
    d = os.path.join(landing, "amik", "prototypes", "one")
    os.makedirs(d)
    with open(os.path.join(d, "index.html"), "w") as f:
        f.write("<p>x</p>")
    loop.land(landing)
    assert not os.path.exists(d)


def test_a_settled_trunk_SKIPS_the_second_verify(landing):
    """The card's own agent already ran the suite on this branch, and
    if the trunk has not moved since the branch was cut the merged tree
    is byte-identical to the one it verified. Running it again is the
    same files answering the same question, at three minutes a card.

    `one` is cut from an unmoved trunk, so it is settled.
    """
    marker = os.path.join(landing, "verify-ran")
    _verify(landing, "touch " + marker)
    res = loop.land(landing)
    assert "one" in res["data"]["landed"]
    assert "one" not in res["data"]["verified"]


def test_a_MOVED_trunk_re_runs_it(landing):
    """The case the second run exists for: two cards can each be green
    alone and broken together, one renaming what the other calls.

    `two` is cut from the same commit `one` was, so landing `one` moves
    the trunk out from under it -- which is exactly the shape that
    becomes common the day cards run in parallel.
    """
    res = loop.land(landing)
    assert "two" in res["data"]["verified"]


def test_a_failed_verify_UNWINDS_that_merge_and_keeps_going(landing):
    """One bad card must not strand the rest, and must not be left
    half-merged either.

    `two` is the one checked here: `one` lands settled and unverified,
    which moves the trunk and puts `two` on the re-verifying path.
    """
    _verify(landing, "test ! -f two.py")      # red once `two` is merged
    res = loop.land(landing)
    assert "one" in res["data"]["landed"]
    assert "two" in res["data"]["refused"]
    assert not os.path.exists(os.path.join(landing, "two.py"))
    assert git.branch_exists(landing, "card/two"), "its branch must survive"


def test_it_never_leaves_MERGE_HEAD_behind(landing):
    """A half-open merge in a shared checkout means anything else that
    commits adopts it under its own message. This repo has paid once."""
    _verify(landing, "false")   # reached by `two`, once `one` has moved the trunk
    loop.land(landing)
    head = os.path.join(landing, ".git", "MERGE_HEAD")
    assert not os.path.exists(head)


def test_it_refuses_while_an_agent_holds_the_lock(landing):
    """Merging under a running agent is the same fault arrived at from
    the other side."""
    with loop.Lock(landing, "one"):
        res = loop.land(landing)
    assert res["ok"] is False
    assert "being worked" in res["reason"]


def test_nothing_owed_is_an_answer_not_a_fault(landing):
    loop.land(landing)
    again = loop.land(landing)
    assert again["ok"] and again["data"]["landed"] == []


# ── the loop lands before it works ──────────────────────────────────

def test_a_tick_lands_what_is_owed_before_taking_a_card(landing):
    """Moving a card to Done is the whole gesture. The finalisation
    belongs to the destination rather than to whoever remembered to run
    a command afterwards -- and that write rings the doorbell anyway,
    so the loop is already awake. It would be strange to wake up, see a
    merge owed, and go looking for something else to do.
    """
    import unittest.mock as mock
    from conftest import write_board
    with open(os.path.join(landing, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\ntrunk = "main"\narmed = true\n'
                '[agent]\ncommand = "the-agent"\n')
    with mock.patch.object(loop, "run_agent") as agent:
        agent.return_value = subprocess.CompletedProcess([], 0, "", "")
        res = loop.work_once(landing)
    assert sorted(res["landed"]["landed"]) == ["one", "two"]
    assert not git.branch_exists(landing, "card/one")


def test_a_refused_landing_does_NOT_stop_the_tick(landing, monkeypatch):
    """Landing and working are different jobs. A branch that will not
    merge is a thing to report, not a reason to stop taking cards."""
    monkeypatch.setattr(loop, "land",
                        lambda *a, **k: {"ok": False, "reason": "nope"})
    with open(os.path.join(landing, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\ntrunk = "main"\narmed = true\n'
                '[agent]\ncommand = "the-agent"\n')
    res = loop.work_once(landing)
    assert res["landed"] == {"refused": "nope"}
    # Nothing in Ready here, so the tick reaches its own answer rather
    # than dying on the landing.
    assert "nothing in Ready" in res["why"]


def test_a_dry_run_lands_NOTHING(landing):
    """A dry run reports; it does not change the repository. Merging
    during one would be the single most surprising thing it could do."""
    with open(os.path.join(landing, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\ntrunk = "main"\narmed = true\n'
                '[agent]\ncommand = "the-agent"\n')
    loop.work_once(landing, dry_run=True)
    assert git.branch_exists(landing, "card/one")
