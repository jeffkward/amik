"""The card modal opens to be READ.

Details used to open as a form on every card — four inputs, a toggle
strip and an editor showing raw markdown — beside tabs that already read
as rendered prose. So the modal opened in the rarer state, and a card is
read far more often than it is written.

View mode is the default now: the card's facts as chips, its prose
rendered, and a pencil that swaps in what Details used to show. The one
piece of real work is the boundary — the body a card shows and the body
its editor holds both EXCLUDE the sections with tabs of their own, and
reader and writer share one rule for where that falls. A third rule is
how a phantom section appears, which this board has already paid for
once.
"""
import json
import os

from amik.core import board as readers
from amik.core import edit as amik_edit
from amik.core import markdown as amik_markdown

from tests.test_amik_page import _board, _card_html, _detail_html, _css, _js

CARD = """The modal opens in the rarer state.

**A ruling.** Cards are read more than they are written.

## Questions

### Where does Edit live?

> Three shapes.

A pencil.

## Outcome

Built it.
"""

ROW = {"id": "a", "title": "T", "status": "ready", "planning": None,
       "group": None, "rank": 1, "created_at": "2026-09-14",
       "updated_at": "2026-09-14"}


# ── the boundary ────────────────────────────────────────────────────────

def test_the_body_stops_at_the_first_promoted_heading():
    body, promoted = amik_markdown.split_promoted(CARD)
    assert "The modal opens in the rarer state." in body
    assert "## Questions" not in body and "## Outcome" not in body
    assert promoted.startswith("## Questions")
    assert "## Outcome" in promoted


def test_a_card_with_no_promoted_section_is_all_body():
    body, promoted = amik_markdown.split_promoted("Just prose.\n")
    assert body == "Just prose.\n"
    assert promoted == ""


def test_a_fenced_heading_is_content_not_a_boundary():
    """The rule `_card_questions` and `_card_outcome` already keep. A
    model answering a question emits fenced code constantly, and a body
    that split inside one would take the rest of the card with it."""
    prose = "Before.\n\n```\n## Outcome\n```\n\nAfter.\n"
    body, promoted = amik_markdown.split_promoted(prose)
    assert body == prose and promoted == ""


def test_an_outcome_alone_splits_too():
    body, promoted = amik_markdown.split_promoted("Prose.\n\n## Outcome\n\nDone.\n")
    assert body.strip() == "Prose."
    assert promoted.strip().startswith("## Outcome")


def test_the_reader_hands_the_page_a_body_without_the_promoted_sections(
        instance):
    _board(instance, [dict(ROW, body=CARD)])
    card = readers.amik(str(instance))["data"]["columns"][2]["cards"][0]
    assert "## Questions" not in card["overview"]
    assert "## Outcome" not in card["overview"]
    assert "**A ruling.**" in card["overview"]
    # The whole file is still there for anything that wants it.
    assert "## Outcome" in card["body"]


# ── what the page renders ───────────────────────────────────────────────

def test_the_card_carries_its_prose_rendered_and_its_body_raw(client,
                                                              instance):
    """Two forms of one text: rendered for view mode, raw for the editor.
    Both come from the same reader, so neither can show a section the
    other hides."""
    _board(instance, [dict(ROW, body=CARD)])
    detail = _detail_html(client, "a")
    rendered = detail.split('class="akbodysrc"', 1)[1].split("</div>", 1)[0]
    assert "<b>A ruling.</b>" in rendered
    assert "Where does Edit live?" not in rendered
    assert "Built it." not in rendered
    source = detail.split('class="akraw"', 1)[1].split("</textarea>", 1)[0]
    assert "## Questions" not in source and "## Outcome" not in source
    assert "The modal opens in the rarer state." in source


def test_a_card_with_no_prose_renders_no_body_at_all(client, instance):
    _board(instance, [ROW])
    detail = _detail_html(client, "a")
    assert "akbodysrc" not in detail


def test_the_view_strip_leads_with_the_status_its_column_names(client,
                                                               instance):
    """The one fact a dialog drops: it covers the board it came from. The
    label is the column's own, so renaming a column renames this."""
    _board(instance, [dict(ROW, status="abandoned")])
    detail = _detail_html(client, "a")
    strip = detail.split('class="akchips akvchips"', 1)[1].split("</span>", 1)[0]
    assert "Abandoned" in strip, "the column's own label"
    assert "akstatus" in strip


