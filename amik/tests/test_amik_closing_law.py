"""Who may close a card.

The old law was flat: Done is the owner's signal. It was written when
Done authorised a MERGE. Where there is no merge to authorise, Done means
only "this is finished", which is not a decision and does not need them.

`ready` is untouched and stays their pull.
"""
from amik.core import board as readers


def test_an_unhalted_card_with_an_outcome_may_be_closed_by_the_agent():
    assert readers.amik_agent_may_close(
        {"id": "a", "outcome": "Landed in abc123."}) is True


def test_an_unhalted_card_with_no_outcome_may_not():
    """The outcome gate joined this predicate: a card can close with no
    commit at all, and for those the git log says nothing and the
    terminal where the agent said what happened dies with the session."""
    assert readers.amik_agent_may_close({"id": "a"}) is False


def test_a_halted_card_may_not():
    assert readers.amik_agent_may_close(
        {"id": "a", "outcome": "Done.", "halt": True}) is False


def test_a_prototype_card_may_not(tmp_path):
    """A prototype forces a halt, so this is belt and braces — but the
    predicate must not depend on the UI having enforced it."""
    assert readers.amik_agent_may_close(
        {"id": "a", "outcome": "Done.", "requires_prototype": True}) is False

