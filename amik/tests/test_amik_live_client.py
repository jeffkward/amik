"""The reconciler's rules, asserted where they live.

These are source-level assertions on purpose: there is no DOM here, and
the alternative -- a headless browser -- is a dependency this project does
not have and does not want. Each one names the rule it guards, so a
reader who breaks one is told what they broke rather than which numbered
paragraph they broke.
"""

from tests.test_amik_page import _js


def _live():
    src = _js("amik.js")
    return src[src.index("window.akLive"):]


def test_it_subscribes_to_the_feed():
    src = _js("amik.js")
    assert "EventSource" in src
    assert "'/events'" in src or '"/events"' in src


def test_it_reconciles_cards_and_never_replaces_a_column():
    """Keeping .akcol alive is what preserves its scroll offset and its
    collapsed class -- the state is not re-derived after a swap, it is
    simply never destroyed."""
    live = _live()
    assert "akcard" in live
    assert ".akcol" in live
    # A column is looked up and read from. It is never itself replaced --
    # doing so would discard its scroll offset and its collapsed class,
    # which is the whole regression this rule exists to prevent.
    for banned in ("col.replaceWith", "mine.replaceWith",
                   "mine.outerHTML", "col.outerHTML", "mine.innerHTML"):
        assert banned not in live, banned


def test_a_card_that_did_not_change_keeps_its_node():
    """Keyed on data-id. Cloning every tile would work and is rejected: it
    destroys node identity, which is what makes focus, hover and any
    transition survive a repaint."""
    live = _live()
    assert '.akcard[data-id="' in live
    reconcile = live[live.index("function reconcile"):]
    assert "cloneNode" in reconcile          # only for a card that is NEW
    assert reconcile.index("querySelector('.akcard[data-id=\"") \
        < reconcile.index("card.cloneNode(true)")


def test_derived_state_comes_from_the_server():
    """The chip's meaning, the column's count and the empty-column
    invitation are the reader's rules. The client PLACES them; it never
    computes one."""
    live = _live()
    assert "fromCount.textContent" in live
    assert ".akchips" in live
    assert ".akempty" in live


def test_it_defers_while_a_gesture_is_in_flight():
    live = _live()
    assert "function busy()" in live
    assert "dialog[open]" in live             # an open dialog is one
    assert "akcard.dragging" in live          # so is a drag
    assert "dataset.writing" in live          # so is a drag's own write


def test_it_keeps_only_the_newest_deferred_render():
    """Three queued renders are not three updates to apply in order; they
    are two stale ones and a current one. Owing a refresh rather than
    holding markup is what makes that true without a queue."""
    live = _live()
    assert "pending" in live
    assert "pending = true" in live
    assert "function flush()" in live


def test_a_deferred_render_is_flushed_when_the_gesture_ends():
    live = _live()
    assert "akgestureend" in live
    assert "'close'" in live, "every dialog's own close event"
    src = _js("amik.js")
    assert src.count("new CustomEvent('akgestureend')") == 2, \
        "a drag that commits nothing, and one whose write lands"


def test_the_changed_ids_go_out_even_while_a_repaint_is_deferred():
    """The open-card rule is the listener that most needs to hear about a
    change the board is deliberately not painting."""
    live = _live()
    dispatch = live.index("akchanged")
    assert dispatch < live.index("payload.fingerprint === board.dataset")


def test_the_fingerprint_follows_the_repaint():
    """The card this whole change exists for. The page could not refresh
    its own fingerprint before, so the first foreign write shut a door
    that stayed shut until a reload."""
    assert "board.dataset.fingerprint =" in _live()


def test_the_top_bar_is_repainted_too(client, instance):
    """It carries the arm/pause pill, which is what someone watches while
    the loop runs -- the one thing whose staleness would be actively
    misleading rather than merely wrong."""
    from tests.test_amik_page import _board, ROWS
    _board(instance, ROWS)
    assert 'id="aktopbar"' in client.get("/amik").text
    assert "'#aktopbar'" in _live()


def test_the_arm_pill_survives_its_own_repaint():
    """Its listener was bound to the button. Repainting the bar it sits in
    would have replaced that node and left the pill silently dead, which
    no test of the repaint itself would have caught."""
    src = _js("amik.js")
    arm = src[src.index("var note = document.getElementById('akarmnote')"):]
    assert "closest('#akarmbtn')" in arm
    assert "btn.addEventListener" not in arm


def test_a_disconnected_board_says_so_without_blanking(client, instance):
    """The failure that matters is the FETCH, not the socket: EventSource
    reconnects on its own, and a re-fetch that returns 500 must leave the
    last good render alone."""
    from tests.test_amik_page import _board, ROWS
    _board(instance, ROWS)
    assert 'id="akoffline"' in client.get("/amik").text
    live = _live()
    assert "akoffline" in live
    fetch = live[live.index("function refresh()"):]
    assert "offline(true)" in fetch
    assert "innerHTML" not in fetch, "a failed fetch clears nothing"
