"""Surgical edits to amik/board.jsonl.

The board is hand-authored and git-tracked, so a drag must rewrite only
the lines whose rank or status actually changed and leave every other
byte alone. That is possible because every line round-trips exactly
through json.dumps(obj, ensure_ascii=False) — asserted here, since the
whole design rests on it.
"""
import json

import pytest

from amik.core import edit as amik_edit


def _line(id_, status, rank, **extra):
    row = {"id": id_, "title": id_.title(), "status": status,
           "rank": rank, "body": "prose about " + id_}
    row.update(extra)
    return json.dumps(row, ensure_ascii=False)


TEXT = "\n".join([
    _line("a", "todo", 1),
    _line("b", "todo", 2),
    _line("c", "todo", 3),
    _line("x", "done", 1),
    _line("y", "done", 2),
]) + "\n"


def _rows(text):
    return {json.loads(l)["id"]: json.loads(l)
            for l in text.split("\n") if l.strip()}


def _order(text, status):
    rows = [r for r in _rows(text).values() if r["status"] == status]
    return [r["id"] for r in sorted(rows, key=lambda r: r["rank"])]


# ── the premise the design rests on ─────────────────────────────────────

def test_every_line_round_trips_byte_identically():
    for line in TEXT.split("\n"):
        if line.strip():
            assert json.dumps(json.loads(line), ensure_ascii=False) == line


# ── reordering inside one column ────────────────────────────────────────

def test_moving_down_inside_a_column_renumbers_it():
    out = amik_edit.move_item(TEXT, "a", "todo", 2)
    assert _order(out, "todo") == ["b", "c", "a"]
    assert [_rows(out)[i]["rank"] for i in ("b", "c", "a")] == [1, 2, 3]


def test_moving_up_inside_a_column_renumbers_it():
    out = amik_edit.move_item(TEXT, "c", "todo", 0)
    assert _order(out, "todo") == ["c", "a", "b"]


def test_a_move_inside_a_column_leaves_the_other_column_alone():
    out = amik_edit.move_item(TEXT, "a", "todo", 2)
    before, after = _rows(TEXT), _rows(out)
    assert before["x"] == after["x"] and before["y"] == after["y"]


def test_a_same_status_move_writes_no_provenance_at_all():
    """Re-pins a test that watched status_from survive a reorder. The
    field is gone; the invariant it protected — a reorder records nothing
    about the item, only its position — is asserted directly."""
    before = _rows(TEXT)["a"]
    out = amik_edit.move_item(TEXT, "a", "todo", 2)
    after = _rows(out)["a"]
    assert set(after) == set(before)
    assert {k: v for k, v in after.items() if k != "rank"} == \
           {k: v for k, v in before.items() if k != "rank"}


# ── moving between columns ──────────────────────────────────────────────

def test_moving_to_another_column_sets_the_status():
    out = amik_edit.move_item(TEXT, "b", "done", 1)
    assert _rows(out)["b"]["status"] == "done"
    assert _order(out, "done") == ["x", "b", "y"]


def test_moving_to_another_column_closes_the_gap_behind_it():
    out = amik_edit.move_item(TEXT, "b", "done", 1)
    assert _order(out, "todo") == ["a", "c"]
    assert [_rows(out)[i]["rank"] for i in ("a", "c")] == [1, 2]


# ── provenance ──────────────────────────────────────────────────────────

def test_reordering_inside_a_column_does_not_restamp_the_row():
    """Triage is not an edit. If a re-prioritising pass stamped every card
    it slid past, updated_at would say the whole board was worked on."""
    out = amik_edit.move_item(TEXT, "a", "todo", 2)
    assert "updated_at" not in _rows(out)["a"]
    assert "decided_on" not in _rows(out)["a"]


def test_reordering_leaves_an_existing_stamp_alone():
    text = "\n".join([
        _line("a", "todo", 1, updated_at="2026-08-09"),
        _line("b", "todo", 2, updated_at="2026-08-09"),
    ]) + "\n"
    out = amik_edit.move_item(text, "a", "todo", 1)
    assert _rows(out)["a"]["updated_at"] == "2026-08-09"


def test_a_row_that_only_shifted_is_not_stamped():
    """b and c were renumbered by a's move, not edited. Stamping them
    would turn the field into noise."""
    out = amik_edit.move_item(TEXT, "a", "todo", 2)
    assert "updated_at" not in _rows(out)["b"]
    assert "updated_at" not in _rows(out)["c"]


def test_a_cross_column_move_stamps_the_row():
    """Re-pins a test that also asserted status_from and decided_on. Both
    fields are gone: one was a spent migration marker, the other held two
    triage days across the whole board. The invariant they shared -- a
    column change is recorded on the row that moved -- is what survives."""
    out = amik_edit.move_item(TEXT, "b", "done", 0)
    row = _rows(out)["b"]
    assert row["updated_at"] == amik_edit._stamp()
    assert "status_from" not in row and "decided_on" not in row


def test_the_stamp_carries_a_time_not_just_a_day():
    """The modal shows "Updated 3m", and minutes cannot be recovered from
    a date. Rows written before this carry bare dates, which the age
    filter still parses -- they just read coarser."""
    stamp = amik_edit._stamp()
    assert "T" in stamp and stamp.count(":") == 2
    import datetime
    datetime.datetime.fromisoformat(stamp)          # parses, or this raises


def test_a_move_between_columns_restamps_only_the_row_that_moved():
    out = amik_edit.move_item(TEXT, "b", "done", 0)
    assert "updated_at" not in _rows(out)["a"]
    assert "updated_at" not in _rows(out)["c"]


# ── the file itself ─────────────────────────────────────────────────────

def test_untouched_lines_are_byte_identical():
    out = amik_edit.move_item(TEXT, "a", "todo", 2)
    before, after = TEXT.split("\n"), out.split("\n")
    assert len(before) == len(after)
    assert before[3] == after[3] and before[4] == after[4]   # the done rows


