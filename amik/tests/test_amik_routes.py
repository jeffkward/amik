"""POST /amik/move — the board's only write path.

Hidden the same way the page is: no amik file, no route. Guarded the
same way every other face POST is (foreign Origin refused), plus a
fingerprint so a drag cannot overwrite a hand edit made since the page
was rendered.
"""
import json
import os

from amik.core import edit as amik_edit
from tests.test_amik_page import ROWS, _board, _card_file


def _read(instance):
    path = os.path.join(str(instance), "amik", "board.jsonl")
    with open(path) as f:
        return {json.loads(l)["id"]: json.loads(l)
                for l in f if l.strip()}


def _card_prose(instance, item_id):
    path = amik_edit.card_path(str(instance), item_id)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def _fingerprint(client):
    body = client.get("/amik").text
    mark = 'data-fingerprint="'
    return body.split(mark, 1)[1].split('"', 1)[0]


def _delete(client, instance, item_id, fp=None):
    return client.delete("/amik/cards/" + item_id, data={
        "fingerprint": fp if fp is not None else _fingerprint(client)})


def _move(client, instance, item_id, to_status, to_index, fp=None):
    return client.patch("/amik/cards/" + str(item_id) + "/position", data={
        "id": item_id, "to_status": to_status, "to_index": to_index,
        "fingerprint": fp if fp is not None else _fingerprint(client)})


# ── it writes ───────────────────────────────────────────────────────────

def test_a_move_lands_in_the_file(client, instance):
    _board(instance, ROWS)
    assert _move(client, instance, "zombie", "done", 0).status_code == 200
    row = _read(instance)["zombie"]
    assert row["status"] == "done" and row["rank"] == 1


def test_a_card_can_be_pulled_into_ready(client, instance):
    """`ready` holds no rows and must still accept a drop — it is the one
    column the owner fills by hand."""
    _board(instance, ROWS)
    assert _move(client, instance, "installer", "ready", 0).status_code == 200
    assert _read(instance)["installer"]["status"] == "ready"


def test_a_retired_status_can_no_longer_be_written(client, instance):
    """to_status comes from the UI, so the column list and the writer have
    to agree — or a drag could write `live` back into a board that has no
    such column."""
    _board(instance, ROWS)
    before = _read(instance)
    # `abandoned` is NOT in this list. It was a retired spelling until
    # 2026-09-17, when the rename of `wont_do` reused the word -- so a
    # status can come back, and a test asserting a name is dead has to
    # be re-read when one does.
    for gone in ("live", "parked", "in_progress", "retired", "wont_do"):
        assert _move(client, instance, "zombie", gone, 0).status_code == 400
    assert _read(instance) == before


def test_a_move_renumbers_the_column_it_left(client, instance):
    _board(instance, ROWS)
    _move(client, instance, "zombie", "done", 0)
    todo = sorted((r for r in _read(instance).values()
                   if r["status"] == "todo"), key=lambda r: r["rank"])
    assert [r["id"] for r in todo] == ["installer", "chat-labels"]
    assert [r["rank"] for r in todo] == [1, 2]


def test_the_response_carries_the_new_fingerprint(client, instance):
    _board(instance, ROWS)
    before = _fingerprint(client)
    body = _move(client, instance, "zombie", "done", 0, fp=before).json()
    assert body["fingerprint"] and body["fingerprint"] != before


def _first_card_in(body, status):
    """The first card id inside one column's markup. Inbox renders first,
    so 'the first card on the page' is not the same question."""
    col = body.split(f'data-status="{status}"', 1)[1].split("</section>", 1)[0]
    return col.split('data-id="', 1)[1].split('"', 1)[0]


def test_the_page_shows_the_new_order_after_a_move(client, instance):
    _board(instance, ROWS)
    assert _first_card_in(client.get("/amik").text, "todo") == "installer"
    _move(client, instance, "chat-labels", "todo", 0)
    assert _first_card_in(client.get("/amik").text, "todo") == "chat-labels"


# ── it refuses ──────────────────────────────────────────────────────────

def test_a_stale_fingerprint_is_refused(client, instance):
    _board(instance, ROWS)
    r = _move(client, instance, "zombie", "done", 0, fp="0/0")
    assert r.status_code == 409


