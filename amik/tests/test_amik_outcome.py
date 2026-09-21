"""What a card produced, carried on the card.

The prose an agent writes after a build — what landed, what it cost, what
was left — went to the terminal, which dies with the session, and to a
commit message, which is scoped to one diff. Neither is the card.

The argument that decides it: a card can close with NO COMMIT AT ALL.
Two of four cards worked in one batch did — one already built and closed
after its claim was verified, one producing a design pass and no code.
For those the log has nothing to say.
"""
import json
import os

import pytest

from amik.core import edit as amik_edit
from amik.core import board as readers


def _instance(tmp_path, prose="Some prose.\n", **row):
    os.makedirs(tmp_path / "amik" / "cards", exist_ok=True)
    base = {"id": "a", "title": "A card", "status": "doing", "planning": None,
            "rank": 1, "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00"}
    base.update(row)
    (tmp_path / "amik" / "board.jsonl").write_text(json.dumps(base) + "\n")
    (tmp_path / "amik" / "cards" / "a.md").write_text(prose)
    return str(tmp_path)


def _prose(root):
    return open(os.path.join(root, "amik", "cards", "a.md")).read()


# ── the reader ─────────────────────────────────────────────────────────


def test_the_outcome_is_the_prose_under_its_heading():
    assert readers._card_outcome(
        "Body.\n\n## Outcome\n\nLanded in abc123.\n") == "Landed in abc123."


def test_a_later_heading_closes_the_section():
    got = readers._card_outcome(
        "## Outcome\n\nLanded.\n\n## Questions\n\n### Why?\n")
    assert got == "Landed."


def test_a_fenced_heading_is_content_not_structure():
    """The same boundary rule the questions reader uses. A model writing
    an outcome emits fenced code constantly."""
    got = readers._card_outcome(
        "## Outcome\n\nRan:\n\n```\n## Outcome\n```\n\nDone.\n")
    assert "Done." in got and got.count("Done.") == 1


def test_a_card_with_no_outcome_reads_empty_rather_than_raising():
    assert readers._card_outcome("Just a body.") == ""
    assert readers._card_outcome(None) == ""


def test_whitespace_is_not_an_outcome():
    assert readers.amik_agent_may_close({"id": "a", "outcome": "  \n "}) is False


# ── the door ───────────────────────────────────────────────────────────


def test_recording_an_outcome_creates_the_section(tmp_path):
    root = _instance(tmp_path)
    assert amik_edit.record_outcome(root, "a", "Landed in abc123.")["ok"]
    assert "## Outcome" in _prose(root)
    # Equality would pin the attribution line's exact wording into a test
    # about the section being created. The entry is what this asserts;
    # who wrote it is tested where that lives.
    assert readers._card_outcome(_prose(root)).startswith("Landed in abc123.")


def test_a_second_outcome_appends_and_does_not_replace(tmp_path):
    """A card worked twice has two outcomes and the second does not
    supersede the first — the same law a ruling carries."""
    root = _instance(tmp_path)
    amik_edit.record_outcome(root, "a", "Built the prototype.")
    amik_edit.record_outcome(root, "a", "Built it for real after the pick.")
    got = readers._card_outcome(_prose(root))
    assert "Built the prototype." in got
    assert "Built it for real after the pick." in got
    assert "---" in got            # and they read as two, not one


def test_an_empty_outcome_is_refused(tmp_path):
    """The verb that satisfies the gate must not be satisfiable by a write
    that said nothing."""
    root = _instance(tmp_path)
    res = amik_edit.record_outcome(root, "a", "   ")
    assert res["ok"] is False
    assert "empty" in res["reason"]
    assert "## Outcome" not in _prose(root)


def test_an_unknown_card_is_refused(tmp_path):
    root = _instance(tmp_path)
    assert amik_edit.record_outcome(root, "nope", "x")["ok"] is False


def test_an_outcome_the_reader_could_not_read_back_is_refused(tmp_path):
    """An unclosed fence swallows everything after it, so an appended
    section lands inside the swallowed region and reports success on a
    write nothing can see."""
    root = _instance(tmp_path, prose="Body.\n\n```\nnever closed\n")
    res = amik_edit.record_outcome(root, "a", "Landed.")
    assert res["ok"] is False
    assert "unreadable" in res["reason"]


def test_recording_stamps_the_row(tmp_path):
    root = _instance(tmp_path)
    amik_edit.record_outcome(root, "a", "Landed.")
    row = json.loads(open(os.path.join(root, "amik", "board.jsonl")).read())
    assert row["updated_at"] != "2026-01-01T00:00:00"


def test_a_refused_outcome_moves_neither_the_row_nor_the_file(tmp_path):
    root = _instance(tmp_path)
    before_row = open(os.path.join(root, "amik", "board.jsonl")).read()
    before_prose = _prose(root)
    amik_edit.record_outcome(root, "a", "")
    assert open(os.path.join(root, "amik", "board.jsonl")).read() == before_row
    assert _prose(root) == before_prose


# ── the tab ────────────────────────────────────────────────────────────


@pytest.fixture()
def client(tmp_path):
    from conftest import Client
    return Client(_instance(
        tmp_path, prose="Body.\n\n## Outcome\n\nLanded in **abc123**.\n"))


def test_the_outcome_pane_is_read_only(client):
    """The whole prose is already editable in the body editor on Details.
    A second editable view of one slice of it is a second writer for the
    same text."""
    body = client.get("/amik").text
    pane = body.split('id="akoutcome"', 1)[1].split(">", 1)[0]
    assert "textarea" not in pane
    dlg = body.split('id="akdlg"', 1)[1].split("</dialog>", 1)[0]
    outcome_block = dlg.split('id="akoutcome"', 1)[1].split("</div>", 1)[0]
    assert "<input" not in outcome_block