def test_a_rewritten_line_keeps_its_key_order():
    """The keys the row already had stay in the author's order. A field
    the writer adds (updated_at on a row that lacked one) appends rather
    than reshuffling — which is what keeps a diff readable."""
    out = amik_edit.move_item(TEXT, "a", "todo", 2)
    line = next(l for l in out.split("\n") if l.strip()
                and json.loads(l)["id"] == "a")
    before = list(json.loads(TEXT.split("\n")[0]).keys())
    after = list(json.loads(line).keys())
    assert after[:len(before)] == before


def test_a_row_that_already_has_the_field_keeps_its_shape_exactly():
    """The real board carries created_at/updated_at on every row, so a
    move updates in place and the key order is untouched."""
    text = "\n".join([
        _line("a", "todo", 1, created_at="2026-08-09", updated_at="2026-08-09"),
        _line("b", "todo", 2, created_at="2026-08-09", updated_at="2026-08-09"),
    ]) + "\n"
    out = amik_edit.move_item(text, "a", "todo", 1)
    line = next(l for l in out.split("\n") if l.strip()
                and json.loads(l)["id"] == "a")
    assert list(json.loads(line).keys()) == list(
        json.loads(text.split("\n")[0]).keys())


def test_line_count_and_trailing_newline_survive():
    out = amik_edit.move_item(TEXT, "c", "done", 0)
    assert out.endswith("\n") and not out.endswith("\n\n")
    assert len(out.split("\n")) == len(TEXT.split("\n"))


def test_a_line_that_is_not_json_is_preserved_verbatim():
    text = TEXT + "not json at all\n"
    out = amik_edit.move_item(text, "a", "todo", 2)
    assert "not json at all" in out.split("\n")


def test_blank_lines_are_preserved():
    text = TEXT.replace('\n{"id": "x"', '\n\n{"id": "x"')
    out = amik_edit.move_item(text, "a", "todo", 2)
    assert "" in out.split("\n")[:-1]


# ── refusals ────────────────────────────────────────────────────────────

def test_an_unknown_id_is_refused():
    with pytest.raises(ValueError):
        amik_edit.move_item(TEXT, "nope", "todo", 0)


def test_an_empty_target_status_is_refused():
    with pytest.raises(ValueError):
        amik_edit.move_item(TEXT, "a", "", 0)


def test_an_index_past_the_end_lands_last():
    out = amik_edit.move_item(TEXT, "a", "todo", 99)
    assert _order(out, "todo") == ["b", "c", "a"]


def test_a_negative_index_lands_first():
    out = amik_edit.move_item(TEXT, "c", "todo", -5)
    assert _order(out, "todo") == ["c", "a", "b"]


def test_moving_into_an_empty_column_gives_it_rank_one():
    out = amik_edit.move_item(TEXT, "a", "parked", 0)
    assert _rows(out)["a"]["rank"] == 1
    assert _rows(out)["a"]["status"] == "parked"


def test_a_row_with_no_rank_still_orders_and_is_renumbered():
    text = TEXT + _line("z", "todo", 0) .replace('"rank": 0, ', '') + "\n"
    out = amik_edit.move_item(text, "z", "todo", 0)
    assert _order(out, "todo") == ["z", "a", "b", "c"]


# ── creating a row ──────────────────────────────────────────────────────

def test_a_new_row_lands_at_the_top_of_inbox():
    """The owner's own newest thought is not a queue-jump. An AGENT adds
    at the bottom; this verb is the + button."""
    text = "\n".join([_line("a", "inbox", 1), _line("b", "inbox", 2)]) + "\n"
    out, new_id = amik_edit.create_item(text, "Fix the thing")
    assert _order(out, "inbox") == [new_id, "a", "b"]
    assert _rows(out)[new_id]["rank"] == 1


def test_a_new_row_carries_the_shape_the_board_expects():
    out, new_id = amik_edit.create_item(TEXT, "Fix the thing")
    row = _rows(out)[new_id]
    assert row["title"] == "Fix the thing"
    assert row["status"] == "inbox"
    assert row["planning"] is None
    assert "body" not in row            # prose lives in amik/cards/<id>.md
    assert row["created_at"] == row["updated_at"] == amik_edit._stamp()
    assert "kind" not in row            # retired with the reference panes


def test_a_new_row_gets_a_slug_from_its_title():
    out, new_id = amik_edit.create_item(TEXT, "Fix the Thing, Please!")
    assert new_id == "fix-the-thing-please"


def test_a_colliding_slug_is_suffixed_not_reused():
    """`id` is referenced by `parent`, so two rows sharing one would
    silently repoint a reference."""
    out, first = amik_edit.create_item(TEXT, "Fix the thing")
    out, second = amik_edit.create_item(out, "Fix the thing")
    assert first != second
    assert len({r["id"] for r in _rows(out).values()}) == len(_rows(out))


def test_a_title_that_slugs_to_nothing_still_gets_an_id():
    out, new_id = amik_edit.create_item(TEXT, "!!!")
    assert new_id and _rows(out)[new_id]["title"] == "!!!"


def test_an_empty_title_is_refused():
    for bad in ("", "   ", None):
        with pytest.raises(ValueError):
            amik_edit.create_item(TEXT, bad)


def test_creating_leaves_every_other_column_byte_identical():
    text = "\n".join([_line("a", "inbox", 1), _line("x", "done", 1)]) + "\n"
    out, _ = amik_edit.create_item(text, "New")
    assert out.split("\n")[1] == text.split("\n")[1]


def test_a_new_row_appends_a_line_and_keeps_the_trailing_newline():
    out, _ = amik_edit.create_item(TEXT, "New")
    assert len(out.split("\n")) == len(TEXT.split("\n")) + 1
    assert out.endswith("\n") and not out.endswith("\n\n")


# ── editing a row ───────────────────────────────────────────────────────

def test_editing_writes_the_fields_it_was_given():
    out, prose = amik_edit.update_item(TEXT, "a", {
        "title": "A better title", "planning": "has-plan",
        "group": "face", "body": "New prose."})
    row = _rows(out)["a"]
    assert row["title"] == "A better title"
    assert row["planning"] == "has-plan"
    assert row["group"] == "face"
    assert "body" not in row, "prose goes to the card file, not the line"
    assert prose == "New prose.", "and comes back for the caller to write"


def test_editing_stamps_the_row():
    out, _ = amik_edit.update_item(TEXT, "a", {"title": "X"})
    assert _rows(out)["a"]["updated_at"] == amik_edit._stamp()


