"""Every component appears on a rendered board.

Amik ships no component gallery, and not to save weight. Every piece of
it — chips, cards, columns, the modal, the create button, the quick-add —
is on screen in normal use, so the stronger check is that a component
appears on a BOARD rather than somewhere a person may never visit. A
component that cannot be made to show up on one is a component Amik does
not need.

The cost of that, named: states rare in real data — an empty column, a
conflict, a card an agent has taken — have to be in the fixture or they
are not covered. That is a requirement on `scenarios.py`, and this is
what enforces it.
"""
import pytest

from amik.app.handle import handle
from amik.app import render

# Each entry is what to look for and the scenario that must produce it.
COMPONENTS = {
    # `akhasproto` is absent on purpose: it is derived from the
    # prototype DIRECTORY rather than the flag, so no fixture row can
    # produce it. Its own test below makes the folder.
    "akcol": None,                       # a column
    "akcard": None,                      # a card
    "akchips": None,                     # the chip row
    "addbtn": None,                      # create, on Inbox
    "akdlg": None,                       # the card modal
    "akquick": None,                     # the quick-add dialog
    "nodata": "ready_plain",             # an empty column's placeholder
    "akplan": "todo_needs_brainstorm",   # a rung
    "akblocking": "todo_needs_brainstorm",
    "akconflict": "conflict_ready_blocking",
    # The question chip marks a MISMATCH between a card's questions and
    # its column, so a blocked card with an open question does not carry
    # one — it is consistent. A To-Do card with an open question does.
    "akquestion": "conflict_question_column",
    "akdup": "duplicate_heading",
    "akgrp": "ready_plain",
    "akbranch": "done_with_branch",
    "akworking": "agent_working",
    "akspin": "agent_working",
    "akqsrc": "blocked_unanswered",
    "akoutsrc": "done_plain",
    "akftoggle": None,
    "akftlink": None,
    # View mode: the strip a card reads as, its prose rendered, and the
    # one control that leaves it.
    "akvchips": None,
    "akstatus": None,
    "akbodysrc": "done_plain",
    "akhandling": "halt_in_review",
    "akpencil": None,
    "time-ago": "done_plain",
    "callout": None,
    "akbrand": None,                     # the top bar's mark
    "akmark": None,                      # the mark's glyph
    "akhost": None,                      # the host project's name
    "akarmbtn": None,                    # the gate on the loop
}


def _declare(root):
    """A board that DECLARES a project, because some components need one.

    "A card an agent has taken" is named in this file's own list of rare
    states that have to be in the fixture or they are not covered. A
    board with no verify and no agent command has no agent to have taken
    anything, and its cards say so by carrying no spinner -- correctly.
    So the surface these tests assert against has to be a board an agent
    could work, which is a fact about the PROJECT and not about the rows
    `scenarios.py` lays down.
    """
    import os
    os.makedirs(os.path.join(root, "amik"), exist_ok=True)
    path = os.path.join(root, "amik", "amik.toml")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write('verify = "true"\narmed = true\n'
                    '[agent]\ncommand = "an-agent"\n')
    return root


def _page(root):
    status, _, body = handle("GET", "/", root=_declare(root))
    assert status == 200
    return body.decode()


def _surface(root):
    """The page AND every card's data block.

    A card's details are FETCHED when its modal opens rather than
    pre-rendered into the page, so the rendered board is two routes now.
    A component that lives in the block is still on screen in ordinary
    use — it arrives a round trip later — and that is what this file is
    about. Asserting it against the page alone would have quietly dropped
    six components from the vocabulary.
    """
    from amik.core import board as readers
    out = [_page(root)]
    data = readers.amik(root)
    for column in (data["data"]["columns"] if data["ok"] else []):
        for card in column["cards"]:
            status, _, body = handle("GET", "/cards/" + card["id"],
                                     root=root)
            assert status == 200, card["id"]
            out.append(body.decode())
    return "\n".join(out)


# Three kinds of thing a FULL board cannot show, and none is a gap in the
# vocabulary. `nodata` is an empty column's placeholder, and every
# scenario together leaves no column empty. `akgit` is derived from the
# repository rather than the board, so a fixture directory that is not one
# renders nothing. `akarmbtn` is derived from `amik.toml` for the same
# reason — a board is not a project, and a scenario writes only the board.
# Each is covered by its own test, here or in test_amik_top_bar.py.
FULL_BOARD_CANNOT_SHOW = ("nodata", "akgit", "akarmbtn")


