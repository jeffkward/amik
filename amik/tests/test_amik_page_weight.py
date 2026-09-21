"""The board page ships tiles, not every card's prose.

Measured before this changed: 768 KB total, of which the board region --
columns, tiles and chips -- was 60 KB and the 166 hidden card blocks were
703 KB. The page shipped every card's full text so that opening one card
would need no round trip.

This is the guard most likely to regress silently: re-adding the
pre-render would leave every other test in the suite green.
"""

from amik.app.handle import handle

# The scenario board's Done card, which carries prose and an outcome. Its
# first sentence appears nowhere else on the board, so it is the sentinel.
PROSE_CARD = "fix-the-timezone-offset"
PROSE = "The offset was applied twice on import."


def _page(root):
    return handle("GET", "/", None, b"", root=root, base="")[2].decode()


def test_the_page_does_not_carry_card_data_blocks(scenario):
    assert 'class="akdata"' not in _page(scenario())


def test_the_page_does_not_carry_card_prose(scenario):
    """A card's body is the bulk of it, and the tile shows only a title."""
    page = _page(scenario("done_plain"))
    assert 'data-id="' + PROSE_CARD + '"' in page      # the tile is there
    assert PROSE not in page                           # the body is not


def test_the_card_route_still_carries_it(scenario):
    html = handle("GET", "/cards/" + PROSE_CARD, None, b"",
                  root=scenario("done_plain"), base="")[2].decode()
    assert PROSE in html


def test_no_positional_card_addresses_remain(scenario):
    """`akd-<n>` and `data-card` addressed a card by its position in file
    order. Every one of the positional addresses this work started with
    is now a landmark or gone; leaving a dead one in the markup invites
    the next reader to use it."""
    root = scenario("done_plain")
    page = _page(root)
    card = handle("GET", "/cards/" + PROSE_CARD, None, b"",
                  root=root, base="")[2].decode()
    for markup in (page, card):
        assert "akd-" not in markup, markup[:400]
        assert "data-card=" not in markup, markup[:400]


def test_the_page_does_not_grow_with_the_prose_on_it(instance):
    """A ratchet, not a benchmark. Sixty cards carrying 4 KB of prose each
    is a quarter of a megabyte the pre-render would have shipped; the page
    that ships tiles does not move with it at all.

    Bounded rather than compared against a second render, because the
    regression is re-adding the pre-render -- and a comparison against a
    page built the same way would move with it."""
    from tests.test_amik_page import _board
    body = ("Prose nobody is looking at. " * 150) + "\n"
    _board(instance, [{"id": "c%d" % i, "title": "Card %d" % i,
                       "status": "todo", "rank": i, "planning": None,
                       "body": body} for i in range(60)])
    page = handle("GET", "/", None, b"", root=instance, base="")[2]
    assert len(body) * 60 > 200_000, "the fixture has to be big to bind"
    assert len(page) < 100_000, len(page)
