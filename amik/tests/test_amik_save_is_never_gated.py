"""Save is always pressable.

Gating it on a dirty check means the button has to be repainted by change
events, and the body is the field most likely to be edited without one.
The button then sits dead over a real edit until some other field is
touched.

What the gate was buying is a write that changes nothing, which costs a
file rewrite and a fingerprint bump. What it cost is an edit that cannot
be saved at all, with no way to tell the two apart from the outside.
"""

import os

from tests.test_amik_page import _js


def test_nothing_ever_disables_the_save_button():
    src = _js("amik.js")
    gates = [ln.strip() for ln in src.splitlines()
             if "saveBtn" in ln and "disabled" in ln]
    assert gates == [], gates


def test_the_markup_does_not_ship_it_disabled():
    """The same bug with nothing in the JS to find: there is no longer any
    code that would re-enable it."""
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "app", "templates", "board.html")
    lines = [ln for ln in open(path).read().splitlines()
             if 'id="aksave"' in ln]
    assert len(lines) == 1, lines
    assert "disabled" not in lines[0], lines[0]
