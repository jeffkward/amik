"""Who the log says did it, from each of the three callers.

The door takes the actor; these are the callers that have to pass one.
Getting this wrong is worse than not logging at all -- a history that
attributes the owner's drag to the loop is a history that will be
believed.
"""

import inspect
import json
import os

import pytest

from amik.core import edit, log

ROW = {"id": "a-card", "title": "A card", "status": "review",
       "planning": None, "rank": 1, "created_at": "2026-01-01T00:00:00",
       "updated_at": "2026-01-01T00:00:00"}


@pytest.fixture()
def board(instance):
    from conftest import write_board
    root = write_board(instance, [dict(ROW)])
    with open(os.path.join(root, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\ntrunk = "main"\narmed = true\n'
                '[agent]\ncommand = "an-agent --flag"\n')
    return root


# ── the web says "user" ─────────────────────────────────────────────

def test_a_drag_is_attributed_to_the_owner(board, client):
    # `/position`, not `/move`: position is a nested RESOURCE here, and
    # the drag is a PATCH on it. Status and rank belong to the drag and
    # to nothing else, which is why they are not fields on the card.
    client.patch("/amik/cards/a-card/position",
                 data={"to_status": "done", "to_index": "0"})
    entry = log.read(board)[-1]
    assert entry["event"] == "move"
    assert entry["by"] == "user"


def test_a_card_created_in_the_page_is_the_owners(board, client):
    client.post("/amik/cards", data={"title": "A new case"})
    entry = log.read(board)[-1]
    assert entry["event"] == "create"
    assert entry["by"] == "user"


# ── the loop says "amik", and names what it started ─────────────────

def test_the_loop_attributes_its_own_work_to_amik(board):
    """By reading what a tick WROTE. Grepping `work_once` for the string
    `by="amik"` would pass on a call that never ran."""
    import unittest.mock as mock
    import subprocess as sp
    from amik import loop
    from conftest import write_board
    write_board(board, [dict(ROW, status="ready", model="a-model")])
    with mock.patch.object(loop, "run_agent") as agent:
        agent.return_value = sp.CompletedProcess(["x"], 0, "", "")
        loop.work_once(board)
    events = {e["event"]: e for e in log.read(board)}
    assert events["move"]["by"] == "amik"
    assert events["move"]["to"] == "doing"


def test_the_work_it_starts_names_the_model_and_the_agent(board):
    """A board that allows more than one agent has to say which one took
    the card, and the row carries no room for either."""
    import unittest.mock as mock
    import subprocess as sp
    from amik import loop
    from conftest import write_board
    write_board(board, [dict(ROW, status="ready", model="a-model")])
    with mock.patch.object(loop, "run_agent") as agent:
        agent.return_value = sp.CompletedProcess(["x"], 0, "", "")
        loop.work_once(board)
    work = next(e for e in log.read(board) if e["event"] == "work")
    assert work["model"] == "a-model"
    assert work["agent"] == "an-agent"


def test_the_agent_is_named_by_its_PROGRAM_not_its_whole_command():
    """`claude -p --output-format stream-json --verbose --setting-sources
    project --allowedTools ...` on every card is a line nobody reads."""
    assert log.program("an-agent --flag --and-another") == "an-agent"
    assert log.program("") == ""


# ── the agent says "agent", through the environment ─────────────────

def test_the_loop_hands_the_agent_its_name(board):
    """A fresh process per card, so a variable works here where it
    would race the server. The card cannot rewrite it.

    Read off the SPAWN rather than out of the source: a variable named
    in the code and not passed to the child is the failure this is
    about."""
    import unittest.mock as mock
    import subprocess as sp
    from amik import loop
    from amik.core import board as readers
    project = readers.amik_project(board)["data"]
    card = {"id": "a-card", "title": "A card"}
    with mock.patch.object(loop.subprocess, "run") as run:
        run.return_value = sp.CompletedProcess(["x"], 0, "", "")
        loop.run_agent(board, card, project)
    assert run.call_args.kwargs["env"]["AMIK_ACTOR"] == "agent"


def test_the_environment_names_the_agent(board, monkeypatch):
    monkeypatch.setenv("AMIK_ACTOR", "agent")
    edit.record_outcome(board, "a-card", "Built it.", model="Opus 5")
    entry = log.read(board)[-1]
    assert entry["by"] == "agent"
    assert entry["model"] == "Opus 5"


# ── try again ───────────────────────────────────────────────────────

def test_TRY_AGAIN_is_part_of_the_cards_history(board):
    """His ask. Throwing away a build and going again is the one
    verdict with no column to drag to, so without this the history
    shows a card in Review and then in Ready with nothing between."""
    edit.discard(board, "a-card", "main", feedback="Try the other parser.")
    events = [e["event"] for e in log.read(board)]
    assert "discard" in events
    entry = next(e for e in log.read(board) if e["event"] == "discard")
    assert entry["card"] == "a-card"


def test_a_discard_records_that_feedback_was_given(board):
    """Not the feedback itself -- that is on the card, where the next
    agent reads it. Only that there was some, so a history shows a
    retry with guidance differently from one without."""
    edit.discard(board, "a-card", "main", feedback="Try the other parser.")
    entry = next(e for e in log.read(board) if e["event"] == "discard")
    assert entry["feedback"] is True


def test_a_discard_with_no_feedback_says_so_by_omission(board):
    edit.discard(board, "a-card", "main")
    entry = next(e for e in log.read(board) if e["event"] == "discard")
    assert "feedback" not in entry


# ── reading it from the command line ────────────────────────────────

def test_amik_log_is_a_command(board, capsys):
    from amik.__main__ import main
    edit.move(board, "a-card", "done", 0, by="user")
    assert main(["--root", board, "log"]) == 0
    out = capsys.readouterr().out
    assert "a-card" in out
    assert "review" in out and "done" in out


def test_the_command_can_be_asked_for_one_card(board, capsys):
    from amik.__main__ import main
    edit.move(board, "a-card", "done", 0, by="user")
    edit.create(board, "Another", by="user")
    main(["--root", board, "log", "--card", "a-card"])
    out = capsys.readouterr().out
    assert "a-card" in out
    assert "Another" not in out


def test_the_command_says_so_when_there_is_no_history(instance, capsys):
    from amik.__main__ import main
    assert main(["--root", instance, "log"]) == 0
    assert "no history" in capsys.readouterr().out.lower()
