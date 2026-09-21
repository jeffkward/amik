"""The write doors, reachable from a command line.

The fault this closes, found on a Bun project: the laws tell an agent
that `amik.core.edit` is the only writer and it may never touch the
board by hand. That module is importable in Amik's own repository,
because the package is sitting in the working directory -- and nowhere
else. A card dragged to Ready on a host project was picked up, worked
by an agent that could not reach the door it was ordered to use, and
left in `doing` with no outcome and no complaint. It did the only
lawful thing available, which was nothing.

So the doors get a surface every agent can reach whatever the host is
written in. Same functions, same refusals, same log lines -- the CLI is
a mouth on the existing door, never a second writer.

Only the verbs a card needs while being worked. `create` and `delete`
are the owner's, and an agent that could delete a card is an agent one
bad turn away from deleting the board.
"""

import json
import os

import pytest

from amik.__main__ import main
from amik.core import board, log

ROW = {"id": "a-card", "title": "A card", "status": "ready",
       "planning": None, "rank": 1, "created_at": "2026-01-01T00:00:00",
       "updated_at": "2026-01-01T00:00:00"}


@pytest.fixture()
def desk(instance):
    from conftest import write_board
    root = write_board(instance, [dict(ROW)])
    with open(os.path.join(root, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\narmed = true\n'
                '[agent]\ncommand = "an-agent"\n')
    return root


def _row(root, cid="a-card"):
    return next(c for col in board.amik(root)["data"]["columns"]
                for c in col["cards"] if c["id"] == cid)


def _prose(root, cid="a-card"):
    with open(os.path.join(root, "amik", "cards", cid + ".md"),
              encoding="utf-8") as f:
        return f.read()


# ── move ────────────────────────────────────────────────────────────

def test_move_changes_the_column(desk):
    assert main(["--root", desk, "move", "a-card", "doing"]) == 0
    assert _row(desk)["status"] == "doing"


def test_move_refuses_a_status_that_is_not_a_column(desk):
    """The door refuses it; this proves the refusal survives the trip
    through argv rather than becoming a traceback."""
    assert main(["--root", desk, "move", "a-card", "nowhere"]) == 1
    assert _row(desk)["status"] == "ready"


def test_move_refuses_a_card_that_is_not_there(desk):
    assert main(["--root", desk, "move", "no-such-card", "doing"]) == 1


def test_move_lands_where_it_is_told(desk):
    from conftest import write_board
    write_board(desk, [dict(ROW), dict(ROW, id="b-card", rank=2)])
    main(["--root", desk, "move", "b-card", "ready", "--index", "0"])
    ready = [c["id"] for col in board.amik(desk)["data"]["columns"]
             if col["status"] == "ready" for c in col["cards"]]
    assert ready == ["b-card", "a-card"]


# ── outcome ─────────────────────────────────────────────────────────

def test_outcome_writes_under_the_heading(desk):
    assert main(["--root", desk, "outcome", "a-card", "Built it."]) == 0
    assert "## Outcome" in _prose(desk)
    assert "Built it." in _prose(desk)


def test_outcome_carries_the_model_when_told(desk):
    """The model is knowable only to the agent, so it is passed. Omitted
    it writes "model unrecorded", which is visible on purpose."""
    main(["--root", desk, "outcome", "a-card", "Built it.",
          "--model", "Opus 5"])
    assert "Opus 5" in _prose(desk)


def test_outcome_APPENDS_rather_than_replacing(desk):
    main(["--root", desk, "outcome", "a-card", "First attempt."])
    main(["--root", desk, "outcome", "a-card", "Second attempt."])
    assert "First attempt." in _prose(desk)
    assert "Second attempt." in _prose(desk)


def test_an_empty_outcome_is_refused(desk):
    assert main(["--root", desk, "outcome", "a-card", "   "]) == 1


# ── ask ─────────────────────────────────────────────────────────────

def test_ask_raises_a_question(desk):
    assert main(["--root", desk, "ask", "a-card", "Which parser?"]) == 0
    assert "### Which parser?" in _prose(desk)


def test_ask_carries_context_as_a_blockquote(desk):
    """A leading blockquote is the ASKER's context. Written any other way
    it lands in the box the owner types into and marks the question
    answered."""
    main(["--root", desk, "ask", "a-card", "Which parser?",
          "--context", "Tried the fast one; it drops empty rows."])
    assert "> Tried the fast one" in _prose(desk)


def test_ask_refuses_a_duplicate_heading(desk):
    """The first occurrence wins on read, so an answer meant for the
    second would write into the first."""
    main(["--root", desk, "ask", "a-card", "Which parser?"])
    assert main(["--root", desk, "ask", "a-card", "Which parser?"]) == 1


# ── halt ────────────────────────────────────────────────────────────

def test_halt_sets_the_field(desk):
    assert main(["--root", desk, "halt", "a-card"]) == 0
    assert _row(desk)["halt"] is True


def test_halt_off_clears_it(desk):
    main(["--root", desk, "halt", "a-card"])
    assert main(["--root", desk, "halt", "a-card", "--off"]) == 0
    assert not _row(desk).get("halt")


# ── every one of them is the SAME door ──────────────────────────────

def test_the_cli_writes_through_the_door_and_is_logged_as_the_agent(desk,
                                                                    monkeypatch):
    """Not a second writer. The log is the proof: a move made here is
    indistinguishable from one the loop made, except in who did it."""
    monkeypatch.setenv("AMIK_ACTOR", "agent")
    main(["--root", desk, "move", "a-card", "doing"])
    entry = log.read(desk)[-1]
    assert entry["event"] == "move"
    assert entry["from"] == "ready" and entry["to"] == "doing"
    assert entry["by"] == "agent"


def test_a_refusal_prints_the_reason_rather_than_raising(desk, capsys):
    """An agent reads stdout. A traceback is a refusal it cannot act
    on."""
    main(["--root", desk, "move", "a-card", "nowhere"])
    said = capsys.readouterr().out
    assert "nowhere" in said or "status" in said


def test_the_write_verbs_are_reachable_without_importing_amik(desk):
    """The whole point. A host project is not a Python project, and the
    agent working a card in one has no amik on its path -- but it has
    the command, because the loop names it in the brief."""
    import inspect
    from amik.__main__ import main as m
    src = inspect.getsource(m)
    for verb in ("move", "outcome", "ask", "halt"):
        assert '"{}"'.format(verb) in src, verb


# ── what it deliberately does NOT offer ─────────────────────────────

def test_there_is_no_delete_verb(desk):
    """An agent that could delete a card is one bad turn from deleting
    the board. Deletion stays the owner's, in the page."""
    with pytest.raises(SystemExit):
        main(["--root", desk, "delete", "a-card"])


# ── plan: the way back in from a brainstorm ─────────────────────────
#
# `needs-brainstorm` blocks a card and the queue skips it saying why.
# Amik hosts no thinking -- that is deliberate -- so the owner leaves
# the board, decides somewhere else, and comes back. Until this verb
# there was no way back except the pencil in the page, which broke the
# loop at its last step for anyone working in a terminal.

def test_plan_names_a_document_and_climbs_the_rung(desk):
    from conftest import write_board
    write_board(desk, [dict(ROW, planning="needs-brainstorm")])
    assert main(["--root", desk, "plan", "a-card",
                 "--doc", "docs/the-plan.md"]) == 0
    row = _row(desk)
    assert row["planning"] == "has-plan"
    assert row["docs"] == ["docs/the-plan.md"]


def test_a_plan_with_no_document_is_a_CONTRADICTION_and_is_refused(desk):
    """`has-plan` claims a plan exists and `docs` is where it is named.
    A rung with nothing in that field prints "plan not named" on the
    card, so writing one deliberately would be filing the contradiction
    rather than resolving it."""
    assert main(["--root", desk, "plan", "a-card"]) == 1


def test_plan_takes_MORE_than_one_document(desk):
    main(["--root", desk, "plan", "a-card", "--doc", "docs/a.md",
          "--doc", "docs/b.md"])
    assert _row(desk)["docs"] == ["docs/a.md", "docs/b.md"]


def test_clear_drops_the_rung_when_no_plan_is_needed(desk):
    """"Thought about it, nothing to write down" is a real answer. The
    rung says what a card still OWES, and a card that owes nothing
    carries none."""
    from conftest import write_board
    write_board(desk, [dict(ROW, planning="needs-brainstorm")])
    assert main(["--root", desk, "plan", "a-card", "--clear"]) == 0
    assert _row(desk)["planning"] is None


def test_needs_brainstorm_can_be_SET_from_here_too(desk):
    """An agent that finds open design questions mid-card says so on the
    ladder rather than guessing an answer. Both rungs, one verb."""
    assert main(["--root", desk, "plan", "a-card", "--needs-brainstorm"]) == 0
    assert _row(desk)["planning"] == "needs-brainstorm"


def test_the_rung_and_the_clear_cannot_be_asked_for_at_once(desk):
    with pytest.raises(SystemExit):
        main(["--root", desk, "plan", "a-card", "--clear",
              "--needs-brainstorm"])


def test_a_planned_card_is_no_longer_skipped_by_the_queue(desk):
    """The whole point of the verb. Blocked before, takeable after."""
    from amik.core import board as readers
    from conftest import write_board
    write_board(desk, [dict(ROW, planning="needs-brainstorm")])
    assert readers.amik_queue(desk)["data"]["take"] is None
    main(["--root", desk, "plan", "a-card", "--doc", "docs/the-plan.md"])
    assert (readers.amik_queue(desk)["data"]["take"] or {})["id"] == "a-card"