def test_a_refused_move_writes_nothing(client, instance):
    _board(instance, ROWS)
    before = _read(instance)
    _move(client, instance, "zombie", "done", 0, fp="0/0")
    assert _read(instance) == before


def test_an_unknown_id_is_refused(client, instance):
    _board(instance, ROWS)
    assert _move(client, instance, "nope", "done", 0).status_code == 400


def test_an_unknown_status_is_refused(client, instance):
    """A drop target must be a column the board actually has, or a typo
    would invent a status and strand the item in a column nothing shows."""
    _board(instance, ROWS)
    assert _move(client, instance, "zombie", "waffle", 0).status_code == 400


def test_an_unknown_status_writes_nothing(client, instance):
    _board(instance, ROWS)
    before = _read(instance)
    _move(client, instance, "zombie", "waffle", 0)
    assert _read(instance) == before


def test_the_route_404s_without_an_amik_file(client):
    r = client.patch("/amik/cards/x/position", data={
        "to_status": "done", "to_index": 0, "fingerprint": "z"})
    assert r.status_code == 404


def test_a_cross_origin_write_is_refused_by_the_host_not_by_amik(client,
                                                                 instance):
    """`handle()` has no opinion about origins — it never sees a header.
    The guard belongs to whatever is serving: the face's middleware, or
    Amik's own server when it stands alone. Both now cover every mutating
    method, not just POST: the board's writes are PATCH and DELETE, and a
    POST-only guard would have let all of them past.
    """
    import inspect
    from amik.app import server
    guard = inspect.getsource(server._Handler._run)
    for verb in ("POST", "PATCH", "PUT", "DELETE"):
        assert verb in guard, verb
    assert "Forbidden" in guard


# ── creating from the UI ────────────────────────────────────────────────

def _add(client, instance, title, fp=None):
    return client.post("/amik/cards", data={
        "title": title,
        "fingerprint": fp if fp is not None else _fingerprint(client)})


def test_the_plus_button_creates_an_inbox_card(client, instance):
    _board(instance, ROWS)
    r = _add(client, instance, "Fix the thing")
    assert r.status_code == 200
    row = _read(instance)[r.json()["id"]]
    assert row["status"] == "inbox" and row["rank"] == 1
    assert row["planning"] is None and "kind" not in row


def test_a_new_card_appears_on_the_board(client, instance):
    _board(instance, ROWS)
    _add(client, instance, "Fix the thing")
    assert _first_card_in(client.get("/amik").text, "inbox") == "fix-the-thing"


def test_a_new_card_does_not_disturb_another_column(client, instance):
    _board(instance, ROWS)
    before = {k: v for k, v in _read(instance).items() if v["status"] == "todo"}
    _add(client, instance, "Fix the thing")
    after = {k: v for k, v in _read(instance).items() if v["status"] == "todo"}
    assert before == after


def test_an_empty_title_is_refused(client, instance):
    _board(instance, ROWS)
    before = _read(instance)
    assert _add(client, instance, "   ").status_code == 400
    assert _read(instance) == before


def test_a_stale_add_is_refused(client, instance):
    _board(instance, ROWS)
    before = _read(instance)
    assert _add(client, instance, "Fix", fp="0/0").status_code == 409
    assert _read(instance) == before


# ── editing from the modal ──────────────────────────────────────────────

def _edit(client, instance, item_id, fields, fp=None):
    data = dict(fields)
    data["fingerprint"] = fp if fp is not None else _fingerprint(client)
    return client.patch(f"/amik/cards/{item_id}", data=data)


def test_the_modal_saves_the_fields_it_owns(client, instance):
    _board(instance, ROWS)
    r = _edit(client, instance, "zombie", {
        "title": "Clear the zombie run", "body": "New prose.",
        "planning": "has-plan", "group": "engine"})
    assert r.status_code == 200
    row = _read(instance)["zombie"]
    assert row["title"] == "Clear the zombie run"
    assert "body" not in row, "prose goes to the card file, not the line"
    assert _card_prose(instance, "zombie") == "New prose."
    assert row["planning"] == "has-plan"
    assert row["group"] == "engine"


