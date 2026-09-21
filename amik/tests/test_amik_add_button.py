"""The + on Inbox must not depend on which script loaded first.

It did, and it silently did nothing. `amik.js` attached its listener
behind `if (add && window.amikQuickAdd)`, but base.html includes the
quick-add partial — and its script — AFTER the page's own content block,
so `amik.js` runs first and that global is still undefined. The guard
reads as a null check and is really a load-order assertion: when it fails
there is no error and no warning, just a button that does nothing.

The Cmd/Ctrl+K chord kept working the whole time, because it registers
inside the file that defines the entry point. Same entry point, two ways
in, and only the one that never crossed a file boundary worked.

Resolving at CLICK time instead is order-independent: by the time anyone
clicks, every script on the page has run.
"""
import os
import re

FACE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
STATIC = os.path.join(FACE, "static")


def _js(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


def test_the_listener_is_not_gated_on_a_global_defined_elsewhere():
    """The exact shape of the bug: a load-time truthiness test on another
    file's global, standing between the button and its handler."""
    assert not re.search(r"if\s*\([^)]*&&\s*window\.amikQuickAdd\s*\)",
                         _js("amik.js"))


def test_the_entry_point_is_resolved_when_the_button_is_clicked():
    """Inside the handler, not beside it."""
    src = _js("amik.js")
    start = src.find("var add = document.querySelector('.addbtn')")
    assert start != -1
    block = src[start:start + 900]
    assert "addEventListener('click'" in block
    assert "window.amikQuickAdd" in block
    # the call has to be after the listener is attached, not a condition
    assert block.index("addEventListener('click'") < \
        block.index("window.amikQuickAdd")


def test_quickadd_still_owns_the_entry_point():
    """This button is another way in, not a second copy that can drift."""
    assert "window.amikQuickAdd = open;" in _js("quickadd.js")


def test_the_board_page_still_renders_exactly_one_add_button(instance, client):
    """Only Inbox carries it — a new thought always lands where a
    decision is owed, so every other column having one would be four
    invitations to break that rule."""
    from tests.test_amik_page import _board
    _board(instance, [{"id": "a", "title": "T", "status": "inbox",
                       "planning": None, "rank": 1,
                       "created_at": "2026-09-14",
                       "updated_at": "2026-09-14"}])
    html = client.get("/amik").text
    assert html.count('class="addbtn"') == 1
    assert 'aria-label="Add an item"' in html


def test_no_template_hardcodes_the_MOUNT_PREFIX():
    """Every URL a template builds goes through `url()` or `static()`,
    because the prefix is whatever the host mounted the board at and
    Amik cannot know it.

    This shipped broken: `_quickadd.html` asked for
    `/amik/static/quickadd.js`, which is correct only in the app Amik
    was extracted from. Served standalone the script 404s, the entry
    point it defines never exists, and the + button on Inbox does
    nothing -- silently, because a missing script logs a 404 nobody is
    watching rather than an error on the page.
    """
    import glob
    import os
    import re
    from conftest import PACKAGE
    for path in glob.glob(os.path.join(PACKAGE, "app", "templates", "*.html")):
        text = open(path, encoding="utf-8").read()
        # Inside a Jinja comment is where this rule is EXPLAINED, so the
        # comments come out before the file is searched.
        text = re.sub(r"\{#.*?#\}", "", text, flags=re.S)
        assert "/amik/" not in text, os.path.basename(path)