def test_a_body_only_edit_stamps_the_row_too():
    """Load-bearing for the board-only stale-write guard.

    The fingerprint hashes `board.jsonl` and nothing else, so a prose
    edit is only guarded because it still rewrites the LINE — the stamp
    is what moves it. Were this to become a card-file-only write, an
    agent writing a verdict into a card would stop invalidating the
    owner's open modal, and their next save would overwrite it with no
    refusal and no trace.
    """
    out, prose = amik_edit.update_item(TEXT, "a", {"body": "Only prose."})
    assert prose == "Only prose."
    assert _rows(out)["a"]["updated_at"] == amik_edit._stamp()


def test_editing_never_moves_the_row():
    """Status and rank belong to the drag, not the modal — two writers for
    one field is how a board and its file drift apart."""
    out, _ = amik_edit.update_item(TEXT, "a", {"title": "X"})
    assert _rows(out)["a"]["status"] == "todo"
    assert _rows(out)["a"]["rank"] == 1


def test_editing_refuses_a_field_it_does_not_own():
    for field in ("status", "rank", "id", "kind", "created_at",
                  "src_title", "src_line", "codes"):
        with pytest.raises(ValueError):
            amik_edit.update_item(TEXT, "a", {field: "x"})


def test_an_empty_rung_clears_it_rather_than_writing_a_blank():
    text = _line("a", "todo", 1, planning="needs-brainstorm") + "\n"
    out, _ = amik_edit.update_item(text, "a", {"planning": ""})
    assert _rows(out)["a"]["planning"] is None


def test_an_unknown_rung_is_refused():
    with pytest.raises(ValueError):
        amik_edit.update_item(TEXT, "a", {"tag": "banana"})


def test_editing_one_row_leaves_every_other_line_byte_identical():
    out, _ = amik_edit.update_item(TEXT, "a", {"title": "X"})
    before, after = TEXT.split("\n"), out.split("\n")
    assert len(before) == len(after)
    assert before[1:] == after[1:]


def test_editing_an_unknown_id_is_refused():
    with pytest.raises(ValueError):
        amik_edit.update_item(TEXT, "nope", {"title": "X"})


# ── prose is written to the card file, never to the line ────────────────

def _prose(tmp_path, item_id):
    import os
    path = os.path.join(str(tmp_path), "amik", "cards", item_id + ".md")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_write_prose_creates_the_cards_directory(tmp_path):
    amik_edit.write_prose(str(tmp_path), "c1", "Some prose.\n")
    assert _prose(tmp_path, "c1") == "Some prose.\n"


def test_empty_prose_removes_the_file_rather_than_leaving_it_blank(tmp_path):
    """A card with no prose has NO file — the reader treats absence as an
    empty body, so an empty file is a second way to say the same thing."""
    amik_edit.write_prose(str(tmp_path), "c1", "text")
    amik_edit.write_prose(str(tmp_path), "c1", "")
    assert _prose(tmp_path, "c1") is None


def test_write_prose_refuses_an_id_that_escapes_the_directory(tmp_path):
    with pytest.raises(ValueError):
        amik_edit.write_prose(str(tmp_path), "../escape", "nope")


def test_the_reader_and_writer_agree_on_a_valid_card_id():
    """`_CARD_ID` is deliberately duplicated in board.py and here: the
    reader tolerates a bad id (returns no prose) where the writer refuses
    one (it would be creating the file), and readers must not import a
    writer to share it. The duplication only stays correct as long as
    both patterns admit exactly the same ids — this pins that, so
    widening one side alone would fail here instead of quietly giving the
    reader a filename the writer can never produce."""
    from amik.core import board as readers
    assert readers._CARD_ID.pattern == amik_edit._CARD_ID.pattern


def test_updating_a_body_writes_the_file_and_not_the_line(tmp_path):
    import json
    import os
    os.makedirs(os.path.join(str(tmp_path), "amik"), exist_ok=True)
    path = os.path.join(str(tmp_path), "amik", "board.jsonl")
    with open(path, "w") as f:
        f.write(_line("a", "todo", 1) + "\n")

    res = amik_edit.update(str(tmp_path), "a", {"body": "New prose."})
    assert res["ok"], res
    with open(path) as f:
        row = json.loads(f.read().strip())
    assert "body" not in row, "prose must not stay in the line"
    assert _prose(tmp_path, "a") == "New prose."


def test_a_state_only_update_leaves_the_prose_file_alone(tmp_path):
    import os
    os.makedirs(os.path.join(str(tmp_path), "amik"), exist_ok=True)
    with open(os.path.join(str(tmp_path), "amik", "board.jsonl"), "w") as f:
        f.write(_line("a", "todo", 1) + "\n")
    amik_edit.write_prose(str(tmp_path), "a", "untouched")
    amik_edit.update(str(tmp_path), "a", {"planning": "has-plan"})
    assert _prose(tmp_path, "a") == "untouched"


def test_deleting_a_card_unlinks_its_prose(tmp_path):
    import os
    os.makedirs(os.path.join(str(tmp_path), "amik"), exist_ok=True)
    with open(os.path.join(str(tmp_path), "amik", "board.jsonl"), "w") as f:
        f.write(_line("a", "todo", 1) + "\n" + _line("b", "todo", 2) + "\n")
    amik_edit.write_prose(str(tmp_path), "a", "prose")
    res = amik_edit.delete(str(tmp_path), "a")
    assert res["ok"], res
    assert _prose(tmp_path, "a") is None


def test_deleting_a_card_with_no_prose_file_is_not_an_error(tmp_path):
    import os
    os.makedirs(os.path.join(str(tmp_path), "amik"), exist_ok=True)
    with open(os.path.join(str(tmp_path), "amik", "board.jsonl"), "w") as f:
        f.write(_line("a", "todo", 1) + "\n")
    assert amik_edit.delete(str(tmp_path), "a")["ok"]


# ── a malformed hand-edited id must never turn a reader-shaped wrapper
# into one that raises ──────────────────────────────────────────────────

