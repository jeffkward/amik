"""`wont_do` becomes `abandoned`, and `closed_as` goes.

Renaming the column made `closed_as: abandoned` the column said twice,
and `retired` -- measured and disproven -- is a considered rejection with
evidence rather than abandonment, so it never sat under either name. One
field, one meaning.

Verified before the field was dropped rather than after: all three
`retired` rows already state their evidence in their card prose, so
nothing carrying a guarantee is being deleted. That is the law the
ladder migration paid for -- you cannot remove a state that holds a
guarantee without moving the guarantee first.
"""

import json
import os

from amik.core import board, edit


def _rows(root):
    return [json.loads(l) for l in open(os.path.join(root, "amik",
                                                     "board.jsonl"))
            if l.strip()]


def _rewrite(root, rows):
    with open(os.path.join(root, "amik", "board.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_abandoned_is_a_column():
    names = [c[0] for c in board.AMIK_COLUMNS]
    assert "abandoned" in names
    assert "wont_do" not in names


def test_abandoned_counts_as_closed():
    assert "abandoned" in board.AMIK_CLOSED
    assert "wont_do" not in board.AMIK_CLOSED


def test_closed_as_is_not_editable():
    assert "closed_as" not in edit.EDITABLE


def test_moving_to_the_old_status_raises(scenario):
    root = scenario("ready_plain")
    res = edit.move(root, "rename-the-export-button", "wont_do", 0)
    assert res["ok"] is False
    assert "wont_do" in res["reason"], res["reason"]
    assert "abandoned" in res["reason"], "say what it became"


def test_writing_closed_as_raises(scenario):
    root = scenario("ready_plain")
    res = edit.update(root, "rename-the-export-button",
                      {"closed_as": "retired"})
    assert res["ok"] is False
    assert "closed_as" in res["reason"], res["reason"]


def test_moving_to_abandoned_works(scenario):
    root = scenario("ready_plain")
    assert edit.move(root, "rename-the-export-button", "abandoned", 0)["ok"]
    assert _rows(root)[0]["status"] == "abandoned"


def test_a_row_still_carrying_either_STILL_RENDERS(scenario):
    """The refusal is on the WRITE path alone. A board mid-migration has
    to render, or there is no face to migrate it from."""
    root = scenario("ready_plain")
    rows = _rows(root)
    rows[0]["status"] = "wont_do"
    rows[0]["closed_as"] = "abandoned"
    _rewrite(root, rows)
    out = board.amik(root)
    assert out["ok"] is True, out
    seen = [c["status"] for col in out["data"]["columns"]
            for c in col["cards"]]
    assert "wont_do" in seen, "an unmigrated row must still appear"


def test_the_live_board_carries_neither():
    """The migration guard, against the real board rather than a
    fixture. This is the one that fails if the data sweep is skipped."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    for row in _rows(root):
        assert row.get("status") != "wont_do", row["id"]
        assert "closed_as" not in row, row["id"]