def test_a_retired_field_cannot_be_smuggled_back_in(client, instance):
    """`tag` and `unpark_when` are gone. The route names its editable
    fields in its signature rather than sweeping the form, so an old
    client posting either is not ignored-by-luck -- the key never reaches
    the writer at all, and nothing new appears on the row."""
    _board(instance, ROWS)
    before = _read(instance)["zombie"]
    r = _edit(client, instance, "zombie",
              {"tag": "brainstorm-needed", "unpark_when": "someday"})
    assert r.status_code == 200
    row = _read(instance)["zombie"]
    assert "tag" not in row and "unpark_when" not in row
    assert row["planning"] == before["planning"]


def test_a_save_stamps_the_row(client, instance):
    """The stamp is second-resolution, so comparing it to a stamp taken
    AFTER the save fails whenever the two land either side of a second
    boundary -- roughly one run in a thousand, which is the frequency
    that teaches a reader to re-run instead of read."""
    _board(instance, ROWS)
    before = amik_edit._stamp()
    _edit(client, instance, "zombie", {"title": "X", "body": "y"})
    assert _read(instance)["zombie"]["updated_at"] in (
        before, amik_edit._stamp())


def test_a_save_cannot_move_the_card(client, instance):
    """Status and rank belong to the drag. If the modal could post them,
    two writers would own one field."""
    _board(instance, ROWS)
    _edit(client, instance, "zombie", {"title": "X", "body": "y",
                                       "status": "done", "rank": "1"})
    row = _read(instance)["zombie"]
    assert row["status"] == "todo" and row["rank"] == 2


# ── the design-pass flag, through the real route ────────────────────────
# amik_edit.update_item is unit-tested directly, but nothing had ever
# posted this field through the actual form boundary -- where an empty
# value never arrives at all (a blank form field collapses to no field
# before Form(None) sees it), which is exactly why `off` exists as its
# own value rather than an empty string.

def test_on_sets_the_flag_through_the_route(client, instance):
    _board(instance, ROWS)
    _edit(client, instance, "zombie", {"requires_prototype": "on"})
    assert _read(instance)["zombie"]["requires_prototype"] is True


def test_off_clears_the_flag_through_the_route(client, instance):
    rows = [dict(r) for r in ROWS]
    for r in rows:
        if r["id"] == "zombie":
            r["requires_prototype"] = True
    _board(instance, rows)
    _edit(client, instance, "zombie", {"requires_prototype": "off"})
    assert "requires_prototype" not in _read(instance)["zombie"]


def test_omitting_the_field_leaves_it_untouched(client, instance):
    """The regression this guards: a save that never mentions the flag,
    because the modal's own box did not change, must not read as an
    implicit `off` -- a sentinel that defaulted the wrong way would
    silently clear it on every unrelated save."""
    rows = [dict(r) for r in ROWS]
    for r in rows:
        if r["id"] == "zombie":
            r["requires_prototype"] = True
    _board(instance, rows)
    _edit(client, instance, "zombie", {"title": "Renamed"})
    assert _read(instance)["zombie"]["requires_prototype"] is True


def test_an_unknown_rung_is_refused(client, instance):
    _board(instance, ROWS)
    before = _read(instance)
    assert _edit(client, instance, "zombie",
                 {"planning": "banana"}).status_code == 400
    assert _read(instance) == before


def test_a_stale_save_is_refused(client, instance):
    _board(instance, ROWS)
    before = _read(instance)
    assert _edit(client, instance, "zombie", {"title": "X"},
                 fp="0/0").status_code == 409
    assert _read(instance) == before


def test_editing_an_unknown_card_is_refused(client, instance):
    _board(instance, ROWS)
    assert _edit(client, instance, "nope", {"title": "X"}).status_code == 400


# ── clearing a rung or an area, through the route ───────────────────────
# A blank select posts an empty string, which a form library collapses to
# no field at all before the route ever sees it -- indistinguishable from
# a box nobody touched, and dropped. Nothing below can see that bug at the
# writer level, which is why it survived: these go through the real route.

