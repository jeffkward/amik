"""A card is a resource. Its data block is fetched, not shipped 166 times."""

from amik.app.handle import handle

# The scenario board's Ready card. Ids are hand-authored on this board and
# a scenario's name is not its id, so the id is named here once.
READY = "rename-the-export-button"


def _get(root, path):
    return handle("GET", path, None, b"", root=root, base="")


def test_a_card_answers_with_its_own_data_block(scenario):
    root = scenario("ready_plain")
    status, headers, body = _get(root, "/cards/" + READY)
    assert status == 200, body
    html = body.decode()
    assert 'class="akdata"' in html
    assert 'data-id="' + READY + '"' in html
    assert "text/html" in headers["Content-Type"]


def test_it_carries_one_card_and_not_the_board(scenario):
    """The whole point: fetching one card must not drag the others."""
    root = scenario("ready_plain", "todo_plain", "done_plain")
    html = _get(root, "/cards/" + READY)[2].decode()
    assert html.count('class="akdata"') == 1


def test_an_unknown_card_is_a_404(scenario):
    assert _get(scenario("ready_plain"), "/cards/no-such-card")[0] == 404


def test_the_route_is_listed():
    """ROUTES is walked by two suite-wide tests; an unlisted route is one
    those gates never see."""
    from amik.app.handle import ROUTES
    assert ("GET", "/cards/{id}") in ROUTES
