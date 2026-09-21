"""Who wrote an outcome.

A board can be worked by more than one model, and by one whose quality
moves under it. Without attribution that difference reads as "the board
got worse this week" with nothing to point at.

The line has two halves and they differ in trust. The HARNESS comes from
the environment and cannot be misreported. The MODEL is knowable only to
the agent — no environment variable carries it — so it is self-reported,
exactly like the outcome it sits under. It attributes; it does not prove.
"""
import importlib
import json
import os

from amik.core import board, edit


def _one(root, prose="Body.\n"):
    os.makedirs(os.path.join(root, "amik", "cards"), exist_ok=True)
    row = {"id": "a", "title": "A card", "status": "doing", "planning": None,
           "rank": 1, "created_at": "2026-01-01T00:00:00",
           "updated_at": "2026-01-01T00:00:00"}
    with open(os.path.join(root, "amik", "board.jsonl"), "w") as f:
        f.write(json.dumps(row) + "\n")
    edit.write_prose(root, "a", prose)
    return root


def test_the_model_is_named_in_the_outcome(tmp_path):
    root = _one(str(tmp_path))
    edit.record_outcome(root, "a", "Landed in abc123.", model="Opus 5")
    got = board._card_outcome(edit.card_path(root, "a") and
                              open(edit.card_path(root, "a")).read())
    assert "Landed in abc123." in got
    assert "Opus 5" in got


def test_an_unnamed_model_says_so_rather_than_going_quiet(tmp_path):
    """An omitted line cannot be told apart from an entry written before
    attribution existed. A gap you cannot see is a gap nobody closes."""
    root = _one(str(tmp_path))
    edit.record_outcome(root, "a", "Landed.")
    got = open(edit.card_path(root, "a")).read()
    assert "model unrecorded" in got


def test_two_outcomes_are_attributed_separately(tmp_path):
    """The attribution belongs to the ENTRY, not the card — a card worked
    twice may have been worked by two different models, which is the
    whole case this exists for."""
    root = _one(str(tmp_path))
    edit.record_outcome(root, "a", "First pass.", model="Sonnet 5")
    edit.record_outcome(root, "a", "Second pass.", model="Opus 5")
    got = open(edit.card_path(root, "a")).read()
    assert got.index("Sonnet 5") < got.index("Second pass.") < got.index("Opus 5")


def test_the_harness_comes_from_the_environment_not_the_agent(monkeypatch):
    """The half that cannot be misreported."""
    monkeypatch.setenv("AI_AGENT", "claude-code_2-1-267_agent")
    importlib.reload(edit)
    assert "claude-code 2.1.267" in edit.attribution("Opus 5")


def test_an_unfamiliar_harness_string_is_passed_through(monkeypatch):
    """A vendor changing its format must cost legibility, not
    correctness."""
    monkeypatch.setenv("AI_AGENT", "some-other-runner/9")
    importlib.reload(edit)
    assert "some-other-runner/9" in edit.attribution("Opus 5")


def test_no_harness_at_all_still_attributes_the_model(monkeypatch):
    monkeypatch.delenv("AI_AGENT", raising=False)
    importlib.reload(edit)
    line = edit.attribution("Haiku 4.5")
    assert "Haiku 4.5" in line and "·" not in line

