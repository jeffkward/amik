"""Three branches, and the third is the one that matters.

An open card the agent has not touched is nobody's conflict. An open card
it HAS touched, that the owner has not typed into, can simply be refilled.
An open card it has touched that the owner IS editing is a real conflict,
and the fingerprint must be HELD stale so the save is refused -- deferring
the repaint without deferring the fingerprint would let the save through
and silently discard the agent's write.
"""

from tests.test_amik_page import _js


def _rule():
    src = _js("amik.js")
    return src[src.index("function akOnChanged"):]


def test_an_unaffected_card_does_not_disturb_the_modal():
    """The commonest case by far: the loop works a card nobody has open."""
    rule = _rule()
    assert "ids.indexOf(id) === -1" in rule
    assert rule.index("ids.indexOf(id) === -1") < rule.index("dirty()")


def test_a_clean_open_card_is_refilled():
    rule = _rule()
    assert "dirty()" in rule
    assert "akCard" in rule
    assert "fill(fresh)" in rule


def test_a_dirty_open_card_holds_the_fingerprint():
    """The staleness is deliberate, and the next reader has to know that
    or they will 'fix' it."""
    rule = _rule()
    assert "window.akHeld = true" in rule
    assert "conflict(id)" in rule
    # and it changes nothing on screen: the owner's text stays put
    held = rule[rule.index("if (dirty())"):rule.index("var keep")]
    assert "fill(" not in held


def test_the_selected_tab_survives_a_refill():
    """View state belongs to the person looking. Jumping to Details
    because an agent wrote an outcome reads as the page losing your
    place."""
    rule = _rule()
    assert "selectedTab()" in rule
    assert "restoreTab(keep)" in rule
    src = _js("amik.js")
    assert 'aria-selected="true"' in src


def test_an_open_editor_survives_a_refill():
    """`fill` puts every card back into view mode, which is right on an
    open and wrong on a refill: the pencil had been clicked, and nothing
    was typed or this would be a conflict."""
    rule = _rule()
    assert "wasEditing" in rule
    assert "startEditing()" in rule


def test_filling_a_card_and_opening_one_are_separate():
    """`showModal()` on a dialog that is already open throws, so the
    refill cannot go through `open`."""
    src = _js("amik.js")
    fill = src[src.index("function fill(b) {"):src.index("function open(b) {")]
    assert "showModal" not in fill
    assert "focus()" not in fill
    assert "showModal" in src[src.index("function open(b) {"):]


def test_a_held_save_sends_no_fingerprint():
    """`fingerprint=None` already means 'do not check' -- it is how the
    loop writes. So override needs no door change and no force flag."""
    src = _js("amik.js")
    save = src[src.index("function save()"):src.index("saveBtn.addEventListener")]
    assert "if (!window.akHeld)" in save
    assert "body.set('fingerprint'" in save


def test_the_hold_does_not_outlive_the_card():
    """Every way out of the modal clears it, via the dialog's own close
    event rather than a line at each of the four places it closes."""
    src = _js("amik.js")
    close = src[src.index("dlg.addEventListener('close'"):]
    assert "window.akHeld = false" in close
