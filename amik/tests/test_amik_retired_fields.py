"""A retired field must not come back.

`dates` is the case that motivated this: an array of ISO dates the
board inherited from the document it was migrated out of, carried on 67
rows, read by nothing and maintained by nothing. A field with no writer cannot be refused at the
door the way a retired rung is — nothing writes it, so there is no call
to raise on. The live board is the only place the old shape can reappear,
which makes a guard over the board the whole ratchet.

The list is meant to grow. Retiring a field means migrating the rows and
adding its name here in the same pass, so the next hand edit or restored
backup that reintroduces it reddens instead of quietly repopulating a
column nothing renders.
"""
import json
import os

from conftest import INSTANCE as ROOT

RETIRED = (
    # The columns the board was migrated in with, retired once it
    # became a kanban.
    "priority", "rank_from", "status_from", "decided_on", "ruling",
    "curated", "src_title", "src_line", "section", "section_heading",
    "title_amended", "authored", "source", "codes",
    # Retired with the nine-key row: `tag` became `planning`, `kind` and
    # its reference rows went, and the rest folded into card bodies.
    "tag", "kind", "unpark_when", "unpark_when_source", "related",
    "parent",
    # Unread history the body already carries better.
    "dates",
)


def test_the_live_board_carries_no_retired_field():
    path = os.path.join(ROOT, "amik", "board.jsonl")
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            for field in RETIRED:
                assert field not in row, f"line {n}: {field}"


def test_no_retired_field_is_writable_through_the_door():
    """`EDITABLE` is the door's own enumeration, and a retired name
    surviving in it is how a field comes back one save at a time."""
    from amik.core import edit as amik_edit
    assert not set(amik_edit.EDITABLE) & set(RETIRED)
