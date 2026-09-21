"""The loop puts the tree where the card belongs, and puts it back.

The fault this closes: `loop.py` contained no git at all, so each agent
placed the tree correctly for its own card and nobody put it back. The
next card -- which had asked for nothing -- was worked on the previous
card's branch, and 34 commits ended up off the trunk.

Branch placement is a property of the transition BETWEEN cards, and the
loop is the only thing that sees two.
"""

import json
import os
import subprocess

import pytest

from amik import loop
from amik.core import board

ROWS = [{"id": "a-card", "title": "A card", "status": "ready",
         "planning": None, "rank": 1, "created_at": "2026-01-01T00:00:00",
         "updated_at": "2026-01-01T00:00:00"}]


@pytest.fixture()
def repo(instance):
    """An armed instance that is also a real git repository."""
    from conftest import write_board
    root = str(instance)
    write_board(root, ROWS)
    with open(os.path.join(root, "LAWS.md"), "w") as f:
        f.write("# Laws\n")
    with open(os.path.join(root, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\nlaws = "LAWS.md"\narmed = true\n'
                'trunk = "main"\n[agent]\ncommand = "the-agent"\n'
                '[state]\nshared = ["amik/board.jsonl"]\n')
    subprocess.run(["git", "init", "-q", "-b", "main", root], check=True)
    subprocess.run(["git", "-C", root, "config", "user.email", "t@t"],
                   check=True)
    subprocess.run(["git", "-C", root, "config", "user.name", "t"],
                   check=True)
    subprocess.run(["git", "-C", root, "add", "-A"], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "first"], check=True)
    return root


def _branch(root):
    return subprocess.run(["git", "-C", root, "rev-parse", "--abbrev-ref",
                           "HEAD"], capture_output=True, text=True).stdout.strip()


def _tick(root, during=lambda root: None, returncode=0):
    """One tick with the AGENT replaced by a callable that runs while
    the tree is wherever the loop put it.

    `run_agent` is patched rather than `subprocess.run`, and the
    difference matters: `loop.subprocess` IS the subprocess module, so
    patching its `run` patches it for `core/git.py` as well -- which
    silently disables the very placement these tests exist to check,
    and leaves them all passing for the wrong reason.
    """
    import unittest.mock as mock
    seen = {}

    def fake_agent(*a, **kw):
        seen["branch"] = _branch(root)
        during(root)
        return subprocess.CompletedProcess(["the-agent"], returncode, "", "")

    with mock.patch.object(loop, "run_agent", side_effect=fake_agent):
        res = loop.work_once(root)
    return res, seen


def _close(status, outcome="Built it."):
    def during(root):
        from amik.core import edit
        if outcome:
            edit.record_outcome(root, "a-card", outcome, model="test")
        edit.move(root, "a-card", status, 0)
    return during


# ── placement ───────────────────────────────────────────────────────

def test_the_agent_runs_on_the_cards_branch(repo):
    _, seen = _tick(repo, _close("done"))
    assert seen["branch"] == "card/a-card"


def test_the_tree_returns_to_the_trunk_after_a_clean_card(repo):
    _tick(repo, _close("done"))
    assert _branch(repo) == "main"


def test_the_tree_STAYS_on_the_branch_after_a_halted_card(repo):
    """A halted card is waiting to be looked at, and the thing worth
    looking at is on its branch. The board's top bar names it."""
    _tick(repo, _close("review"))
    assert _branch(repo) == "card/a-card"


def test_the_cards_close_reaches_the_TRUNKS_board(repo):
    """The live-lock. A close committed on the branch is invisible once
    the tree returns, and the loop re-picks the card it just finished --
    and every other test here passes while that is broken."""
    _tick(repo, _close("done"))
    rows = [json.loads(l) for l
            in open(os.path.join(repo, "amik", "board.jsonl")) if l.strip()]
    assert rows[0]["status"] == "done"
    assert _branch(repo) == "main"


def test_placement_happens_BEFORE_the_card_moves_to_doing(repo):
    """Order is load-bearing: the move writes board.jsonl, and placing
    after it would make the tree dirty by Amik's own hand."""
    import inspect
    src = inspect.getsource(loop.work_once)
    assert src.index("git.start") < src.index('"doing"')


# ── refusals ────────────────────────────────────────────────────────

def test_a_refused_placement_halts_the_card_carrying_gits_words(repo,
                                                                monkeypatch):
    """Not just that it halted -- WHY, ON THE CARD.

    The reason used to go only into work_once's return value, where
    launchd's log is the only reader. A card halted at placement said
    nothing at all, and this test passed anyway because it was reading
    the return value too. It reads the card now.
    """
    monkeypatch.setattr(loop.git, "start",
                        lambda *a, **k: {"ok": False,
                                         "reason": "would be overwritten"})
    res, _ = _tick(repo)
    assert res["did"] is None
    rows = [json.loads(l) for l
            in open(os.path.join(repo, "amik", "board.jsonl")) if l.strip()]
    assert rows[0]["status"] == "review" and rows[0]["halt"] is True
    prose = open(os.path.join(repo, "amik", "cards", "a-card.md")).read()
    assert "would be overwritten" in prose, prose
    assert "could not be placed" in prose


def test_a_refused_placement_does_not_spawn_the_agent(repo, monkeypatch):
    monkeypatch.setattr(loop.git, "start",
                        lambda *a, **k: {"ok": False, "reason": "nope"})
    _, seen = _tick(repo)
    assert "branch" not in seen, "the agent ran anyway"


def test_an_instance_that_is_not_a_repository_STILL_WORKS_CARDS(instance):
    """Amik does not require git. A project without it loses branch
    placement and keeps its board -- refusing the card instead would
    make Amik a tool for git repositories only, which is the opposite
    of what every declared key is for."""
    from conftest import write_board
    root = str(instance)
    write_board(root, ROWS)
    with open(os.path.join(root, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\narmed = true\n'
                '[agent]\ncommand = "the-agent"\n')
    res, _ = _tick(root, _close("done"))
    assert res["did"] == "a-card", res

