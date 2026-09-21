"""The ladder answers one question: does this card still owe thinking?

Four of six rungs left. `just-do-it` was a handling instruction wearing a
readiness costume and is the halt toggle now. `decision-needed` was the
question mechanism said twice — an unanswered question already holds a
card, chips it, and tells the queue why. `brainstorm-complete` and
`build-ready` both meant "nothing owed", which is what absent means.
"""
import pytest

from amik.core import edit as amik_edit
from amik.core import board as readers


def test_the_ladder_is_two_rungs_plus_absent():
    assert amik_edit.RUNGS == ("needs-brainstorm", "has-plan")


def test_only_needs_brainstorm_blocks():
    assert readers.AMIK_BLOCKING == ("needs-brainstorm",)
    assert readers.AMIK_BLOCKS_READY == readers.AMIK_BLOCKING


def test_the_reader_and_the_writer_agree_on_the_ladder():
    """Two lists of the same vocabulary drift. The reader's order is the
    writer's order."""
    assert tuple(readers.AMIK_PLANNING) == amik_edit.RUNGS


@pytest.mark.parametrize("retired", [
    "brainstorm-needed", "decision-needed", "brainstorm-complete",
    "plan-exists", "build-ready", "just-do-it"])
def test_a_retired_spelling_is_refused_not_translated(retired):
    """Errors, never aliases. A stale token
    must fail loudly rather than be silently reinterpreted."""
    text = ('{"id": "a", "title": "T", "status": "todo", "planning": null, '
            '"rank": 1, "created_at": "2026-09-14", '
            '"updated_at": "2026-09-14"}')
    with pytest.raises(ValueError):
        amik_edit.update_item(text, "a", {"planning": retired})