def test_every_component_appears_on_a_rendered_board(scenario):
    page = _surface(scenario())
    missing = sorted(n for n in COMPONENTS
                     if n not in page and n not in FULL_BOARD_CANNOT_SHOW)
    assert not missing, (
        "components absent from a board built from every scenario — either "
        "the component is gone or the fixture stopped producing its "
        "state: {}".format(missing))


@pytest.mark.parametrize("component,needs", sorted(
    (c, s) for c, s in COMPONENTS.items() if s))
def test_the_fixture_that_produces_it_really_does(scenario, component, needs):
    """The other half. The test above passes if ANY scenario produces a
    component, which would let the named one rot while something else
    carried it — and then the named scenario could be deleted without a
    failure."""
    assert component in _surface(scenario(needs)), (component, needs)


def test_a_prototype_chip_needs_the_directory_not_the_flag(scenario):
    """`has_prototype` is derived from the directory existing, so the
    board cannot disagree with the disk. The fixture sets the FLAG, which
    is why this chip needs its folder made."""
    import os
    root = scenario("prototype_card")
    assert "akhasproto" not in _page(root)
    os.makedirs(os.path.join(root, "amik", "prototypes",
                             "try-a-compact-card-layout"))
    assert "akhasproto" in _page(root)


def test_a_wrapped_bullet_stays_one_bullet():
    """This prose is hand-written at about 72 columns, so most items run
    to a second line. Each line used to be its own block: the list closed
    at the wrap and the rest of the sentence became a paragraph under it,
    which put half a sentence outside the bullet it belonged to. Card
    bodies are rendered now, so a board's commonest shape has to survive
    the renderer."""
    from amik.app import markdown_render as md
    html = md.markdown("Lead line.\n\n- **One.** carried\n  onto a second"
                       "\n- **Two.** also\n  carried\n\nAfter.")
    assert html.count("<ul>") == 1
    assert "<li><b>One.</b> carried onto a second</li>" in html
    assert "<li><b>Two.</b> also carried</li>" in html
    assert html.startswith("<p>Lead line.</p>")
    assert html.endswith("<p>After.</p>")


def test_a_lead_line_before_bullets_is_still_a_paragraph():
    """The shape the run-detection was written for: a bold lead and then
    items. A continuation only continues something — it must not swallow
    the line above the list."""
    from amik.app import markdown_render as md
    html = md.markdown("**Three things.**\n- one\n- two")
    assert html == "<p><b>Three things.</b></p>\n<ul><li>one</li>" \
                   "<li>two</li></ul>"


def test_the_environment_is_strict_about_undefined():
    """The whole case for using a template engine here rests on this one
    setting. Jinja's default `Undefined` renders empty, which makes a
    typo indistinguishable from a field a card legitimately lacks — the
    failure a component vocabulary exists to prevent. A default that
    silently reverts would take the argument with it."""
    from jinja2 import StrictUndefined
    env = render.environment()
    assert env.undefined is StrictUndefined
    assert env.autoescape is True


def test_a_missing_key_raises_rather_than_rendering_blank():
    """Stated as behaviour, not configuration."""
    from jinja2 import UndefinedError
    env = render.environment()
    with pytest.raises(UndefinedError):
        env.from_string("{{ nope.at_all }}").render()


def test_card_prose_is_escaped_not_injected(scenario, instance):
    from amik.core import edit
    from amik.tests.conftest import write_board
    write_board(instance, [{"id": "x", "title": "<script>alert(1)</script>",
                            "status": "inbox", "planning": None, "rank": 1,
                            "created_at": "2026-01-01T00:00:00",
                            "updated_at": "2026-01-01T00:00:00"}])
    page = _page(instance)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_the_page_javascript_actually_parses(scenario):
    """The stronger claim, and the one that would have caught it: take
    what the browser is handed and check it is a program. Balanced tags
    are necessary and not sufficient."""
    import re
    import subprocess
    page = _page(scenario("ready_plain"))
    blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
                        page, re.S)
    assert blocks, "the board served no inline script at all"
    for i, code in enumerate(blocks):
        out = subprocess.run(["node", "--check", "-"], input=code,
                             text=True, capture_output=True)
        assert out.returncode == 0, (i, out.stderr[:400])