def test_clearing_a_rung_through_the_route_clears_it(client, instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": "has-plan"}])
    _edit(client, instance, "c1", {"title": "A card", "planning": "none"})
    assert _read(instance)["c1"].get("planning") in (None, "")


def test_clearing_an_area_through_the_route_clears_it(client, instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "group": "face"}])
    _edit(client, instance, "c1", {"title": "A card", "group": "none"})
    assert _read(instance)["c1"].get("group") in (None, "")


def test_a_save_that_omits_a_field_leaves_it_alone(client, instance):
    """The regression this shape must not introduce: a sentinel that
    defaulted wrong would clear a field on every unrelated save."""
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": "has-plan",
                       "group": "face"}])
    _edit(client, instance, "c1", {"title": "Renamed"})
    row = _read(instance)["c1"]
    assert row["planning"] == "has-plan" and row["group"] == "face"


# ── deleting from the modal ─────────────────────────────────────────────

def test_a_delete_removes_the_row_from_the_file(client, instance):
    _board(instance, ROWS)
    assert _delete(client, instance, "zombie").status_code == 200
    assert "zombie" not in _read(instance)


def test_a_delete_renumbers_the_column_it_left(client, instance):
    _board(instance, ROWS)
    _delete(client, instance, "installer")
    todo = {i: r for i, r in _read(instance).items()
            if r["status"] == "todo"}
    assert sorted(r["rank"] for r in todo.values()) == [1, 2]


def test_a_delete_answers_with_a_fresh_fingerprint(client, instance):
    """The page reloads after a delete, but the fingerprint has to be
    honest in the response too -- a caller that did not reload must not be
    handed a stale one and told the board changed on disk by its own
    write."""
    _board(instance, ROWS)
    before = _fingerprint(client)
    data = _delete(client, instance, "zombie").json()
    assert data["fingerprint"] and data["fingerprint"] != before


def test_a_delete_against_a_stale_fingerprint_is_refused(client, instance):
    _board(instance, ROWS)
    before = _read(instance)
    r = _delete(client, instance, "zombie", fp="0/0")
    assert r.status_code == 409
    assert _read(instance) == before


def test_deleting_an_unknown_id_is_refused(client, instance):
    _board(instance, ROWS)
    before = _read(instance)
    assert _delete(client, instance, "nope").status_code == 400
    assert _read(instance) == before


def test_a_stale_parent_ref_does_not_block_a_delete(client, instance):
    """`parent` was retired with the reference panes' grouping. A row that
    still carries one by hand must not make its target undeletable."""
    _board(instance, ROWS + [{"id": "kid", "title": "A child",
                              "status": "todo", "rank": 9,
                              "planning": None, "parent": "zombie",
                              "body": "x"}])
    assert _delete(client, instance, "zombie").status_code == 200
    assert "zombie" not in _read(instance)


# ── the global quick-add's POST ─────────────────────────────────────────

def test_an_empty_fingerprint_means_do_not_check(client, instance):
    """The quick-add fires from pages that never rendered the board and so
    have none to quote. Sound for THIS verb only: the guard exists so a
    drag cannot reorder against a stale view, and a create reads the file
    fresh and appends at the top of inbox -- there is no prior state for
    it to clobber."""
    _board(instance, ROWS)
    r = client.post("/amik/cards", data={"title": "From another page",
                                          "fingerprint": ""})
    assert r.status_code == 200
    row = _read(instance)[r.json()["id"]]
    assert row["status"] == "inbox" and row["rank"] == 1


def test_a_wrong_fingerprint_is_still_refused(client, instance):
    """Empty means unchecked; WRONG still means stale. Loosening the one
    must not quietly loosen the other."""
    _board(instance, ROWS)
    before = _read(instance)
    r = client.post("/amik/cards", data={"title": "Nope",
                                          "fingerprint": "0/0"})
    assert r.status_code == 409
    assert _read(instance) == before


def test_the_quick_add_lands_above_the_owners_existing_inbox(client,
                                                             instance):
    """Top of Inbox, the same place the + puts it. An idea caught mid-task
    is the owner's own newest thought, not an agent's addition."""
    _board(instance, ROWS)
    r = client.post("/amik/cards", data={"title": "An idea", })
    assert r.status_code == 200
    inbox = sorted((x for x in _read(instance).values()
                    if x["status"] == "inbox"), key=lambda x: x["rank"])
    assert inbox[0]["id"] == r.json()["id"]
    assert [x["rank"] for x in inbox] == list(range(1, len(inbox) + 1))


