"""Every card branches, so a toggle asking for it says nothing.

It also removed a real failure. The toggle is one tap among several in a
modal opened mostly to re-rank from, and its consequence -- a whole
card's work landing on another card's branch, and 34 commits off the
trunk -- surfaced two days later.

`branch` stays. It records where a card's work went, and Amik writes it
now; `branch_requested` asked a question with one answer.
"""

import json
import os

from amik.core import board, edit


def _rows(root):
    return [json.loads(l) for l in open(os.path.join(root, "amik",
                                                     "board.jsonl"))
            if l.strip()]


def test_the_field_is_not_editable():
    assert "branch_requested" not in edit.EDITABLE


def test_writing_it_raises(scenario):
    root = scenario("ready_plain")
    res = edit.update(root, "rename-the-export-button",
                      {"branch_requested": "on"})
    assert res["ok"] is False
    assert "branch_requested" in res["reason"], res["reason"]


def test_a_row_still_carrying_it_renders(scenario):
    """The refusal is on the write path alone."""
    root = scenario("ready_plain")
    path = os.path.join(root, "amik", "board.jsonl")
    rows = _rows(root)
    rows[0]["branch_requested"] = True
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert board.amik(root)["ok"] is True

