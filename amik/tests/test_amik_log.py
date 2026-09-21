"""The board's own history, written by the one door.

`board.jsonl` says where everything is. It cannot say how it got there:
a row carries one `updated_at` and forgets every move before the last.
So the same door that renumbers columns and stamps the times appends a
line saying what it just did.

Structural events only. A title edit fires on every save, and a log
recording them buries the four lines somebody wanted.
"""

import json
import os

import pytest

from amik.core import edit, log

ROW = {"id": "a-card", "title": "A card", "status": "ready",
       "planning": None, "rank": 1, "created_at": "2026-01-01T00:00:00",
       "updated_at": "2026-01-01T00:00:00"}


@pytest.fixture()
def board(instance):
    from conftest import write_board
    return write_board(instance, [dict(ROW)])


def _lines(root):
    return log.read(root)


def _events(root):
    return [e["event"] for e in _lines(root)]


# ── who did it ──────────────────────────────────────────────────────

def test_an_explicit_actor_wins(monkeypatch):
    monkeypatch.setenv("AMIK_ACTOR", "agent")
    assert log.actor("user") == "user"


def test_the_environment_is_the_AGENTS_way_in(monkeypatch):
    """The loop spawns the agent as its own process and hands it a
    variable no card can rewrite -- the same reasoning the outcome's
    attribution uses for the harness."""
    monkeypatch.setenv("AMIK_ACTOR", "agent")
    assert log.actor() == "agent"


def test_nobody_saying_is_written_as_unknown(monkeypatch):
    """Not guessed. A gap you can see is a gap somebody closes."""
    monkeypatch.delenv("AMIK_ACTOR", raising=False)
    assert log.actor() == "unknown"


# ── what gets written ───────────────────────────────────────────────

def test_a_move_records_both_ends(board):
    edit.move(board, "a-card", "doing", 0, by="amik")
    entry = _lines(board)[-1]
    assert entry["event"] == "move"
    assert entry["from"] == "ready"
    assert entry["to"] == "doing"
    assert entry["card"] == "a-card"
    assert entry["by"] == "amik"
    assert entry["at"]


def test_a_creation_says_where_it_landed(board):
    edit.create(board, "A new case", by="user")
    entry = _lines(board)[-1]
    assert entry["event"] == "create"
    assert entry["to"] == "inbox"
    assert entry["by"] == "user"


def test_questions_are_counted(board):
    edit.ask(board, "a-card", "Which parser?", by="agent")
    entry = _lines(board)[-1]
    assert entry["event"] == "ask"
    assert entry["count"] == 1
    assert entry["by"] == "agent"


def test_answers_are_counted_when_the_owner_saves_them(board):
    """His own example. Answering is the owner's gesture and the log
    should say how much of it landed."""
    edit.ask(board, "a-card", "Which parser?")
    edit.ask(board, "a-card", "Which encoding?")
    prose = open(os.path.join(board, "amik", "cards", "a-card.md")).read()
    answered = prose.replace("### Which parser?\n",
                             "### Which parser?\n\nThe fast one.\n")
    edit.update(board, "a-card", {"body": answered}, by="user")
    entry = _lines(board)[-1]
    assert entry["event"] == "answer"
    assert entry["count"] == 1
    assert entry["by"] == "user"


def test_the_TOGGLES_are_logged(board):
    """Metadata, unlike a title: a pause changes what the queue does."""
    edit.update(board, "a-card", {"halt": True}, by="user")
    entry = _lines(board)[-1]
    assert entry["event"] == "toggle"
    assert entry["field"] == "halt"
    assert entry["value"] is True


def test_the_prototype_toggle_is_logged_too(board):
    edit.update(board, "a-card", {"requires_prototype": True}, by="user")
    assert _lines(board)[-1]["field"] == "requires_prototype"


def test_a_toggle_that_did_not_change_is_not_logged(board):
    """A save is not an event. Setting halt to what it already was is
    the modal being closed, not a decision being made."""
    edit.update(board, "a-card", {"halt": False}, by="user")
    assert "toggle" not in _events(board)


def test_an_outcome_is_logged_with_its_model(board):
    """A board worked by more than one model has to say which wrote
    what, and the row carries no room for it."""
    edit.record_outcome(board, "a-card", "Built it.", model="Opus 5",
                        by="agent")
    entry = _lines(board)[-1]
    assert entry["event"] == "outcome"
    assert entry["model"] == "Opus 5"


def test_a_branch_is_logged_when_set_and_when_cleared(board):
    edit.set_branch(board, "a-card", "card/a-card", by="amik")
    assert _lines(board)[-1]["branch"] == "card/a-card"
    edit.set_branch(board, "a-card", "", by="amik")
    assert _lines(board)[-1]["event"] == "branch"
    assert "branch" not in _lines(board)[-1]


def test_a_deletion_is_logged(board):
    edit.delete(board, "a-card", by="user")
    assert _lines(board)[-1]["event"] == "delete"


# ── what does NOT get written ───────────────────────────────────────

def test_a_TITLE_edit_is_not_an_event(board):
    edit.update(board, "a-card", {"title": "Renamed"}, by="user")
    assert _events(board) == []


def test_a_BODY_edit_with_no_new_answer_is_not_an_event(board):
    edit.update(board, "a-card", {"body": "Some new prose.\n"}, by="user")
    assert _events(board) == []


# ── it is bookkeeping, never a gate ─────────────────────────────────

def test_a_log_that_cannot_be_WRITTEN_does_not_fail_the_move(board):
    """The board is the record and this is the account of it. Losing a
    line costs a gap in a story; failing the write costs a card in the
    wrong column."""
    os.makedirs(os.path.join(board, "amik", "log.jsonl"))
    res = edit.move(board, "a-card", "doing", 0, by="user")
    assert res["ok"], res


def test_a_TORN_line_does_not_take_the_history_with_it(board):
    """Appended to by a process that can be killed mid-write."""
    edit.move(board, "a-card", "doing", 0)
    with open(os.path.join(board, "amik", "log.jsonl"), "a") as f:
        f.write('{"at": "2026-01-0')
    edit.move(board, "a-card", "review", 0)
    assert len(_lines(board)) == 2


def test_a_REFUSED_write_is_not_logged(board):
    """The log says what happened. A stale move did not happen."""
    edit.move(board, "a-card", "doing", 0, fingerprint="nonsense")
    assert _events(board) == []


# ── reading it back ─────────────────────────────────────────────────

def test_it_can_be_read_for_one_card(board):
    edit.move(board, "a-card", "doing", 0)
    edit.create(board, "Another")
    assert [e["card"] for e in log.read(board, card="a-card")] == ["a-card"]


def test_the_log_travels_with_the_board():
    """A project that tracks its board tracks its log. THIS repository
    ignores both, because its board is whoever is working here."""
    from conftest import REPO
    with open(os.path.join(REPO, ".gitignore"), encoding="utf-8") as f:
        text = f.read()
    assert "amik/log.jsonl" in text
    assert "amik/board.jsonl" in text
