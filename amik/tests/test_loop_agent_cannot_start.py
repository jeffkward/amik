"""The agent could not be STARTED — not failed, never ran.

The fault this closes: `com.amik.board` ran under launchd with a
four-directory PATH, `claude` was not on it, and `run_agent` raised the
ValueError its own comment promised. `work_once` caught it as an
ordinary refusal — the same shape as "not armed" — after it had already
moved the card to `doing` and checked out its branch. The card stayed
there, the tree stayed there, nothing was written on the card and
nothing reached the log. The next tick took the next card and did it
again: three cards in `doing` in twenty seconds, no agent ever run.

"Command not found is the FIRST thing an unattended run meets" was
already written in `run_agent`. This is the half of that sentence the
caller owed.
"""
import os
import subprocess

import pytest

from amik import loop
from amik.core import board
from test_loop import _toml, ready  # noqa: F401  (fixture)
from test_loop_places_the_tree import repo, _branch  # noqa: F401

MISSING = "no-such-agent-xyz"


def _row(root, card_id):
    return next(c for col in board.amik(root)["data"]["columns"]
                for c in col["cards"] if c["id"] == card_id)


def _outcome(root, card_id):
    path = os.path.join(root, "amik", "cards", card_id + ".md")
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_a_card_whose_agent_cannot_start_halts_in_review(ready):
    """The same halt a failed verify sets and an owner sets by hand.
    `doing` is invisible to the queue, so a card left there has silently
    stopped being work — and `ready` would be taken again next tick and
    fail the same way, forever."""
    _toml(ready, armed=True, agent=MISSING)
    res = loop.work_once(ready)
    row = _row(ready, "a-card")
    assert row["status"] == "review"
    assert row["halt"] is True
    assert res["did"] is None
    assert MISSING in res["why"]


def test_the_error_is_written_on_the_card(ready):
    """Where the owner reads. A return value under launchd has one
    reader, and it is a log file nobody opens until something is
    already wrong."""
    _toml(ready, armed=True, agent=MISSING)
    loop.work_once(ready)
    text = _outcome(ready, "a-card")
    assert "## Outcome" in text
    assert MISSING in text
    assert "not worked" in text


def test_a_refusal_to_start_is_a_fault_the_ticker_reports(ready, capsys):
    """"Not armed" is an answer and stays quiet. "Cannot run the agent"
    is a fault: the board is armed, a card was owed work, and the loop
    could not do its one job. Surviving that quietly is the failure the
    ticker's own test says it must not have."""
    _toml(ready, armed=True, agent=MISSING)
    loop.tick_forever(ready, sleep=0, rounds=1)
    assert MISSING in capsys.readouterr().err


def test_the_next_card_is_not_taken_after_one_cannot_start(ready):
    """One halted card in review pauses what is ranked below it. That is
    the queue's own law doing the work: the loop must not strand a
    second card on the same missing command."""
    from conftest import write_board
    rows = [dict(r) for r in loop_rows()]
    write_board(ready, rows)
    _toml(ready, armed=True, agent=MISSING)
    loop.work(ready)
    loop.work(ready)
    assert _row(ready, "a-card")["status"] == "review"
    assert _row(ready, "b-card")["status"] == "ready"


def loop_rows():
    from test_loop import ROWS
    second = dict(ROWS[0], id="b-card", title="B card", rank=2)
    return [ROWS[0], second]


def test_the_tree_comes_home_when_the_agent_cannot_start(repo):
    """Nothing was built, so there is nothing on the branch worth
    parking the tree on. A checkout left on an empty card branch is
    the owner's `main` quietly not being `main`."""
    import unittest.mock as mock
    with mock.patch.object(loop, "run_agent",
                           side_effect=ValueError(
                               "cannot run the agent command "
                               "'the-agent': No such file")):
        loop.work_once(repo)
    assert _branch(repo) == "main"
    assert _row(repo, "a-card")["status"] == "review"
    assert not os.path.exists(os.path.join(repo, "amik", ".lock"))
