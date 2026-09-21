"""A prototype is reachable from the card as it OPENS.

Cards open in view mode now. The only link to a design pass lived inside
the form, so looking at the thing a card was built to produce meant
clicking through to an editor first -- on a card whose whole reason for
halting was that somebody should look at it.

The chip already said `prototype` when one was merely asked for. Once one
exists it stops describing an intention and becomes the way to see it,
which is the rule the form's own toggle already keeps.
"""

import os

from amik.app import render


def _card(**over):
    card = {"id": "c1", "status": "review", "status_label": "Review",
            "planning_chip": "", "blocking": False, "group": "",
            "halt": False, "branch_requested": False,
            "requires_prototype": True, "has_prototype": False,
            "conflict": "", "conflict_label": "", "question_flag": False,
            "question_flag_label": "", "unanswered": 0,
            "overview": "Some prose."}
    card.update(over)
    return card


def test_a_card_with_a_prototype_links_to_it_in_view_mode():
    html = render.card_view(_card(has_prototype=True))
    assert "View prototype" in html
    assert "/cards/c1/prototype" in html