def test_the_view_strip_carries_the_area_and_the_rung(client, instance):
    _board(instance, [dict(ROW, status="todo", planning="has-plan",
                           group="face")])
    view = _detail_html(client, "a").split('class="akchips akvchips"', 1)[1]
    assert "has-plan" in view
    assert "face" in view


def test_a_handling_icon_shows_only_when_it_is_on(client, instance):
    """A chip says something is TRUE of this card — the law every other
    chip on this board keeps. An unset toggle is not a fact."""
    _board(instance, [ROW])
    plain = _detail_html(client, "a")
    assert "akhandling" not in plain

    _board(instance, [dict(ROW, halt=True,
                           requires_prototype=True)])
    loud = _detail_html(client, "a")
    assert loud.count("akhandling") == 2
    assert "pause" in loud and "prototype" in loud


def test_the_tile_still_carries_no_status_chip(client, instance):
    """The card face sits IN its column, so a status chip there restates
    what the reader can already see. Only the modal, which covers the
    board, has to say it."""
    _board(instance, [dict(ROW, status="todo")])
    assert "akstatus" not in _card_html(client.get("/amik").text, "a")


def test_the_view_markup_has_one_definition(client, instance):
    """Rendered from the same partial the save route hands back. A second
    copy in the page or a script would drift, and nothing would say so.

    The card's block left the page for `_carddata.html`, which is what the
    card route renders — so the include is asserted there, and the page is
    still asserted to carry no copy of its own."""
    here = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "app", "templates")
    page = open(os.path.join(here, "board.html"), encoding="utf-8").read()
    data = open(os.path.join(here, "_carddata.html"), encoding="utf-8").read()
    assert "_cardview.html" in data
    for markup in (page, data):
        assert "akstatus" not in markup, "view chip markup moved to the partial"


# ── the body field ──────────────────────────────────────────────────────

def test_the_body_field_is_a_plain_textarea(client, instance):
    """A rich editor renders into a contenteditable surface, and iOS gives
    one none of the keyboard's help: no autocorrect, no autocapitalisation
    and no predictive strip. This board is written from a phone.

    The three attributes are the browser's own defaults, named anyway --
    `spellcheck="false"` is the house style on a source field and would
    turn the keyboard back off if it were ever copied in here."""
    _board(instance, [ROW])
    tag = client.get("/amik").text.split('id="akeditor"', 1)
    assert tag[0].endswith("<textarea "), tag[0][-40:]
    tag = tag[1].split(">", 1)[0]
    assert 'spellcheck="true"' in tag
    assert 'autocorrect="on"' in tag
    assert 'autocapitalize="sentences"' in tag


def test_no_editor_bundle_is_shipped_or_imported(client, instance):
    """The field needs no JavaScript at all, so the 572KB bundle and its
    glue are gone rather than merely unreferenced -- a vendored file kept
    beside a page that no longer loads it is the one nobody notices."""
    assert "import(" not in _js("amik.js")
    for name in ("cm6.js", "editor-init.js"):
        assert client.get("/amik/static/" + name).status_code == 404, name


def test_the_form_and_the_view_swap_rather_than_stack():
    js = _js("amik.js")
    edit_fn = js.split("function startEditing() {", 1)[1].split("\n  }\n", 1)[0]
    assert "viewPane.hidden = true;" in edit_fn
    assert "form.hidden = false;" in edit_fn
    fill_fn = js.split("function fill(b) {", 1)[1].split("\n  }\n", 1)[0]
    assert "form.hidden = true;" in fill_fn
    assert "viewPane.hidden = false;" in fill_fn


def test_neither_mode_carries_a_display_rule():
    """`[hidden]` is a UA rule any `display` value beats — the trap
    .akfield, .akqlist and .akq each fell into. Here it would show both
    modes at once."""
    css = _css()
    for selector in ("#akview {", "#akform {"):
        assert selector not in css


