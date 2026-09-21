"""The one way out of a bad outcome that needs a control.

Every other verdict IS a destination, and destinations clean up after
themselves however you reach them: Done lands the card, Abandoned drops
its branch, and answering the last question returns it to Ready on its
own. Throwing the build away and going again is the only one with no
status to drag to — dragging to Ready keeps the branch, so the next run
would resume the very attempt being rejected.

It sits under the outcome because that is where the judgement is made,
not in a footer already four controls wide on a phone. Small and
outlined: real, rare, and not competing with Save.
"""

import os

from tests.test_amik_page import ROWS, _board


def _css():
    return open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "app", "static", "amik.css")).read()


def _js():
    return open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "app", "static", "amik.js")).read()


def _pane(html):
    start = html.index('id="akoutcome"')
    return html[start:html.index("</div>\n  </div>", start)]


def test_the_one_button_lives_in_the_outcome_pane(client, instance):
    _board(instance, ROWS)
    assert 'id="akdiscard"' in _pane(client.get("/amik").text)


def test_the_pane_has_a_body_the_actions_do_not_live_in(client, instance):
    """`buildOutcome` replaces the body's children on every open. With
    the actions inside that element they would be wiped by the first
    card opened."""
    _board(instance, ROWS)
    assert 'id="akoutbody"' in client.get("/amik").text
    js = _js()
    assert "outcomeBody.replaceChildren" in js
    assert "outcome.replaceChildren" not in js


def test_it_asks_for_feedback_and_sends_it(client, instance):
    """The moment you decide to retry is when you know what went
    wrong. Asking then beats making someone find a spot afterwards."""
    js = _js()
    block = js[js.index("discardBtn.addEventListener"):]
    assert "Do you have feedback for the agent?" in block
    assert "body.set('feedback', answer.text)" in block

