"""`handle()` — the whole public surface, exercised as HTTP.

No server and no host: four strings in, three out. That is the point of
the seam, and testing it this way is what proves a host needs nothing
Amik-shaped to embed it.
"""
import json
import urllib.parse

from amik.app.handle import handle


def _form(**kw):
    return urllib.parse.urlencode(kw).encode("utf-8")


def _get(root, path="/", base=""):
    return handle("GET", path, root=root, base=base)


def test_the_board_renders(scenario):
    root = scenario("ready_plain", "doing_plain", "done_plain")
    status, headers, body = _get(root)
    assert status == 200
    assert "text/html" in headers["Content-Type"]
    page = body.decode()
    assert "Rename the export button" in page
    assert "Split the settings page" in page


def test_updating_a_card_hands_back_its_chips(scenario):
    """Derived state the page cannot recompute — the waiting count, the
    conflict — comes back from the same reader that drew it."""
    root = scenario("ready_plain")
    status, _, body = handle(
        "PATCH", "/cards/rename-the-export-button",
        body=_form(title="Rename it properly", group="ui"), root=root)
    assert status == 200
    assert "chips" in json.loads(body)


def test_position_is_its_own_resource(scenario):
    """`move` and `update` are separate writers — status and rank belong
    to the drag and nothing else — so position is a nested resource
    rather than a field on the card."""
    root = scenario("ready_plain")
    status, _, _ = handle(
        "PATCH", "/cards/rename-the-export-button/position",
        body=_form(to_status="doing", to_index="0"), root=root)
    assert status == 200
    page = _get(root)[2].decode()
    doing = page.split('ak-doing', 1)[1]
    assert "Rename the export button" in doing


def test_a_stale_write_is_a_409_not_a_400(scenario):
    """Stale is not an error in the machinery — the file moved on, and
    the page has to catch up before writing again."""
    root = scenario("ready_plain")
    status, _, body = handle(
        "PATCH", "/cards/rename-the-export-button",
        body=_form(title="x", fingerprint="0/0"), root=root)
    assert status == 409


def _card(root, card_id):
    """One card's data block. The page ships tiles, so a card's prose is
    only ever on its own route."""
    status, _, body = handle("GET", "/cards/" + card_id, root=root)
    assert status == 200
    return body.decode()


def test_answers_without_a_body_are_refused(scenario):
    """They are spliced INTO prose; with none there is nothing to splice
    into, and a save that guessed would write over what it never read."""
    root = scenario("blocked_unanswered")
    status, _, body = handle(
        "PATCH", "/cards/pick-a-migration-tool",
        body=_form(answers=json.dumps([{"heading": "x", "text": "y"}])),
        root=root)
    assert status == 400
    assert "body" in json.loads(body)["detail"]


# ── answering the last question unblocks the card ─────────────────────


def _status(root, card_id):
    from amik.core import board
    for column in board.amik(root)["data"]["columns"]:
        for card in column["cards"]:
            if card["id"] == card_id:
                return card["status"]
    return None


def _answer(root, card_id, prose, heading, text):
    return handle("PATCH", "/cards/" + card_id,
                  body=_form(body=prose,
                             answers=json.dumps([{"heading": heading,
                                                  "text": text}])),
                  root=root)


_BLOCKED = "## Questions\n\n### Which migration tool?\n"
_HALF = ("## Questions\n\n### Redis or Postgres?\n\nPostgres — one less\n"
         "thing to run.\n\n### Who gets paged when it backs up?\n")


def test_the_last_answer_moves_a_blocked_card_back_to_ready(scenario):
    """The owner answering is the pull — the drag back to Ready was
    always the second half of the same gesture, and a card left in
    Blocked with nothing waiting on it is a contradiction."""
    root = scenario("blocked_unanswered", "ready_plain")
    assert _status(root, "pick-a-migration-tool") == "blocked"
    status, _, _ = _answer(root, "pick-a-migration-tool", _BLOCKED,
                           "Which migration tool?", "The thin one.")
    assert status == 200
    assert _status(root, "pick-a-migration-tool") == "ready"


def test_it_lands_at_the_bottom_of_ready(scenario):
    """Where the modal's own status dropdown lands a card. The top would
    re-prioritise a queue nobody asked it to touch."""
    from amik.core import board
    root = scenario("blocked_unanswered", "ready_plain")
    _answer(root, "pick-a-migration-tool", _BLOCKED,
            "Which migration tool?", "The thin one.")
    ready = next(c["cards"] for c in board.amik(root)["data"]["columns"]
                 if c["status"] == "ready")
    assert [c["id"] for c in ready] == ["rename-the-export-button",
                                        "pick-a-migration-tool"]


