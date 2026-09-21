"""Informed consent, two exits.

The buttons say what they do, so the body says what the dialog knows that
they do not: which fields moved. "status, outcome" says the agent did not
touch your prose. "body" says it did.
"""

import os

from tests.test_amik_page import _css, _js


def _shell():
    return open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "app", "templates", "_shell.html")).read()


def _conflict():
    src = _js("amik.js")
    return src[src.index("function conflict"):]


def test_the_field_diff_covers_the_prose_as_well_as_the_row():
    """`body` is the word that tells the owner the agent touched what
    they are typing into. A diff over the data attributes alone could
    never say it."""
    src = _js("amik.js")
    diff = src[src.index("function changedFields"):src.index("function standing")]
    assert ".akraw" in diff and "'body'" in diff
    assert ".akoutsrc" in diff and "'outcome'" in diff


def test_keep_editing_is_the_safe_default():
    """ESC resolves the cancel path, and nothing is written until Save is
    pressed -- whereas Reload destroys what was typed the instant it is.
    So Keep Editing is the cancel, and Reload takes the danger styling."""
    # The ARGUMENTS, not their order of appearance in the file: the
    # comment above the call names both labels, so an index comparison
    # over the whole function proves nothing about which slot each is in.
    assert "'Reload Card', 'Keep Editing'" in _conflict()


def test_the_confirm_is_the_one_that_destroys_something():
    """`ask` renders the confirm in the danger style and autofocuses the
    cancel, so which argument each label goes in IS the safety."""
    shell = _shell()
    assert 'id="askyes"' in shell and "danger" in shell
    assert "getElementById('askno').focus()" in shell


def test_it_asks_once_per_card():
    """Having consented to override, being asked again is nagging about a
    decision already made. A standing line replaces the second dialog."""
    fn = _conflict()
    assert "asked[id]" in fn
    assert "standing(true)" in fn


def test_the_consent_does_not_outlive_the_edit():
    src = _js("amik.js")
    close = src[src.index("dlg.addEventListener('close'"):]
    assert "asked = {}" in close
    assert "standing(false)" in close


def test_a_conflict_that_cannot_be_read_still_holds():
    """The fetch can fail -- the server may be the thing that changed
    underneath. The hold is already set by then, so the save is still
    refused; the standing line is what says so."""
    fn = _conflict()
    tail = fn[fn.index("}).catch"):]
    assert "standing(true)" in tail
