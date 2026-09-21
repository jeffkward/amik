"""The handling toggles, as icons rather than a checkbox.

Each reads as an instruction — "build a prototype" — not as the question
a checkbox asks. Each is glyph-only, so each MUST carry an accessible
name; nothing else names them.
"""
from tests.test_amik_page import _board, _card_html, _detail_html, _open_fn

ROW = {"id": "a", "title": "T", "status": "ready", "planning": None,
       "rank": 1, "created_at": "2026-09-14", "updated_at": "2026-09-14"}


def test_the_two_toggles_render(instance, client):
    _board(instance, [ROW])
    html = client.get("/amik").text
    for el in ("akf-halt", "akf-prototype"):
        assert f'id="{el}"' in html, el


def test_each_toggle_is_named(instance, client):
    """Glyph-only controls. An aria-label is the only name they have."""
    _board(instance, [ROW])
    html = client.get("/amik").text
    for name in ("Pause for review", "Build a prototype"):
        assert f'aria-label="{name}"' in html, name


def test_the_route_accepts_the_handling_fields(instance, client):
    import json
    from amik.core import board as readers
    _board(instance, [ROW])
    r = client.patch("/amik/cards/a", data={
        "title": "T", "halt": "on",
        "fingerprint": readers.amik_fingerprint(instance)})
    assert r.status_code == 200, r.text
    row = json.loads(open(f"{instance}/amik/board.jsonl").read().strip())
    assert row["halt"] is True


def _with_prototype(instance):
    import os
    os.makedirs(f"{instance}/amik/prototypes/a", exist_ok=True)
    open(f"{instance}/amik/prototypes/a/index.html", "w").write("<html></html>")
    _board(instance, [ROW])


def test_opening_a_prototype_card_with_no_halt_forces_it_pressed():
    """The one dialog markup is shared by every card and always starts
    `aria-pressed="false"` -- only `open()` fills in a card's real state,
    so the server-rendered page can never show this bug either way. A row
    can carry `requires_prototype: true` with no `halt` at all (hand-edited,
    or written before this pairing existed); `open()` used to read `halt`
    as the row said it and lock the toggle disabled straight after, so such
    a card opened with the pause unpressed AND unclickable -- no way to
    turn it on, and the queue would not stop behind it.

    Bounded to `open()`'s own body via `_open_fn()`, and to `f.halt` --
    the halt button's own element (see the `f` map's `getElementById`) --
    rather than the whole file: the click handler already presses
    `f.halt`, so an unbounded search for that line would pass whether or
    not `open()` itself did anything."""
    body = _open_fn()
    assert "if (pressed(f.prototype)) { press(f.halt, true); }" in body
    # Forced on before the toggle is locked, matching the click handler.
    # The locking itself now lives in paintHandling(), which also reads
    # the status — the ordering it has to keep is the same one.
    assert body.index("press(f.halt, true)") < body.index("paintHandling()")


# ── a closed card's handling is a record, not a lever ──────────────────


def _amik_js():
    import os
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
    return open(os.path.join(here, "static", "amik.js")).read()


def test_the_toggles_are_locked_on_a_closed_card():
    """Nothing reads them once a card is closed: the queue takes its gate
    from a halted card in `review` or in `ready`, a closed card is not
    going to be built on a branch, and the prototype sweep keys off the
    directory rather than the flag."""
    js = _amik_js()
    assert "var CLOSED = ['done', 'abandoned'];" in js
    paint = js.split("function paintHandling()", 1)[1].split("\n  }", 1)[0]
    assert "f.prototype.disabled = closed;" in paint


def test_a_shelved_card_keeps_its_handling():
    """`someday` is not closed — a shelved card is still going to be
    worked, and recording "this one needs a branch" while shelving it is
    a note about future work, not a moot field."""
    js = _amik_js()
    assert "'someday'" not in js.split("var CLOSED =", 1)[1].split("]", 1)[0]