def test_answering_one_of_two_questions_unblocks_nothing(scenario):
    root = scenario("blocked_half_answered")
    status, _, _ = _answer(root, "choose-a-queue-backend", _HALF,
                           "Redis or Postgres?", "Postgres, still.")
    assert status == 200
    assert _status(root, "choose-a-queue-backend") == "blocked"


def test_the_fingerprint_handed_back_is_the_one_after_the_move(scenario):
    """The page writes it straight back onto the board, and the next
    write quotes it. One that predates the move is refused as stale."""
    root = scenario("blocked_unanswered")
    _, _, body = _answer(root, "pick-a-migration-tool", _BLOCKED,
                         "Which migration tool?", "The thin one.")
    from amik.core import board
    assert json.loads(body)["fingerprint"] == board.amik_fingerprint(root)


def test_a_card_in_another_column_is_not_moved(scenario):
    """Only Blocked. Answering a question on a Todo card says nothing
    about whether the owner wants it worked — `ready` is a pull."""
    root = scenario("conflict_question_column")
    status, _, _ = _answer(root, "tidy-the-error-copy",
                           "## Questions\n\n### Which tone?\n",
                           "Which tone?", "Plain.")
    assert status == 200
    assert _status(root, "tidy-the-error-copy") == "todo"


def test_a_save_carrying_no_answers_leaves_a_blocked_card_alone(scenario):
    """A blocked card can carry an answered question already — answered
    once and dragged back by hand, or never dragged at all. Retitling it
    is not a second answer."""
    root = scenario("blocked_unanswered")
    _answer(root, "pick-a-migration-tool", _BLOCKED,
            "Which migration tool?", "The thin one.")
    handle("PATCH", "/cards/pick-a-migration-tool/position",
           body=_form(to_status="blocked", to_index="0"), root=root)
    assert _status(root, "pick-a-migration-tool") == "blocked"
    status, _, _ = handle("PATCH", "/cards/pick-a-migration-tool",
                          body=_form(title="Pick a migration tool, then"),
                          root=root)
    assert status == 200
    assert _status(root, "pick-a-migration-tool") == "blocked"


# ── the routes are resource-named ─────────────────────────────────────


def test_the_old_verb_in_path_routes_are_gone(scenario):
    root = scenario("ready_plain")
    for method, path in (("POST", "/amik/move"), ("POST", "/amik/add"),
                         ("POST", "/cards/rename-the-export-button/edit")):
        status, _, _ = handle(method, path, body=_form(), root=root)
        assert status == 404, path


def test_a_mount_prefix_moves_every_route(scenario):
    """Embedded, a host hands over the path it received. Amik strips its
    own prefix and builds every URL back with it, so one setting moves
    the lot."""
    root = scenario("ready_plain")
    status, _, body = handle("GET", "/amik", root=root, base="/amik")
    assert status == 200
    page = body.decode()
    assert 'data-base="/amik"' in page
    assert '/amik/static/amik.css' in page
    status, _, _ = handle("PATCH", "/amik/cards/rename-the-export-button",
                          body=_form(title="x"), root=root, base="/amik")
    assert status == 200


def test_static_files_are_served_and_cannot_escape_the_folder(empty_board):
    status, headers, body = _get(empty_board, "/static/amik.css")
    assert status == 200 and b"--accent" in body
    for bad in ("/static/../core/edit.py", "/static/..%2fcore/edit.py",
                "/static/"):
        assert _get(empty_board, bad)[0] == 404, bad


def test_a_prototype_is_served_when_the_project_declares_itself(project):
    import os
    d = os.path.join(project, "amik", "prototypes", "a-card")
    os.makedirs(d)
    with open(os.path.join(d, "index.html"), "w") as f:
        f.write("<html><head></head><body>proto</body></html>")
    status, _, body = _get(project, "/cards/a-card/prototype")
    assert status == 200 and b"proto" in body


def test_a_prototype_needs_a_project_declaration(empty_board):
    """The whole of Amik's prototype surface is gated on the project
    having said it is agent-worked at all."""
    import os
    d = os.path.join(empty_board, "amik", "prototypes", "a-card")
    os.makedirs(d)
    with open(os.path.join(d, "index.html"), "w") as f:
        f.write("<html></html>")
    assert _get(empty_board, "/cards/a-card/prototype")[0] == 404