def test_deleting_a_malformed_id_row_still_succeeds(tmp_path):
    """The board is hand-authored, so a row can carry an id `_CARD_ID`
    would refuse (a leading `-`, here). Such an id can never have had a
    card file -- the writer refuses to create one under it -- so there
    is nothing to unlink, and removing the line is the whole job. Being
    unable to delete a bad row would be worse than the bug."""
    import os
    os.makedirs(os.path.join(str(tmp_path), "amik"), exist_ok=True)
    with open(os.path.join(str(tmp_path), "amik", "board.jsonl"), "w") as f:
        f.write(_line("-oops", "todo", 1) + "\n")
    res = amik_edit.delete(str(tmp_path), "-oops")
    assert res["ok"], res
    assert "-oops" not in _rows(open(
        os.path.join(str(tmp_path), "amik", "board.jsonl")).read())


def test_updating_body_on_a_malformed_id_row_is_refused(tmp_path):
    """A `body` field on such a row would have to reach write_prose, which
    cannot name a file for it. Refusing before the line write means no
    partial state -- the state change and the prose write either both
    happen or neither does."""
    import os
    os.makedirs(os.path.join(str(tmp_path), "amik"), exist_ok=True)
    path = os.path.join(str(tmp_path), "amik", "board.jsonl")
    original = _line("-oops", "todo", 1) + "\n"
    with open(path, "w") as f:
        f.write(original)
    res = amik_edit.update(str(tmp_path), "-oops", {"body": "text"})
    assert not res["ok"]
    assert res["reason"]
    with open(path) as f:
        assert f.read() == original, "no partial write on a refused update"


def test_updating_state_only_on_a_malformed_id_row_still_succeeds(tmp_path):
    """A state-only update never touches the card file, so a malformed id
    is nobody's business -- refusing it would be a needless new failure
    mode for rows that never asked for prose."""
    import os
    os.makedirs(os.path.join(str(tmp_path), "amik"), exist_ok=True)
    with open(os.path.join(str(tmp_path), "amik", "board.jsonl"), "w") as f:
        f.write(_line("-oops", "todo", 1) + "\n")
    res = amik_edit.update(str(tmp_path), "-oops",
                              {"planning": "has-plan"})
    assert res["ok"], res
    assert _rows(open(os.path.join(
        str(tmp_path), "amik", "board.jsonl")).read())["-oops"]["planning"] \
        == "has-plan"


def test_an_unwritable_cards_directory_is_refused_not_raised(tmp_path):
    """The line write and the prose write are two separate file operations
    inside one `update()` call. When `amik/cards` cannot be created --
    here, because a plain file already sits where the directory needs to
    go -- the failure has to come back in the reader shape, the same way
    a bad id already does, never as a raw OSError out of a reader-shaped
    wrapper. The state fields have already landed on the line by the time
    this is discovered, so only the prose is missing afterward."""
    import os
    amik_dir = os.path.join(str(tmp_path), "amik")
    os.makedirs(amik_dir, exist_ok=True)
    with open(os.path.join(amik_dir, "board.jsonl"), "w") as f:
        f.write(_line("a", "todo", 1) + "\n")
    open(os.path.join(amik_dir, "cards"), "w").close()  # blocks the dir

    res = amik_edit.update(str(tmp_path), "a",
                              {"title": "New title", "body": "text"})
    assert not res["ok"]
    assert res["reason"].startswith("unwritable")
    row = _rows(open(os.path.join(amik_dir, "board.jsonl")).read())["a"]
    assert row["title"] == "New title", "the line write already committed"


# ── deleting a row ──────────────────────────────────────────────────────
# Terminal, and git is the only undo. The door still refuses the one case
# that would leave the board quietly wrong.

def test_deleting_removes_the_line_and_nothing_else():
    out = amik_edit.delete_item(TEXT, "b")
    assert "b" not in _rows(out)
    assert sorted(_rows(out)) == ["a", "c", "x", "y"]


def test_deleting_renumbers_the_column_it_left():
    """A gap in the ranks is not fatal, but the file is the board's only
    order and a contiguous 1..n is the one thing every view assumes."""
    out = amik_edit.delete_item(TEXT, "a")
    assert _order(out, "todo") == ["b", "c"]
    assert [_rows(out)[i]["rank"] for i in ("b", "c")] == [1, 2]


def test_deleting_leaves_every_other_column_alone():
    before = [l for l in TEXT.split("\n") if '"done"' in l]
    out = amik_edit.delete_item(TEXT, "b")
    assert [l for l in out.split("\n") if '"done"' in l] == before


def test_deleting_an_unknown_id_is_refused():
    with pytest.raises(ValueError) as exc:
        amik_edit.delete_item(TEXT, "nope")
    assert "nope" in str(exc.value)


def test_deleting_the_last_row_of_a_column_leaves_an_empty_one():
    text = _line("only", "doing", 1) + "\n"
    assert amik_edit.delete_item(text, "only").strip() == ""


def test_a_delete_needs_no_referential_guard():
    """`parent` and `related` are both retired, so nothing on a row names
    another row's id and no delete can leave a dangling reference. A
    stale one left behind by hand is inert -- it must not make its target
    undeletable by the one verb that could clear it."""
    text = (TEXT + _line("k", "todo", 4, parent="a", related=["a"]) + "\n")
    out = amik_edit.delete_item(text, "a")
    assert "a" not in _rows(out)
    assert _order(out, "todo") == ["b", "c", "k"]


# ── who is adding decides where it lands ────────────────────────────────

def test_an_agents_row_joins_the_bottom_of_the_column():
    """Nothing an agent adds may jump the owner's queue. The law was
    written down before any verb could honour it; this is the verb."""
    text = "\n".join([_line("a", "inbox", 1), _line("b", "inbox", 2)]) + "\n"
    out, new_id = amik_edit.create_item(text, "An agent's finding",
                                           at_top=False)
    assert _order(out, "inbox") == ["a", "b", new_id]
    assert _rows(out)[new_id]["rank"] == 3


def test_an_agent_adding_to_an_empty_column_is_still_first():
    text = _line("x", "done", 1) + "\n"
    out, new_id = amik_edit.create_item(text, "First inbox row",
                                           at_top=False)
    assert _rows(out)[new_id]["rank"] == 1