# ── answers are spliced server-side, never in the browser ──────────────
# The box is an input. The body is submitted once, transformed once and
# written once, so the rule that finds a heading and replaces its body
# stays implemented in exactly one language.

CARD_WITH_QUESTIONS = """Some prose.

## Questions

### First question?

### Second question?
"""


def test_an_answer_is_written_beneath_its_heading(client, instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1", CARD_WITH_QUESTIONS)
    res = _edit(client, instance, "c1", {
        "body": CARD_WITH_QUESTIONS,
        "answers": json.dumps([{"heading": "First question?",
                                "text": "The answer."}])})
    assert res.status_code == 200, res.text
    prose = _card_prose(instance, "c1")
    assert "### First question?\n\nThe answer.\n" in prose
    assert "### Second question?" in prose


def test_the_rest_of_the_body_survives_an_answer(client, instance):
    """The body is submitted whole and transformed, so a prose edit made
    in the same save must not be lost to the splice, and vice versa."""
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1", CARD_WITH_QUESTIONS)
    edited = CARD_WITH_QUESTIONS.replace("Some prose.", "Edited prose.")
    _edit(client, instance, "c1", {
        "body": edited,
        "answers": json.dumps([{"heading": "First question?",
                                "text": "A."}])})
    prose = _card_prose(instance, "c1")
    assert prose.startswith("Edited prose.")
    assert "A." in prose


def test_two_answers_in_one_save_both_land(client, instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1", CARD_WITH_QUESTIONS)
    _edit(client, instance, "c1", {
        "body": CARD_WITH_QUESTIONS,
        "answers": json.dumps(
            [{"heading": "First question?", "text": "A."},
             {"heading": "Second question?", "text": "B."}])})
    prose = _card_prose(instance, "c1")
    assert "### First question?\n\nA.\n" in prose
    assert "### Second question?\n\nB.\n" in prose


def test_an_answer_to_a_missing_heading_is_refused(client, instance):
    """A heading the submitted body no longer carries means the owner
    answered something they deleted in the same edit, or the card moved
    under them. Telling them beats writing most of it."""
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1", CARD_WITH_QUESTIONS)
    res = _edit(client, instance, "c1", {
        "body": CARD_WITH_QUESTIONS,
        "answers": json.dumps([{"heading": "Never asked?", "text": "x"}])})
    assert res.status_code == 400
    assert _card_prose(instance, "c1") == CARD_WITH_QUESTIONS


def test_a_malformed_answers_payload_is_refused(client, instance):
    """It arrives as a string over a form field, so it is untrusted
    input and cannot be allowed to reach the writer half-parsed."""
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1", CARD_WITH_QUESTIONS)
    for payload in ("{not json", "{}", '[{"heading": 1}]', '["a string"]'):
        res = _edit(client, instance, "c1", {
            "body": CARD_WITH_QUESTIONS, "answers": payload})
        assert res.status_code == 400, payload
        assert _card_prose(instance, "c1") == CARD_WITH_QUESTIONS


def test_clearing_an_answer_empties_the_section(client, instance):
    """An answer can be withdrawn the same way it was given: the box sent
    with "", the section emptied, and the card reads as waiting again."""
    card = ("Some prose.\n\n## Questions\n\n### First question?\n\n"
            "The answer.\n")
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1", card)
    res = _edit(client, instance, "c1", {
        "body": card,
        "answers": json.dumps([{"heading": "First question?",
                                "text": ""}])})
    assert res.status_code == 200, res.text
    prose = _card_prose(instance, "c1")
    assert "The answer." not in prose
    assert "### First question?" in prose
    from amik.core import board as readers
    assert readers._card_questions(prose)[0]["answered"] is False


def test_a_save_with_no_answers_behaves_exactly_as_before(client, instance):
    """The field is optional, and a card with no questions must not pay
    for this feature existing."""
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1", "Just prose.\n")
    res = _edit(client, instance, "c1", {"body": "Changed prose.\n"})
    assert res.status_code == 200, res.text
    assert _card_prose(instance, "c1") == "Changed prose.\n"


# ── a prototype is served from disk, wearing the host's clothes ────────


def _prototype(root, card_id, html):
    import os
    path = os.path.join(str(root), "amik", "prototypes", card_id,
                        "index.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def _amik_toml(root, text):
    import os
    path = os.path.join(str(root), "amik", "amik.toml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


PROTO_TOML = ('verify = "pytest -q"\n\n[prototypes]\n'
              'assets = ["/static/themes.css", "/static/app.css"]\n')


def test_a_prototype_is_served(client, instance):
    _prototype(instance, "c1", "<html><head></head><body>Hi</body></html>")
    _amik_toml(instance, PROTO_TOML)
    res = client.get("/amik/cards/c1/prototype")
    assert res.status_code == 200
    assert "Hi" in res.text


def test_the_declared_assets_are_injected(client, instance):
    """A prototype should look like the app it is prototyping, and which
    stylesheet that is belongs to the project rather than to the file."""
    _prototype(instance, "c1", "<html><head></head><body>Hi</body></html>")
    _amik_toml(instance, PROTO_TOML)
    body = client.get("/amik/cards/c1/prototype").text
    assert '/static/app.css' in body
    assert '/static/themes.css' in body


def test_a_non_root_relative_asset_is_never_injected(client, instance):
    """The reader drops these before the route ever sees them, so this
    proves the drop end to end rather than only at the reader."""
    _prototype(instance, "c1", "<html><head></head><body>Hi</body></html>")
    _amik_toml(instance, 'verify = "pytest -q"\n\n[prototypes]\nassets = '
                        '["javascript:alert(1)", '
                        '"http://evil.example/x.css"]\n')
    body = client.get("/amik/cards/c1/prototype").text
    assert "javascript:" not in body
    assert "evil.example" not in body


def test_the_authored_markup_is_not_rewritten(client, instance):
    """Serving is not licence to rewrite a file the owner wrote — only
    the link tags are added."""
    html = "<html><head><title>Mine</title></head><body>Hi</body></html>"
    _prototype(instance, "c1", html)
    _amik_toml(instance, PROTO_TOML)
    body = client.get("/amik/cards/c1/prototype").text
    assert "<title>Mine</title>" in body
    assert "Hi" in body


def test_a_project_declaring_no_assets_still_serves(client, instance):
    _prototype(instance, "c1", "<html><head></head><body>Hi</body></html>")
    _amik_toml(instance, 'verify = "pytest -q"\n')
    assert client.get("/amik/cards/c1/prototype").status_code == 200


def test_a_missing_prototype_is_a_404(client, instance):
    _amik_toml(instance, PROTO_TOML)
    assert client.get("/amik/cards/nope/prototype").status_code == 404


def test_a_card_id_cannot_escape_the_prototypes_directory(client, instance):
    """The id arrives from a URL as well as from a hand-authored file, so
    it is untrusted twice over."""
    _amik_toml(instance, PROTO_TOML)
    import os
    outside = os.path.join(str(instance), "secret.html")
    with open(outside, "w") as f:
        f.write("SECRET")
    for bad in ("../../secret", "..%2f..%2fsecret", "a/../../secret"):
        res = client.get("/amik/cards/" + bad)
        assert res.status_code == 404, bad
        assert "SECRET" not in res.text


def test_a_single_segment_dotdot_is_refused_by_the_guard_itself(
        client, instance):
    """A raw `../` is caught by the router before it ever reaches this
    code — a single URL segment cannot carry a slash at all, so the
    three cases above never exercise the id guard. Percent-encoded dots
    (`%2e%2e`) DO arrive as one segment and reach the handler as a
    literal `..`, so this is the one input that is stopped by the guard
    and nothing else: a sibling file one directory up proves it, present
    to read if the guard were gone, absent from every real response."""
    _amik_toml(instance, PROTO_TOML)
    import os
    os.makedirs(os.path.join(str(instance), "amik", "prototypes"),
                exist_ok=True)
    with open(os.path.join(str(instance), "amik", "index.html"), "w") as f:
        f.write("ESCAPED")
    res = client.get("/amik/cards/%2e%2e/prototype")
    assert res.status_code == 404
    assert "ESCAPED" not in res.text
