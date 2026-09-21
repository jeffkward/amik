"""A save repaints the card's tile with freshly DERIVED chips.

Before this, a save wrote the title back to the tile and left the chips
at page-load state: change a card's rung or area and the tile kept the
old ones until a manual refresh. The chips were deliberately left alone,
and for a good reason — the ⚠ conflict, the question flag and a rung's
blocking styling are the READER's derivations, not the page's, so a
script recomputing them would be a second source of truth.

So the server sends them back. The route re-reads the board after the
write and renders the same partial the page does, which keeps one
definition of the markup and leaves every derivation where it belongs.
"""
import json

from tests.test_amik_page import _board

ROW = {"id": "a", "title": "T", "status": "ready", "planning": None,
       "group": None, "rank": 1, "created_at": "2026-09-14",
       "updated_at": "2026-09-14"}


def _save(client, instance, **fields):
    from amik.core import board as readers
    data = {"title": "T", "body": "",
            "fingerprint": readers.amik_fingerprint(instance)}
    data.update(fields)
    r = client.patch("/amik/cards/a", data=data)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_save_returns_the_card_s_chips(instance, client):
    _board(instance, [ROW])
    out = _save(client, instance, planning="has-plan", group="face")
    assert "chips" in out
    assert "has-plan" in out["chips"]
    assert "face" in out["chips"]


def test_a_derived_chip_comes_back_derived(instance, client):
    """The whole reason this goes through the server. A `ready` card given
    a blocking rung is a contradiction the READER computes — no script on
    the page knows that rule, and one that guessed would be a second
    source of truth."""
    _board(instance, [ROW])
    out = _save(client, instance, planning="needs-brainstorm", group="face")
    assert "⚠" in out["chips"]
    assert "akconflict" in out["chips"]


def test_clearing_every_chip_returns_nothing_to_paint(instance, client):
    """An empty string, not a stale block. The tile must be able to LOSE
    a chip, which is half of what the card asked for."""
    _board(instance, [dict(ROW, planning="has-plan", group="face")])
    out = _save(client, instance, planning="none", group="none")
    assert out["chips"].strip() == ""


def test_the_chip_markup_has_one_definition(instance, client):
    """Rendered from the same partial the board page includes. A second
    copy in a script or a route would drift, and nothing would say so."""
    import os
    page = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "app", "templates", "board.html"),
        encoding="utf-8").read()
    assert "_chips.html" in page
    assert "akconflict" not in page, "chip markup moved to the partial"


def test_the_board_page_still_renders_chips(instance, client):
    """The extraction must not cost the page its own chips."""
    _board(instance, [dict(ROW, planning="needs-brainstorm", group="face")])
    html = client.get("/amik").text
    assert "akconflict" in html
    assert "needs-brainstorm" in html
    assert "face" in html


def test_a_card_with_nothing_to_say_renders_no_chip_row(instance, client):
    """On the TILE. A chip there says something is true of this card that
    is not true of the column it sits in, so a card with nothing to add
    gets no row at all. The modal's own strip is a different promise — it
    answers "what does this card say" for a dialog covering the board —
    and always carries at least the status."""
    from tests.test_amik_page import _card_html
    _board(instance, [ROW])
    html = client.get("/amik").text
    assert "akchips" not in _card_html(html, "a")