def test_raised_by_records_an_adder_who_is_not_the_owner():
    """Absent means the owner, which is the common case and needs no
    field — so it is written only when something else added the row."""
    text = _line("a", "inbox", 1) + "\n"
    out, new_id = amik_edit.create_item(text, "From the watcher",
                                           at_top=False,
                                           raised_by="watcher")
    assert _rows(out)[new_id]["raised_by"] == "watcher"
    out, other = amik_edit.create_item(text, "From the owner")
    assert "raised_by" not in _rows(out)[other]


# ── answering one question leaves the rest of the card alone ───────────

CARD = """Opening prose.

## Questions

### First question?

The first answer.

### Second question?

## Notes

Closing prose.
"""


def test_an_answer_lands_under_its_own_heading():
    out = amik_edit.replace_section_body(CARD, "Second question?", "Yes.")
    assert "### Second question?\n\nYes.\n" in out


def test_everything_outside_the_section_is_untouched():
    """The surgical rule the board file already lives by, one level down:
    a prose edit shows as the sentences that changed and nothing else."""
    out = amik_edit.replace_section_body(CARD, "Second question?", "Yes.")
    assert out.startswith("Opening prose.\n")
    assert "### First question?\n\nThe first answer.\n" in out
    assert out.rstrip().endswith("Closing prose.")


def test_replacing_an_existing_answer_replaces_only_it():
    out = amik_edit.replace_section_body(CARD, "First question?", "Changed.")
    assert "Changed." in out
    assert "The first answer." not in out
    assert "### Second question?" in out


def test_an_empty_answer_empties_the_section():
    """An answer can be withdrawn, and the card goes back to waiting."""
    out = amik_edit.replace_section_body(CARD, "First question?", "")
    assert "The first answer." not in out
    assert "### First question?" in out


def test_an_unknown_heading_is_refused():
    """The writer refuses where the reader would merely find nothing: it
    is about to change a file, and a silent no-op would look like a save
    that worked."""
    with pytest.raises(ValueError):
        amik_edit.replace_section_body(CARD, "Never asked?", "x")


def test_a_heading_outside_the_questions_section_is_not_a_target():
    """A `###` ABOVE `## Questions` is not a target -- this is the
    `if not inside: continue` gate. The fixture needs a real `###`
    sitting before the section for that gate to be the reason the
    replace refuses, rather than the heading simply not existing."""
    prose = "### Before?\n\n## Questions\n\n### Real?\n\nans\n"
    with pytest.raises(ValueError):
        amik_edit.replace_section_body(prose, "Before?", "x")


def test_the_result_still_parses_as_the_same_questions():
    """The round trip that matters: what the writer produces is what the
    reader reads, so an answer written here is answered there."""
    from amik.core import board as readers
    out = amik_edit.replace_section_body(CARD, "Second question?", "Yes.")
    qs = readers._card_questions(out)
    assert [q["heading"] for q in qs] == ["First question?", "Second question?"]
    assert qs[1]["answer"] == "Yes."
    assert qs[1]["answered"] is True


def test_the_reader_and_writer_agree_on_the_questions_heading():
    """`_QUESTIONS_HEADING` is deliberately duplicated in board.py and
    here: board.py is the lower module and must not import the writer,
    and the writer only imports readers lazily inside `_write`, on
    purpose. If the two spellings ever drifted, the reader would find
    questions under a heading the writer cannot target — an answer typed
    against a heading the card visibly displays would be refused as
    unknown, which is worse than the `_CARD_ID` split this pins beside:
    that one only lets a bad id slip past the reader, this one would
    break every save."""
    from amik.core import board as readers
    assert readers._QUESTIONS_HEADING == amik_edit._QUESTIONS_HEADING


def test_a_heading_with_inner_whitespace_round_trips():
    """The reader's heading is whatever follows `### `, stripped -- inner
    whitespace survives that strip() but not a rebuilt `"### " + heading`
    compared to the whole line, so a heading like this one used to agree
    with the reader and disagree with the writer. Matching the reader's
    own rule instead means the two cannot drift apart."""
    from amik.core import board as readers
    prose = "## Questions\n\n###  Two  spaces\n\nold\n"
    heading = readers._card_questions(prose)[0]["heading"]
    assert heading == "Two  spaces"          # the reader's own parse
    out = amik_edit.replace_section_body(prose, heading, "new")
    qs = readers._card_questions(out)
    assert qs[0]["heading"] == "Two  spaces"
    assert qs[0]["answer"] == "new"


# ── a question with no sibling heading runs to end of file ─────────────

END_CARD = """Opening prose.

## Questions

### First question?

The first answer.

### Last question?

The last answer.
"""


def test_a_final_question_with_no_sibling_heading_reaches_end_of_file():
    """Every other fixture in this file closes its questions section with
    a sibling heading (`## Notes`, or another `### `) — the one shape
    that never reaches the end of the document. This fixture doesn't:
    the last question is the last thing in the file, which is the
    ordinary shape of a real card (an agent appends `## Questions`, asks
    one thing, and the file ends there). Only this test exercises the
    branch that closes the section at end-of-file rather than at a
    sibling heading."""
    out = amik_edit.replace_section_body(END_CARD, "Last question?", "Changed.")
    expected = ("Opening prose.\n\n## Questions\n\n### First question?\n\n"
                "The first answer.\n\n### Last question?\n\nChanged.\n")
    assert out == expected


# ── a repeated heading is undefined by the format, not by this function ─

DUP_HEADING_CARD = """## Questions

### Repeated question?

First body.

### Repeated question?

Second body.
"""


def test_a_duplicate_heading_only_the_first_occurrence_is_the_target():
    """Two `### ` lines with the same text are undefined by the card
    format itself — nothing stops an agent from asking the same question
    twice. This pins the function's actual behaviour rather than
    changing it: the first occurrence becomes `start`, and the next
    `### ` line — here, the second occurrence — closes the section, so
    only the first occurrence's body is replaced and the second stands
    untouched. A future change that resolves duplicates some other way
    now has to break this test to do it, rather than drifting quietly."""
    out = amik_edit.replace_section_body(DUP_HEADING_CARD,
                                          "Repeated question?", "Changed.")
    assert out.count("### Repeated question?") == 2
    assert "Changed." in out
    assert "First body." not in out
    assert "Second body." in out


