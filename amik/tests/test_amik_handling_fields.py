"""The handling toggles: whether the queue stops, and whether a design
pass comes first.

Stored the way `requires_prototype` is — a real boolean, REMOVED when
false. Absent means no, and a `false` on every one of 174 rows is noise
in a file read by eye.

`branch_requested` was the third until 2026-09-17. Every card branches
now, so a toggle asking for it had one answer.
"""
import json

from amik.core import edit as amik_edit

TEXT = ('{"id": "a", "title": "T", "status": "ready", "planning": null, '
        '"rank": 1, "created_at": "2026-09-14", "updated_at": "2026-09-14"}')


def _row(text):
    return json.loads(text.strip())


def test_halt_is_stored_as_a_boolean():
    out, _ = amik_edit.update_item(TEXT, "a", {"halt": "on"})
    assert _row(out)["halt"] is True


def test_halt_off_removes_the_key():
    on, _ = amik_edit.update_item(TEXT, "a", {"halt": "on"})
    off, _ = amik_edit.update_item(on, "a", {"halt": "off"})
    assert "halt" not in _row(off)


def test_requires_prototype_is_stored_the_same_way():
    out, _ = amik_edit.update_item(TEXT, "a", {"requires_prototype": "on"})
    assert _row(out)["requires_prototype"] is True


def test_the_two_are_independent():
    """An earlier draft derived one from the other. Both combinations
    are meaningful and neither is a contradiction."""
    out, _ = amik_edit.update_item(
        TEXT, "a", {"halt": "on", "requires_prototype": "off"})
    row = _row(out)
    assert row["halt"] is True and "requires_prototype" not in row


def test_both_are_editable():
    assert "halt" in amik_edit.EDITABLE
    assert "requires_prototype" in amik_edit.EDITABLE


def test_the_retired_one_is_not():
    assert "branch_requested" not in amik_edit.EDITABLE
