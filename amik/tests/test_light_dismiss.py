"""Clicking outside a modal closes it — the card modal, the quick-add and
the confirm alike.

The gesture itself is not testable here, so these pin the parts that were
paid for: the rect comparison (a click on the dialog's own padding reports
the same event target as one on the backdrop), the press-and-release gate
(a selection dragged out of the body editor releases on the backdrop), and
the `cancel` dispatch — without which the card modal's discard prompt
would guard ESC and not this.

The last test is the enumeration law: one delegated listener covers every
dialog on the page, so what breaks this is a dialog rendered on a page the
shell is not included in.
"""
import os

from conftest import PACKAGE

TEMPLATES = os.path.join(PACKAGE, "app", "templates")


def _read(name):
    return open(os.path.join(TEMPLATES, name), encoding="utf-8").read()


def _dismiss_block():
    """The light-dismiss IIFE out of the shell — its CODE, with the
    comment above it dropped. A match against the prose explaining the
    mechanism would not prove the mechanism is there."""
    shell = _read("_shell.html")
    marked = shell.index("click outside a modal to close it")
    start = shell.index("(function () {", marked)
    end = shell.index("})();", start)
    return shell[start:end]


def test_the_handler_is_delegated_at_the_document():
    block = _dismiss_block()
    # POINTER, not mouse. A touch on a backdrop is not reliably given the
    # synthesized mousedown/click a mouse gets — those are dispatched
    # only for targets the platform treats as interactive, and a
    # backdrop is not one. The gesture worked with a mouse and did
    # nothing under a thumb.
    assert "document.addEventListener('pointerdown'" in block
    assert "document.addEventListener('pointerup'" in block
    assert "'mousedown'" not in block and "'click'" not in block
    assert "dialog[open]" in block


def test_the_backdrop_is_told_from_the_padding_by_the_rect():
    block = _dismiss_block()
    assert "getBoundingClientRect()" in block
    assert "clientX" in block and "clientY" in block
    assert "e.target === dlg" not in block


def test_press_and_release_must_both_land_outside():
    block = _dismiss_block()
    assert "pressedOut" in block
    assert "if (!dlg || !pressedOut) return;" in block
    assert "if (!outside(dlg, e)) return;" in block


def test_it_closes_through_cancel_so_the_discard_prompt_still_fires():
    """The card modal answers ESC by asking about unsaved edits and
    preventing the default close. This gesture goes through that same
    handler, so the close has to be conditional on the dispatch
    surviving — a bare close() here would drop an edit silently."""
    block = _dismiss_block()
    assert "new Event('cancel', {cancelable: true})" in block
    assert "if (dlg.dispatchEvent" in block
    assert "dlg.close();" in block


def test_the_card_modal_still_guards_unsaved_edits_on_cancel():
    """The other half of the pair: the guard this gesture relies on."""
    script = open(os.path.join(PACKAGE, "app", "static", "amik.js"),
                  encoding="utf-8").read()
    assert "dlg.addEventListener('cancel'" in script
    assert "e.preventDefault(); leave();" in script


def test_every_dialog_lives_on_the_page_the_shell_is_on():
    """The shell is included by board.html, which is the only page. A
    dialog in a template board.html does not reach would be
    undismissable — widen this list only after checking it does."""
    found = set()
    for name in sorted(os.listdir(TEMPLATES)):
        if not name.endswith(".html"):
            continue
        if "<dialog" in _read(name):
            found.add(name)
    assert found == {"_shell.html", "_quickadd.html", "board.html"}
    board = _read("board.html")
    assert '{% include "_shell.html" %}' in board
    assert '{% include "_quickadd.html" %}' in board