def test_the_body_a_card_opens_with_is_the_body_it_saves():
    """One field is reused across every card, so reading it in view mode
    answers with whatever card was edited LAST. A snapshot that did that
    would mark an untouched card dirty and offer to discard edits nobody
    made."""
    js = _js("amik.js")
    body_fn = js.split("function bodyText() {", 1)[1].split("\n  }\n", 1)[0]
    assert "editing ? host.value" in body_fn
    assert "docText" in body_fn
    snapshot = js.split("function snapshot() {", 1)[1].split("\n  }\n", 1)[0]
    assert "bodyText()" in snapshot
    assert "host.value" not in snapshot


# ── saving a body back ──────────────────────────────────────────────────

def _fingerprint(instance):
    return readers.amik_fingerprint(str(instance))


def test_a_saved_body_leaves_the_promoted_sections_alone(client, instance):
    """The editor never held them. Reattaching them is the door's job, so
    the page carries no copy of where the boundary falls."""
    _board(instance, [dict(ROW, body=CARD)])
    r = client.patch("/amik/cards/a", data={
        "title": "T", "overview": "Rewritten body.",
        "fingerprint": _fingerprint(instance)})
    assert r.status_code == 200, r.text
    prose = open(amik_edit.card_path(str(instance), "a"),
                 encoding="utf-8").read()
    assert prose.startswith("Rewritten body.")
    assert "### Where does Edit live?" in prose
    assert "> Three shapes." in prose
    assert "## Outcome\n\nBuilt it." in prose


def test_a_card_with_no_promoted_section_saves_its_body_whole(client,
                                                              instance):
    _board(instance, [dict(ROW, body="Old prose.\n")])
    r = client.patch("/amik/cards/a", data={
        "title": "T", "overview": "New prose.",
        "fingerprint": _fingerprint(instance)})
    assert r.status_code == 200, r.text
    assert open(amik_edit.card_path(str(instance), "a"),
                encoding="utf-8").read().strip() == "New prose."


def test_an_answer_and_a_body_edit_can_ride_together(client, instance):
    """One Save posts both. The answer splices into the prose the body
    edit just produced, not into the text the page loaded with."""
    _board(instance, [dict(ROW, body=CARD)])
    r = client.patch("/amik/cards/a", data={
        "title": "T", "overview": "Rewritten body.",
        "answers": json.dumps([{"heading": "Where does Edit live?",
                                "text": "On the pane."}]),
        "fingerprint": _fingerprint(instance)})
    assert r.status_code == 200, r.text
    prose = open(amik_edit.card_path(str(instance), "a"),
                 encoding="utf-8").read()
    assert prose.startswith("Rewritten body.")
    assert "On the pane." in prose
    assert "A pencil." not in prose
    assert "> Three shapes." in prose, "the asker's context stays"


def test_the_save_hands_back_the_view_it_just_changed(client, instance):
    """Same reason the tile's chips come back: the block the modal reads
    from is written by this page, so a reopened card would otherwise show
    what the file said at page load."""
    _board(instance, [dict(ROW, body=CARD)])
    out = client.patch("/amik/cards/a", data={
        "title": "T", "overview": "Rewritten body.", "group": "face",
        "fingerprint": _fingerprint(instance)}).json()
    assert "view" in out
    assert "Rewritten body." in out["view"]
    assert "Built it." not in out["view"]
    assert "face" in out["view"]


def test_a_body_cleared_to_nothing_comes_back_empty(client, instance):
    """The pane has to be able to lose its prose, the same way a tile has
    to be able to lose a chip."""
    _board(instance, [dict(ROW, body=CARD)])
    out = client.patch("/amik/cards/a", data={
        "title": "T", "overview": "",
        "fingerprint": _fingerprint(instance)}).json()
    assert "akbodysrc" not in out["view"]
    prose = open(amik_edit.card_path(str(instance), "a"),
                 encoding="utf-8").read()
    assert prose.startswith("## Questions"), "the sections survive"


def test_the_page_posts_the_body_and_never_the_whole_file():
    js = _js("amik.js")
    save = js.split("function save() {", 1)[1].split("\n  }\n", 1)[0]
    assert "body.set('overview', doc);" in save
    assert "body.set('body'" not in save