def test_a_closed_card_keeps_showing_how_it_was_handled():
    """Disabled, never cleared. A done card still showing ⏸ pressed is how
    it says it paused for a look before it landed; clearing the field
    would erase that. The planning rung IS cleared on a closed row because
    it says what is still owed, which is a different kind of fact."""
    js = _amik_js()
    paint = js.split("function paintHandling()", 1)[1].split("\n  }", 1)[0]
    assert "press(" not in paint          # it disables; it never unsets


def test_the_prototype_still_forces_the_halt_on_an_open_card():
    """The lock a prototype puts on the halt has to survive the new rule,
    or a card could ask for a design pass and then be un-paused."""
    js = _amik_js()
    assert "f.halt.disabled = closed || pressed(f.prototype);" in js


def test_the_halt_rule_is_computed_in_exactly_one_place():
    """It used to be written in `open()` and again in the click handler —
    two copies of one rule, waiting to disagree."""
    js = _amik_js()
    assert js.count("f.halt.disabled") == 1


def test_changing_status_in_the_modal_repaints_the_handling():
    """Status is editable in this same modal, so moving a card out of a
    closed column has to hand the toggles back without a save and a
    reopen."""
    assert "f.status.addEventListener('change', paintHandling);" in _amik_js()


# ── an icon chip needs a name that is not the icon ─────────────────────


def test_the_branch_chip_shows_the_branch_name(instance, client):
    """The icon was the whole chip: an aria-hidden SVG with no visible
    text and no aria-label, while every sibling chip pairs a tooltip with
    a visible label. The name is what the label should be — it is the one
    fact the board carries nowhere else, and these chips sit inside a
    draggable `button.akcard`, so they cannot be made focusable to reach
    their own tooltip."""
    _board(instance, [dict(ROW, branch="card/a-long-branch-name")])
    body = client.get("/amik").text
    # Bounded to the CARD's chip row: the board header's git-branch chip
    # carries the same `.akbranch` class and comes first in the document,
    # so an unbounded split reads the wrong element entirely.
    row = body.split('class="akchips"', 1)[1].split("</span>\n</span>", 1)[0]
    chip = row.split('class="chip akbranch', 1)[1].split("</span></span>", 1)[0]
    assert "akchiplabel" in chip
    assert "card/a-long-branch-name" in chip
    # the tooltip keeps the whole string, since the label truncates
    assert 'data-tip="card/a-long-branch-name"' in chip


def test_the_modal_carries_the_branch_name_too(instance, client):
    """The chip's tooltip is mouse-only by construction. The modal is
    reachable, so the name lives there as well — inert text, since
    `branch` is deliberately outside EDITABLE and `set_branch` is its
    only door."""
    _board(instance, [dict(ROW, branch="card/a-long-branch-name")])
    assert 'data-branch="card/a-long-branch-name"' in _detail_html(
        client, "a")
    body = client.get("/amik").text
    dlg = body.split('id="akdlg"', 1)[1].split("</dialog>", 1)[0]
    assert 'id="akf-branchname"' in dlg
    js = _amik_js()
    assert "branchName.hidden = !d.branch;" in js
    assert "branchName.lastElementChild.textContent = d.branch || '';" in js


def test_the_spinner_stops_for_reduced_motion():
    """Motion that cannot be stopped is not decoration. The dot stays so
    the chip reads the same; it simply stops turning."""
    import os
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
    css = open(os.path.join(here, "static", "amik.css")).read()
    # Bound to the block that actually names .akspin: app.css carries five
    # reduced-motion blocks, and splitting on the first reads a rule
    # written about something else entirely.
    import re
    blocks = re.findall(r"@media \(prefers-reduced-motion:\s*reduce\)\s*\{"
                        r"(.*?)\n\}", css, re.S)
    mine = [b for b in blocks if ".akspin" in b]
    assert mine, "no reduced-motion block mentions .akspin"
    assert "animation:none" in mine[0]