# ── a REPEATED `## Questions` heading is a real shape, not a typo ──────
#
# An agent appending a new `## Questions` section to a card that already
# has one produces this. The result is spliced positionally
# (`lines[:start] + body + lines[end:]`), so any line the scan leaves
# inside `[start:end)` is a line this function deletes -- including a
# second `## Questions` line itself, if the scan does not treat it as a
# terminator.

TWO_QUESTIONS_SECTIONS_CARD = """## Questions

### Q1?

old

## Questions

### Q2?

b2
"""


def test_a_repeated_questions_heading_survives_a_replacement_before_it():
    """Replacing a question in the FIRST section must not cost the card
    its second `## Questions` line -- that line has to close the target
    section without falling inside the range that gets replaced."""
    out = amik_edit.replace_section_body(TWO_QUESTIONS_SECTIONS_CARD,
                                          "Q1?", "new")
    assert out.count("## Questions") == 2
    assert "### Q1?\n\nnew\n\n## Questions" in out
    assert "### Q2?\n\nb2" in out


def test_a_question_under_a_repeated_questions_heading_is_still_a_target():
    """`readers._card_questions` collects questions from every `##
    Questions` section a card has, so a question under the second one is
    visibly displayed -- and has to stay reachable here too, or an answer
    typed against it would raise `ValueError` on save. Answering it
    stands, with no sibling heading after to close it, so it runs to
    end of file."""
    out = amik_edit.replace_section_body(TWO_QUESTIONS_SECTIONS_CARD,
                                          "Q2?", "new")
    assert out == ("## Questions\n\n### Q1?\n\nold\n\n"
                    "## Questions\n\n### Q2?\n\nnew\n")


# ── a fenced code block in the answer is content, not structure ────────

def test_a_fenced_question_heading_does_not_end_the_section_being_replaced():
    """A fenced code block inside the section body can quote a `###`
    line. Mistaking it for the section's own end would splice the new
    answer in at that line and leave the fence's tail standing afterward
    as an orphaned, phantom question -- card corruption, not a redundant
    heading."""
    prose = ("## Questions\n\n### First question?\n\nold answer\n\n"
             "```\n### not a question\n```\n\nafter the fence\n")
    out = amik_edit.replace_section_body(prose, "First question?",
                                          "New answer.")
    assert "New answer." in out
    assert "### not a question" not in out
    from amik.core import board as readers
    assert [q["heading"] for q in readers._card_questions(out)] == \
        ["First question?"]


def test_a_fenced_sibling_heading_does_not_end_the_section_being_replaced():
    """The same corruption, one level up: a fenced `##` line looks like
    the sibling heading that legitimately closes a section, and treating
    it as one would splice the new answer in early and strand the
    fence's tail after it."""
    prose = ("## Questions\n\n### Q1?\n\nold\n\n"
             "```\n## fake section\n```\n\nafter the fence\n")
    out = amik_edit.replace_section_body(prose, "Q1?", "new")
    assert "## fake section" not in out
    assert "after the fence" not in out
    assert "new" in out


# ── a top-level section, created when absent ───────────────────────────
# A verdict is a `## Review` section, not a `###` under one, and unlike a
# question it may not exist yet: a card earns its first verdict. So this
# writer CREATES where the question writer REFUSES.

REVIEWED = """Opening prose.

## Review

The first verdict.

## Questions

### Still open?
"""


def test_a_verdict_replaces_the_body_of_its_own_section():
    out = amik_edit.upsert_section(REVIEWED, "Review", "A new verdict.")
    assert "## Review\n\nA new verdict.\n" in out
    assert "The first verdict." not in out


def test_a_heading_with_inner_whitespace_is_replaced_not_duplicated():
    """`upsert_section` used to rebuild `"## " + heading` and compare it
    to the whole line with `==` -- which agrees with neither a line that
    carries extra inner whitespace nor the reader's own match rule, so a
    heading like this one was never found and the old body was left
    stranded under a second, appended section. Matched through the same
    `amik_markdown.heading_text` helper `replace_section_body` uses, it
    is found and replaced instead."""
    prose = "Opening.\n\n##  Review\n\nold verdict\n"
    out = amik_edit.upsert_section(prose, "Review", "new verdict")
    assert out.count("Review") == 1
    assert "old verdict" not in out
    assert "new verdict" in out


def test_the_sections_around_it_are_untouched():
    out = amik_edit.upsert_section(REVIEWED, "Review", "A new verdict.")
    assert out.startswith("Opening prose.\n")
    assert "## Questions\n\n### Still open?" in out


def test_an_absent_section_is_created_at_the_end():
    """A card earns its first verdict. Refusing here would make the
    common case an error — the opposite of the question writer, where an
    unknown heading means the owner answered something that is not
    there."""
    out = amik_edit.upsert_section("Just prose.\n", "Review", "Merged.")
    assert out.startswith("Just prose.\n")
    assert "## Review\n\nMerged.\n" in out


def test_a_card_with_no_prose_at_all_gets_a_clean_section():
    out = amik_edit.upsert_section("", "Review", "Merged.")
    assert out.strip() == "## Review\n\nMerged."


def test_an_empty_verdict_empties_the_section_without_removing_it():
    """Reviewed-and-cleared is not the same claim as never-reviewed, so
    the heading survives an empty body."""
    out = amik_edit.upsert_section(REVIEWED, "Review", "")
    assert "## Review" in out
    assert "The first verdict." not in out


def test_a_nested_heading_is_not_a_target():
    """`### Review` under another section is not a `## Review` section,
    and targeting it would write a verdict into somebody's question."""
    prose = "## Questions\n\n### Review\n\nan answer\n"
    out = amik_edit.upsert_section(prose, "Review", "verdict")
    assert "### Review\n\nan answer" in out
    assert out.rstrip().endswith("## Review\n\nverdict".rstrip())


def test_writing_a_verdict_leaves_the_questions_alone():
    """The round trip that matters: writing a verdict must not disturb
    the questions the reader finds."""
    from amik.core import board as readers
    out = amik_edit.upsert_section(REVIEWED, "Review", "A new verdict.")
    assert [q["heading"] for q in readers._card_questions(out)] == \
        ["Still open?"]


