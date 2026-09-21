"""A question can carry its own context, and the context is not an answer.

A question had two slots — the `###` heading and everything beneath it —
so an asker who wrote anything to help the owner decide put it in the box
the owner types into AND marked the question answered. Measured on a real
card: 1,530 characters of the asker's own analysis gave `unanswered: 0`
and no waiting chip.

Ruled: a contiguous blockquote directly under the heading is the asker's
context; the first line that is neither blank nor quoted begins the
answer, and everything after it stays the answer. Reader and writer share
one boundary rule — a save that disagreed with the render would splice
over the context the page had just shown.
"""
from amik.core import edit as amik_edit
from amik.core import markdown as amik_markdown
from amik.core import board as readers


def _q(prose, i=0):
    return readers._card_questions(prose)[i]


CTX = """## Questions

### Which way should this go?

> Option A is cheap and reversible.
> Option B is thorough and is not.
"""


# ── the boundary rule ───────────────────────────────────────────────────

def test_context_alone_is_not_an_answer():
    """The bug this card exists for."""
    q = _q(CTX)
    assert q["answered"] is False
    assert q["answer"] == ""
    assert "Option A is cheap" in q["context"]


def test_the_first_unquoted_line_begins_the_answer():
    q = _q(CTX + "\nGo with A.\n")
    assert q["answered"] is True
    assert q["answer"] == "Go with A."
    assert "Option B" in q["context"]


def test_a_quote_inside_the_answer_stays_in_the_answer():
    """Context is the LEADING run only. Once the answer starts it cannot
    be reclassified, or an owner quoting something mid-answer would
    silently lose it to the preamble."""
    q = _q(CTX + "\nGo with A.\n\n> as you said, cheap and reversible\n")
    assert "as you said" in q["answer"]
    assert "as you said" not in q["context"]


def test_a_question_with_no_quote_has_no_context():
    q = _q("## Questions\n\n### Plain?\n\nJust an answer.\n")
    assert q["context"] == ""
    assert q["answer"] == "Just an answer."


def test_an_answer_opening_with_a_quote_reads_as_context_and_HOLDS():
    """The convention's known edge, and it fails in the safe direction:
    the question reads unanswered, so the queue keeps holding the card
    rather than taking one nobody actually answered."""
    q = _q("## Questions\n\n### Plain?\n\n> quoting you back\n")
    assert q["answered"] is False


def test_blank_lines_before_the_quote_do_not_break_it():
    assert _q("## Questions\n\n### Q?\n\n\n> ctx\n")["context"] == "> ctx"


def test_the_span_helper_is_shared_not_reimplemented():
    """Reader and writer must agree. One function, imported by both."""
    assert amik_markdown.context_span(["", "> a", "> b", "", "x"]) == 3
    assert amik_markdown.context_span(["x", "> a"]) == 0
    assert amik_markdown.context_span([]) == 0


# ── the writer keeps it ─────────────────────────────────────────────────

def test_answering_does_not_eat_the_context():
    """The save path splices positionally. If it started at the heading
    the answer would overwrite the very text that justified it."""
    out = amik_edit.replace_section_body(CTX, "Which way should this go?",
                                         "Go with A.")
    assert "Option A is cheap" in out
    assert "Go with A." in out
    assert _q(out)["answer"] == "Go with A."


def test_answering_twice_replaces_only_the_answer():
    once = amik_edit.replace_section_body(CTX, "Which way should this go?",
                                          "Go with A.")
    twice = amik_edit.replace_section_body(once, "Which way should this go?",
                                           "Changed my mind: B.")
    assert "Option A is cheap" in twice
    assert "Go with A." not in twice
    assert _q(twice)["answer"] == "Changed my mind: B."


# ── the door writes it ──────────────────────────────────────────────────

def _card(root, cid="c1"):
    import os
    os.makedirs(os.path.join(root, "amik", "cards"), exist_ok=True)
    with open(os.path.join(root, "amik", "board.jsonl"), "w") as f:
        f.write('{"id": "c1", "title": "T", "status": "ready", '
                '"planning": null, "rank": 1, "created_at": "2026-09-14", '
                '"updated_at": "2026-09-14"}\n')
    with open(os.path.join(root, "amik", "cards", cid + ".md"), "w") as f:
        f.write("Some prose.\n")
    return os.path.join(root, "amik", "cards", cid + ".md")


def test_ask_writes_context_as_a_blockquote(instance):
    p = _card(instance)
    assert amik_edit.ask(instance, "c1", "Which way?",
                         context="A is cheap.\nB is thorough.")["ok"]
    prose = open(p).read()
    assert "> A is cheap." in prose
    assert "> B is thorough." in prose


def test_a_question_asked_with_context_is_still_unanswered(instance):
    """The whole point: the asker may explain without answering."""
    _card(instance)
    amik_edit.ask(instance, "c1", "Which way?", context="A or B.")
    q = _q(open(f"{instance}/amik/cards/c1.md").read())
    assert q["answered"] is False
    assert q["context"] == "> A or B."


def test_a_held_card_with_context_is_still_skipped(instance):
    """End to end — the queue must keep declining it."""
    _card(instance)
    amik_edit.ask(instance, "c1", "Which way?", context="A or B.")
    out = readers.amik_queue(instance)["data"]
    assert out["take"] is None
    assert out["skipped"][0]["id"] == "c1"


def test_ask_without_context_is_unchanged(instance):
    _card(instance)
    amik_edit.ask(instance, "c1", "Which way?")
    prose = open(f"{instance}/amik/cards/c1.md").read()
    assert ">" not in prose
    assert _q(prose)["context"] == ""
