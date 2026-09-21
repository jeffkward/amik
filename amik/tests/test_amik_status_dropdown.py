"""A status dropdown on the card edit form.

Asked for because dragging across lanes is hard on a phone — spanning
several columns with a finger is the one board gesture a small screen
makes worse.

The important part is what it must NOT become. `status` and `rank` are
the DRAG's business: `amik_edit.move` renumbers the columns a card leaves
and joins, and it is the only function that writes either field. The edit
route deliberately omits them from its signature so a smuggled `status=`
is absent by construction rather than ignored by luck.

So the dropdown does not teach the edit route a new field. It posts to
`/amik/move`, the same route the drag already uses, and `move` stays the
one writer.
"""
import json

from tests.test_amik_page import _board

ROW = {"id": "a", "title": "T", "status": "inbox", "planning": None,
       "group": None, "rank": 1, "created_at": "2026-09-14",
       "updated_at": "2026-09-14"}


def _row(instance, item_id="a"):
    for line in open(f"{instance}/amik/board.jsonl"):
        if line.strip() and json.loads(line)["id"] == item_id:
            return json.loads(line)
    raise AssertionError("row gone")


# ── the control ─────────────────────────────────────────────────────────

def test_the_modal_offers_every_column(instance, client):
    from amik.core import board as readers
    _board(instance, [ROW])
    html = client.get("/amik").text
    assert 'id="akf-status"' in html
    from markupsafe import escape
    for status, label, _ in readers.AMIK_COLUMNS:
        # Escaped, because a label is free text: "Won't Do" carried an
        # apostrophe until the 2026-09-17 rename, and the next one might.
        assert f'<option value="{status}">{escape(label)}</option>' in html, \
            status


# ── the law it must not break ───────────────────────────────────────────

def test_the_edit_route_still_cannot_write_status(instance, client):
    """Absent by construction, not ignored by luck. A smuggled status must
    change nothing — and must not error either, since FastAPI simply does
    not bind a field the signature never named."""
    from amik.core import board as readers
    _board(instance, [ROW])
    r = client.patch("/amik/cards/a", data={
        "title": "T", "status": "done", "rank": "9",
        "fingerprint": readers.amik_fingerprint(instance)})
    assert r.status_code == 200, r.text
    assert _row(instance)["status"] == "inbox"
    assert _row(instance)["rank"] == 1


def test_status_is_not_an_editable_field():
    from amik.core import edit as amik_edit
    assert "status" not in amik_edit.EDITABLE
    assert "rank" not in amik_edit.EDITABLE


def test_the_dropdown_posts_to_the_move_door():
    """One writer for status. A second path that wrote it directly is how
    a board and its file drift."""
    import os
    static = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "app", "static")
    src = open(os.path.join(static, "amik.js"), encoding="utf-8").read()
    start = src.find("akf-status")
    assert start != -1
    # The move door is a nested resource now: position belongs to the
    # drag, and folding it into the card's own PATCH would merge two
    # writers the design keeps apart.
    assert "/position" in src
    assert "akSend('PATCH'" in src


def test_a_status_pick_outranks_the_unblock_reload():
    """One save can carry an answer AND a status change. Answering the
    last question on a blocked card sends it to Ready on its own, and the
    answers branch reloads the page — so a status post queued after that
    reload would never be sent, and the derived move would look like it
    had overruled a choice the owner made out loud. The pick posts
    first."""
    import os
    static = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "app", "static")
    src = open(os.path.join(static, "amik.js"), encoding="utf-8").read()
    pick = src.find("mv.set('to_status'")
    reload_on_answers = src.find(
        "if (answers.length) { window.location.reload()")
    assert pick != -1 and reload_on_answers != -1
    assert pick < reload_on_answers


# ── and the door still does the work ────────────────────────────────────

def test_moving_through_the_door_renumbers_and_stamps(instance, client):
    """What the dropdown will cause, exercised at the route the drag and
    the modal share."""
    from amik.core import board as readers
    _board(instance, [ROW, dict(ROW, id="b", rank=2)])
    r = client.patch("/amik/cards/a/position", data={ "to_status": "ready", "to_index": "0",
        "fingerprint": readers.amik_fingerprint(instance)})
    assert r.status_code == 200, r.text
    assert _row(instance, "a")["status"] == "ready"
    assert _row(instance, "b")["rank"] == 1, "the column it left renumbers"


def test_an_index_past_the_end_lands_at_the_end(instance, client):
    """A dropdown has no drop position, so it appends. The clamp in
    `move_item` is what makes that safe from a stale count."""
    from amik.core import board as readers
    _board(instance, [ROW, dict(ROW, id="b", status="ready", rank=1),
                      dict(ROW, id="c", status="ready", rank=2)])
    r = client.patch("/amik/cards/a/position", data={ "to_status": "ready", "to_index": "999",
        "fingerprint": readers.amik_fingerprint(instance)})
    assert r.status_code == 200, r.text
    assert _row(instance, "a")["rank"] == 3