def test_a_fenced_sibling_heading_does_not_end_an_upserted_section():
    """The same corruption `replace_section_body` is guarded against: a
    fenced `##` line inside the section's own body looks like the next
    section starting, and closing there would splice the new verdict in
    early and strand the fence's tail as an orphaned section afterward."""
    prose = ("## Review\n\nold verdict\n\n"
             "```\n## fake close\n```\n\nmore old\n")
    out = amik_edit.upsert_section(prose, "Review", "new verdict")
    assert out.count("## Review") == 1
    assert "## fake close" not in out
    assert "more old" not in out


def test_an_unclosed_fence_around_a_heading_is_not_that_section():
    """An unclosed fence swallows the rest, deliberately -- that is what
    a markdown renderer does too, and a writer that disagreed would be
    deciding a `##` line inside it IS a heading while the reader deciding
    the same question says it is not. Agreeing means this writer cannot
    find the section at all, so it does what it always does when a
    section is absent: append a new one. The result is a document with
    two `## Review` lines, one of them inert inside the fence -- visible
    to the owner on the card, not silently merged into by a writer
    guessing at what the fence meant."""
    prose = "```\nunclosed\n## Review\n\nold\n"
    out = amik_edit.upsert_section(prose, "Review", "new")
    assert out.count("## Review") == 2
    assert "old" in out
    assert "## Review\n\nnew" in out


# ── the branch a card was built on ─────────────────────────────────────


def _row_of(tmp_path, item_id):
    import json
    import os
    path = os.path.join(str(tmp_path), "amik", "board.jsonl")
    with open(path) as f:
        for line in f:
            if line.strip() and json.loads(line).get("id") == item_id:
                return json.loads(line)
    return None


