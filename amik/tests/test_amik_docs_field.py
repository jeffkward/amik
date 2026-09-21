"""`docs` names the document a `has-plan` rung is claiming.

The conflict chip reads this field: a card saying it has a plan and
naming no document prints "plan not named", because the rung's whole
value is that a build can open what it points at.

The field was on rows for months with no writer. `EDITABLE` did not carry
it, so the only way to satisfy the chip was to hand-edit the line and go
around the door -- a gate on a field nothing could write.
"""

import json

import pytest

from amik.core import board, edit


def _row(root, card_id):
    for line in open(f"{root}/amik/board.jsonl"):
        if line.strip():
            row = json.loads(line)
            if row.get("id") == card_id:
                return row
    raise AssertionError("no such row")


def test_a_list_is_stored_as_a_list(scenario):
    root = scenario("ready_plain")
    assert edit.update(root, "rename-the-export-button", {"docs": ["docs/a.md", "docs/b.md"]})["ok"]
    assert _row(root, "rename-the-export-button")["docs"] == ["docs/a.md", "docs/b.md"]


def test_newline_separated_text_becomes_a_list(scenario):
    """What a textarea posts."""
    root = scenario("ready_plain")
    edit.update(root, "rename-the-export-button", {"docs": "docs/a.md\ndocs/b.md\n"})
    assert _row(root, "rename-the-export-button")["docs"] == ["docs/a.md", "docs/b.md"]


def test_blank_entries_are_dropped(scenario):
    root = scenario("ready_plain")
    edit.update(root, "rename-the-export-button", {"docs": "docs/a.md\n\n  \n"})
    assert _row(root, "rename-the-export-button")["docs"] == ["docs/a.md"]


def test_emptying_it_removes_the_key(scenario):
    """The readers test emptiness, and a `[]` on a row read by eye says
    less than no key at all."""
    root = scenario("ready_plain")
    edit.update(root, "rename-the-export-button", {"docs": ["docs/a.md"]})
    edit.update(root, "rename-the-export-button", {"docs": ""})
    assert "docs" not in _row(root, "rename-the-export-button")


def test_naming_a_document_clears_the_conflict_chip(scenario):
    """The whole point, end to end."""
    root = scenario("ready_plain")
    edit.update(root, "rename-the-export-button", {"planning": "has-plan"})

    def chip():
        for column in board.amik(root)["data"]["columns"]:
            for card in column["cards"]:
                if card["id"] == "rename-the-export-button":
                    return card["conflict_label"]
        raise AssertionError("card vanished")

    assert chip() == "plan not named"
    edit.update(root, "rename-the-export-button", {"docs": ["docs/plan.md"]})
    assert chip() == ""