def _one_card_board(tmp_path):
    import os
    path = os.path.join(str(tmp_path), "amik", "board.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(_line("a", "review", 1) + "\n")
    return path


def test_a_branch_is_recorded_on_the_line(tmp_path):
    _one_card_board(tmp_path)
    res = amik_edit.set_branch(str(tmp_path), "a", "card/a")
    assert res["ok"], res
    assert _row_of(tmp_path, "a")["branch"] == "card/a"


def test_an_empty_branch_removes_the_key(tmp_path):
    """Deleting the branch is what marks the work shipped, so the record
    of it has to be removable — and absent, not blank, because a blank
    string is a second way to say the same thing."""
    _one_card_board(tmp_path)
    amik_edit.set_branch(str(tmp_path), "a", "card/a")
    amik_edit.set_branch(str(tmp_path), "a", "")
    assert "branch" not in _row_of(tmp_path, "a")


def test_setting_a_branch_leaves_every_other_field_alone(tmp_path):
    _one_card_board(tmp_path)
    before = _row_of(tmp_path, "a")
    amik_edit.set_branch(str(tmp_path), "a", "card/a")
    after = _row_of(tmp_path, "a")
    for key in before:
        if key != "updated_at":
            assert after[key] == before[key], key


def test_an_unknown_card_is_refused(tmp_path):
    _one_card_board(tmp_path)
    assert amik_edit.set_branch(str(tmp_path), "nope", "card/x")["ok"] \
        is False


def test_branch_is_not_owner_editable():
    """Provenance is written by the system, never typed. A hand-entered
    branch name is a claim about git that nothing checked, and the modal
    must not offer it."""
    assert "branch" not in amik_edit.EDITABLE


def test_clearing_it_removes_the_key():
    """Absent means no. A false on every card is noise on a file the
    owner reads by eye."""
    text = "\n".join([_line("a", "todo", 1, requires_prototype=True),
                      _line("b", "todo", 2)]) + "\n"
    out, _prose = amik_edit.update_item(text, "a",
                                        {"requires_prototype": ""})
    assert "requires_prototype" not in _rows(out)["a"]


def test_it_is_a_boolean_not_the_string_it_arrived_as():
    """A form sends "on". Storing that would put a second spelling of
    true into a file that already has one."""
    out, _prose = amik_edit.update_item(TEXT, "a",
                                        {"requires_prototype": "on"})
    value = _rows(out)["a"]["requires_prototype"]
    assert value is True and not isinstance(value, str)


def test_a_real_false_clears_the_field():
    """A caller off the door -- an agent script, not the form -- passes a
    real Python bool. `str(False)` is the non-empty string "False", which
    used to satisfy the truthy branch and ARM the flag on a clear."""
    text = "\n".join([_line("a", "todo", 1, halt=True),
                      _line("b", "todo", 2)]) + "\n"
    out, _prose = amik_edit.update_item(text, "a", {"halt": False})
    assert "halt" not in _rows(out)["a"]


def test_a_real_zero_clears_the_field():
    """Same trap as `False`: `str(0)` is "0", non-empty and not "off"."""
    text = "\n".join([_line("a", "todo", 1, halt=True),
                      _line("b", "todo", 2)]) + "\n"
    out, _prose = amik_edit.update_item(text, "a", {"halt": 0})
    assert "halt" not in _rows(out)["a"]


def test_the_string_false_clears_the_field():
    """Belt and braces alongside the real bool/int above -- a caller might
    reasonably spell it as the string "false" rather than "off"."""
    text = "\n".join([_line("a", "todo", 1, halt=True),
                      _line("b", "todo", 2)]) + "\n"
    out, _prose = amik_edit.update_item(text, "a", {"halt": "false"})
    assert "halt" not in _rows(out)["a"]


# ── asking is a door verb ────────────────────────────────────────────


def test_asking_creates_the_section_when_absent(tmp_path):
    _one_card_board(tmp_path)
    amik_edit.write_prose(str(tmp_path), "a", "Just prose.\n")
    res = amik_edit.ask(str(tmp_path), "a", "Is this the first?")
    assert res["ok"], res
    prose = _prose(tmp_path, "a")
    assert "## Questions" in prose
    assert "### Is this the first?" in prose


def test_a_second_question_joins_the_existing_section(tmp_path):
    _one_card_board(tmp_path)
    amik_edit.write_prose(str(tmp_path), "a",
                          "## Questions\n\n### First?\n\nAnswered.\n")
    amik_edit.ask(str(tmp_path), "a", "Second?")
    prose = _prose(tmp_path, "a")
    assert prose.count("## Questions") == 1
    assert "### Second?" in prose
    assert "Answered." in prose


def test_a_new_question_arrives_unanswered(tmp_path):
    from amik.core import board as readers
    _one_card_board(tmp_path)
    amik_edit.write_prose(str(tmp_path), "a", "Prose.\n")
    amik_edit.ask(str(tmp_path), "a", "Open?")
    qs = readers._card_questions(_prose(tmp_path, "a"))
    assert qs[0]["answered"] is False


def test_asking_the_same_thing_twice_is_refused(tmp_path):
    """The writers refuse rather than no-op because a silent no-op reads
    as a save that worked. A duplicated question is that failure one
    level up: the first occurrence wins, so answering the second writes
    into the first."""
    _one_card_board(tmp_path)
    amik_edit.write_prose(str(tmp_path), "a", "## Questions\n\n### Open?\n")
    res = amik_edit.ask(str(tmp_path), "a", "Open?")
    assert res["ok"] is False
    assert "already" in res["reason"].lower()
    assert _prose(tmp_path, "a").count("### Open?") == 1


def test_the_refusal_ignores_surrounding_whitespace(tmp_path):
    """Matched the way the reader matches, or a heading with inner
    whitespace would agree with neither."""
    _one_card_board(tmp_path)
    amik_edit.write_prose(str(tmp_path), "a", "## Questions\n\n###  Open?\n")
    assert amik_edit.ask(str(tmp_path), "a", "Open?")["ok"] is False


def test_asking_an_unknown_card_is_refused(tmp_path):
    _one_card_board(tmp_path)
    assert amik_edit.ask(str(tmp_path), "nope", "Open?")["ok"] is False


def test_asking_stamps_the_row_as_updated(tmp_path):
    """The one writer here that skipped this would leave a card looking
    untouched by the one event that HOLDS it: an unanswered question."""
    import os
    path = os.path.join(str(tmp_path), "amik", "board.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(_line("a", "review", 1, updated_at="2020-01-01T00:00:00")
                + "\n")
    amik_edit.ask(str(tmp_path), "a", "Open?")
    assert _row_of(tmp_path, "a")["updated_at"] != "2020-01-01T00:00:00"


def test_asking_is_refused_when_the_appended_prose_would_be_unreadable(tmp_path):
    """Reporting success on a write nothing can read is the same failure
    this verb exists to close, arriving through a third door: an
    unclosed fence swallows the appended section, so the question would
    never show up to the reader that gates the build queue."""
    _one_card_board(tmp_path)
    amik_edit.write_prose(str(tmp_path), "a", "```\nunclosed\n")
    before = _prose(tmp_path, "a")
    res = amik_edit.ask(str(tmp_path), "a", "Open?")
    assert res["ok"] is False
    assert "unreadable" in res["reason"].lower()
    assert _prose(tmp_path, "a") == before


def test_the_row_is_not_stamped_when_the_appended_prose_is_refused(tmp_path):
    import os
    path = os.path.join(str(tmp_path), "amik", "board.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(_line("a", "review", 1, updated_at="2020-01-01T00:00:00")
                + "\n")
    amik_edit.write_prose(str(tmp_path), "a", "```\nunclosed\n")
    amik_edit.ask(str(tmp_path), "a", "Open?")
    assert _row_of(tmp_path, "a")["updated_at"] == "2020-01-01T00:00:00"


def test_a_normal_ask_is_readable_by_the_same_reader_that_gates_the_queue(tmp_path):
    from amik.core import board as readers
    _one_card_board(tmp_path)
    amik_edit.write_prose(str(tmp_path), "a", "Just prose.\n")
    amik_edit.ask(str(tmp_path), "a", "Open?")
    qs = readers._card_questions(_prose(tmp_path, "a"))
    assert any(q["heading"] == "Open?" and not q["answered"] for q in qs)


# ── the ruled write order: the line first ───────────────────────────────
#
# Ruled by the owner: "line first how it is now." The line write is what
# the stale-check guards, so writing it FIRST is what makes the guard
# mean anything. Prose-first would buy a cleaner failure in a rare case
# by inverting a property chosen deliberately — that a refused or stale
# write must never leave prose on disk for a state change that did not
# happen.

def _one_card(tmp_path):
    import os
    os.makedirs(os.path.join(str(tmp_path), "amik"), exist_ok=True)
    with open(os.path.join(str(tmp_path), "amik", "board.jsonl"), "w") as f:
        f.write(_line("a", "todo", 1) + "\n")


def test_a_failed_prose_write_is_reported_not_swallowed(tmp_path,
                                                        monkeypatch):
    """The half-applied state is accepted, but never silent. A caller
    that got `ok` while the card file did not change would have no reason
    to write again, and the board and the card would disagree forever."""
    _one_card(tmp_path)

    def boom(*a, **kw):
        raise OSError(13, "Permission denied")
    monkeypatch.setattr(amik_edit, "write_prose", boom)
    res = amik_edit.update(str(tmp_path), "a", {"body": "new prose"})
    assert res["ok"] is False
    assert "unwritable" in res["reason"]


def test_the_line_is_already_committed_when_the_prose_write_fails(
        tmp_path, monkeypatch):
    """The ruled order, stated as its consequence. Line first means the
    state change survives a prose failure — which is exactly the
    half-applied case, accepted with its eyes open."""
    _one_card(tmp_path)

    def boom(*a, **kw):
        raise OSError(13, "Permission denied")
    monkeypatch.setattr(amik_edit, "write_prose", boom)
    amik_edit.update(str(tmp_path), "a",
                     {"planning": "has-plan", "body": "new prose"})
    import os
    with open(os.path.join(str(tmp_path), "amik", "board.jsonl")) as f:
        assert json.loads(f.read().strip())["planning"] == "has-plan"


def test_a_stale_write_leaves_no_prose_behind(tmp_path):
    """The property line-first exists to protect, and the one prose-first
    would have traded away."""
    _one_card(tmp_path)
    res = amik_edit.update(str(tmp_path), "a", {"body": "never happened"},
                           fingerprint="not-the-current-one")
    assert res == {"ok": False, "reason": "stale"}
    assert _prose(tmp_path, "a") is None
