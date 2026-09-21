"""The owner's dev board at /amik — a Kanban column view over
amik/board.jsonl, with an edit modal over each card.

The page is hidden two ways and both are asserted here: it is absent from
the nav, and it 404s when the instance has no amik file. A ported
install has no amik/board.jsonl, so the route cannot render there.
"""
import json
import os

import pytest

from amik.core import board as readers
from amik.core import edit as amik_edit


def _board(root, rows):
    """Write amik/board.jsonl into an instance tree. `rows` may hold raw
    strings, which is how a malformed line — or a stale inline `body` the
    migration missed — gets onto a line untouched.

    A dict row's `body` is split out to its own card file and dropped from
    the line first, the same split the write door does on a save — so a
    fixture that wants a card to carry prose shapes its data the way a
    real write would, rather than handing the reader a key it no longer
    reads.
    """
    path = os.path.join(str(root), "amik", "board.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            if isinstance(r, dict) and "body" in r:
                r = dict(r)
                body = r.pop("body")
                if body:
                    amik_edit.write_prose(str(root), r["id"], str(body))
            f.write((r if isinstance(r, str) else json.dumps(r)) + "\n")
    return path


ROWS = [
    # inbox — the one blocking rung lives here; the other inbox row
    # carries none, since an owed decision is a Question now, not a rung
    {"id": "merge-verb", "rank": 1,
     "title": "Add a merge verb to the importer", "status": "inbox",
     "planning": "needs-brainstorm", "group": "importer",
     "body": "The source produces duplicates by construction."},
    {"id": "prune-runs", "rank": 2,
     "title": "Decide whether to prune workflow_runs", "status": "inbox",
     "planning": None, "group": "observability",
     "body": "See the noise during a real outage first.\n\n**Ruling.** "
             "2026-09-06: not yet — measure an outage first."},
    # todo — intended; a rung here says what is still owed, and the one
    # clearing rung is as real a declaration as the blocking one; absent
    # is N/A, not a third state
    {"id": "installer", "rank": 1,
     "title": "Ship the installer", "status": "todo",
     "planning": None,
     "group": "productization", "body": "Ship a one-line installer."},
    {"id": "zombie", "rank": 2,
     "title": "Clear the 29-day zombie", "status": "todo",
     "planning": "has-plan", "docs": ["docs/zombie-fix.md"],
     "group": "observability", "body": "A run row has sat `running`."},
    {"id": "chat-labels", "rank": 3,
     "title": "Give the editor domain-aware labels", "status": "todo",
     "planning": None, "group": "ui", "body": "Small."},
    # doing
    {"id": "watcher-cost", "rank": 1,
     "title": "Cut the polling cost", "status": "doing",
     "planning": None,
     "body": "Two fetch steps are 60% of all cloud output."},
    # done
    {"id": "e4-engine", "rank": 1,
     "title": "Build the E4 multi-step runner", "status": "done",
     "planning": None,
     "body": "Shipped.", "commits": ["d25b947"],
     "docs": ["docs/workflow-authoring.md"],
     "created_at": "2026-08-01", "updated_at": "2026-08-23T14:05:00"},
    # someday — the condition that revives a shelved row is prose in its
    # own body now, so nothing about it is a field the board has to carry
    {"id": "companies-rename", "rank": 1,
     "title": "Rename companies to organizations",
     "status": "someday", "planning": None,
     "body": "Second time.\n\n**Back when.** the schema is quiet "
             "(verified)"},
    {"id": "no-condition", "rank": 2,
     "title": "A shelved row with no condition", "status": "someday",
     "planning": None, "body": "Nothing says when this comes back."},
    # abandoned — one word for one meaning since 2026-09-17
    {"id": "effort-lever", "rank": 1,
     "title": "Use the per-step effort key", "status": "abandoned",
     "planning": None,
     "body": "The low arm averaged higher.\n\n**Ruling.** "
             "2026-09-07: not a cost lever. Do not re-raise."},
    {"id": "dep-graph", "rank": 2,
     "title": "Draw the dependency graph", "status": "abandoned",
     "planning": "has-plan",
     "body": "Google's visualizer does not exist publicly."},
]


# Every row is work now: `kind` retired with the reference panes.
WORK_IDS = [r["id"] for r in ROWS]


def _card_html(body, item_id):
    """The one card's whole <button>, opening tag included — so an
    assertion about the card FACE cannot pass on the hidden detail block,
    and cannot miss an attribute written before data-id (draggable and
    class both are)."""
    import re
    m = re.search(r'<button[^>]*class="akcard"[^>]*data-id="' + item_id
                  + r'"[^>]*>(.*?)</button>', body, re.S)
    assert m, "no card for " + item_id
    return m.group(0)


def _chip_text(card, css_class):
    """One chip's rendered TEXT, its attributes sliced away — so an
    assertion built on this cannot pass on the `data-tip` sentence alone.
    The label happens to be a substring of its own sentence, which once
    let three tests pass against a chip with no visible label at all."""
    element = card.split('class="chip ' + css_class, 1)[1].split(
        "</span>", 1)[0]
    return element.rsplit(">", 1)[1]


def _detail_html(client, item_id):
    """The hidden .akdata block — FETCHED, because the page no longer
    ships it. `GET /cards/{id}` renders one card's block and nothing
    else, so there is no card face to slice past any more."""
    res = client.get("/amik/cards/" + item_id)
    assert res.status_code == 200, "no detail block for " + item_id
    return res.text


def _column_html(body, status):
    """The whole <section>, opening tag included — the class attribute is
    written before data-status, so slicing from the marker would silently
    drop the very classes a collapse assertion is about."""
    import re
    m = re.search(r'<section[^>]*data-status="' + status + r'"[^>]*>'
                  r'(.*?)</section>', body, re.S)
    assert m, "no column for " + status
    return m.group(0)


# ── hidden, both ways ───────────────────────────────────────────────────

def test_reader_says_no_when_the_instance_has_no_amik(instance):
    assert readers.amik(str(instance))["ok"] is False


def test_page_404s_when_the_instance_has_no_amik(client):
    assert client.get("/amik").status_code == 404


def test_columns_are_the_nine_pm_states_in_board_order(instance):
    """Re-pins test_columns_are_the_seven_pm_states_in_board_order. The
    invariant is unchanged — a DECLARED order, not one derived from
    whatever the data happens to contain — and the vocabulary grew by the
    two states an agent working the board needs to report."""
    _board(instance, ROWS)
    cols = readers.amik(str(instance))["data"]["columns"]
    assert [c["status"] for c in cols] == [
        "inbox", "todo", "ready", "doing", "blocked", "review",
        "done", "someday", "abandoned"]
    assert [c["label"] for c in cols] == [
        "Inbox", "To-Do", "Ready", "Doing", "Blocked", "Review",
        "Done", "Someday", "Abandoned"]


def test_the_closed_columns_are_collapsed_by_default(instance):
    _board(instance, ROWS)
    cols = {c["status"]: c for c in readers.amik(str(instance))["data"]["columns"]}
    assert [s for s, c in cols.items() if c["collapsed"]] == [
        "done", "someday", "abandoned"]


def test_the_working_columns_are_open_by_default(instance):
    _board(instance, ROWS)
    cols = {c["status"]: c for c in readers.amik(str(instance))["data"]["columns"]}
    for s in ("inbox", "todo", "ready", "doing", "blocked", "review"):
        assert cols[s]["collapsed"] is False


def test_ready_is_declared_not_derived(instance):
    """No row carries status `ready`, and the column must exist anyway —
    it is a pull the owner drags into, so it ships empty."""
    assert not any(r["status"] == "ready" for r in ROWS)
    _board(instance, ROWS)
    cols = readers.amik(str(instance))["data"]["columns"]
    ready = next(c for c in cols if c["status"] == "ready")
    assert ready["count"] == 0 and ready["cards"] == []


def test_nothing_auto_fills_ready(instance):
    """A rule that promoted rows into ready would only restate todo."""
    _board(instance, ROWS)
    cols = readers.amik(str(instance))["data"]["columns"]
    assert next(c for c in cols if c["status"] == "ready")["cards"] == []
    assert next(c for c in cols if c["status"] == "todo")["count"] == 3


def test_an_empty_column_still_appears(instance):
    _board(instance, [r for r in ROWS if r["status"] != "done"])
    cols = readers.amik(str(instance))["data"]["columns"]
    done = next(c for c in cols if c["status"] == "done")
    assert done["count"] == 0 and done["cards"] == []


def test_an_unknown_status_gets_its_own_column_at_the_end(instance):
    """This is what kept the page rendering while the data migration ran
    ahead of the view. Filtering on `kind` must not become filtering on
    status: a work row in a status nobody declared still gets a column."""
    _board(instance, ROWS + [{"id": "odd", "title": "Odd", "status": "waffle",
                              "kind": "work", "rank": 1, "tag": None,
                              "body": "x"}])
    cols = readers.amik(str(instance))["data"]["columns"]
    assert cols[-1]["status"] == "waffle"
    assert [c["id"] for c in cols[-1]["cards"]] == ["odd"]


def test_column_count_matches_its_cards(instance):
    _board(instance, ROWS)
    for col in readers.amik(str(instance))["data"]["columns"]:
        assert col["count"] == len(col["cards"])


# ── nothing silently vanishes ───────────────────────────────────────────

def test_every_work_row_lands_in_exactly_one_column(instance):
    _board(instance, ROWS)
    data = readers.amik(str(instance))["data"]
    seen = [c["id"] for col in data["columns"] for c in col["cards"]]
    assert sorted(seen) == sorted(WORK_IDS)


def test_the_board_accounts_for_every_row(instance):
    """One structure, not two: every parsed row is a card in exactly one
    column. `kind` and the reference panes are retired, so there is no
    longer anywhere for a row to be filed instead."""
    _board(instance, ROWS)
    data = readers.amik(str(instance))["data"]
    assert sum(c["count"] for c in data["columns"]) == data["total"] \
        == len(ROWS)


# ── rank is the only sort ───────────────────────────────────────────────

def test_every_column_is_one_flat_list_ordered_by_rank(instance):
    """Re-pins test_live_is_grouped_by_priority_high_first. There is no
    priority field any more — rank carries the order those bands produced,
    so a sub-header could only restate the column it sits in."""
    _board(instance, ROWS)
    cols = readers.amik(str(instance))["data"]["columns"]
    todo = next(c for c in cols if c["status"] == "todo")
    assert [c["id"] for c in todo["cards"]] == [
        "installer", "zombie", "chat-labels"]
    assert [c["rank"] for c in todo["cards"]] == [1, 2, 3]


def test_the_reader_offers_no_priority_grouping(instance):
    assert not hasattr(readers, "AMIK_PRIORITIES")
    _board(instance, ROWS)
    for col in readers.amik(str(instance))["data"]["columns"]:
        assert "groups" not in col


def test_file_order_does_not_decide_a_column(instance):
    _board(instance, list(reversed(ROWS)))
    cols = readers.amik(str(instance))["data"]["columns"]
    todo = next(c for c in cols if c["status"] == "todo")
    assert todo["cards"][0]["id"] == "installer"


def test_a_row_with_no_rank_sorts_last_not_crashed(instance):
    _board(instance, [r for r in ROWS if r["status"] == "todo"]
           + [{"id": "nr", "title": "No rank", "status": "todo",
               "kind": "work", "tag": None, "body": "x"}])
    cols = readers.amik(str(instance))["data"]["columns"]
    todo = next(c for c in cols if c["status"] == "todo")
    assert [c["id"] for c in todo["cards"]][-1] == "nr"


# ── kind: the work board is work only ───────────────────────────────────


def test_a_leftover_kind_key_does_not_hide_a_row(instance):
    """`kind` was retired with the reference panes. A row still carrying
    one -- an old line the migration missed, or a hand edit -- is work
    like every other row, because nothing reads the field any more."""
    _board(instance, [{"id": "bare", "title": "No kind at all",
                       "status": "todo", "rank": 1, "planning": None,
                       "body": "x"},
                      {"id": "stale", "title": "Still says reference",
                       "status": "todo", "rank": 2, "planning": None,
                       "kind": "reference", "body": "y"}])
    cols = readers.amik(str(instance))["data"]["columns"]
    todo = next(c for c in cols if c["status"] == "todo")
    assert [c["id"] for c in todo["cards"]] == ["bare", "stale"]


# ── the readiness ladder ────────────────────────────────────────────────

def test_a_card_with_no_planning_value_carries_no_chip(client, instance):
    """Most rows are N/A, so a chip has to say something about THIS card
    rather than restate the column it sits in."""
    _board(instance, ROWS)
    assert "akplan" not in _card_html(client.get("/amik").text,
                                      "chat-labels")


def test_a_card_on_the_ladder_says_where(client, instance):
    _board(instance, ROWS)
    card = _card_html(client.get("/amik").text, "merge-verb")
    assert "akplan" in card and "needs-brainstorm" in card


def test_a_blocking_rung_reads_louder_than_a_clearing_one(client, instance):
    """Both get a chip; only the blocking one gets the attention class. A
    rung that clears the way is information about the card, not a warning
    about it."""
    _board(instance, ROWS)
    body = client.get("/amik").text
    assert "akblocking" in _card_html(body, "merge-verb")
    assert "akblocking" not in _card_html(body, "zombie")
    assert "has-plan" in _card_html(body, "zombie")


def test_the_reader_reports_where_a_card_sits(instance):
    _board(instance, ROWS)
    cols = readers.amik(str(instance))["data"]["columns"]
    by_id = {c["id"]: c for col in cols for c in col["cards"]}
    assert by_id["merge-verb"]["planning_chip"] == "needs-brainstorm"
    assert by_id["merge-verb"]["blocking"] is True
    assert by_id["zombie"]["planning_chip"] == "has-plan"
    assert by_id["zombie"]["blocking"] is False
    assert by_id["chat-labels"]["planning_chip"] == ""


def test_a_closed_row_shows_no_rung_even_with_a_stale_one(instance):
    """A rung left on a shipped row would print "not ready" against
    something that is already done. The FILE keeps the value -- the modal
    must not erase what it cannot see -- but the board shows nothing."""
    _board(instance, ROWS)
    cols = readers.amik(str(instance))["data"]["columns"]
    by_id = {c["id"]: c for col in cols for c in col["cards"]}
    assert by_id["dep-graph"]["planning"] == "has-plan"
    assert by_id["dep-graph"]["planning_chip"] == ""
    assert _chip_of(instance, "needs-brainstorm", "done") == ""
    assert _chip_of(instance, "needs-brainstorm", "abandoned") == ""
    assert _chip_of(instance, "needs-brainstorm", "someday") \
        == "needs-brainstorm"


# ── the ready invariant: surfaced, never corrected (D7) ─────────────────

def _ready(planning, **extra):
    row = {"id": "r1", "title": "A pulled row", "status": "ready",
           "rank": 1, "planning": planning, "body": "x"}
    row.update(extra)
    return row


def _flag_of(instance, rows, item_id="r1"):
    _board(instance, rows)
    cols = readers.amik(str(instance))["data"]["columns"]
    by_id = {c["id"]: c for col in cols for c in col["cards"]}
    return by_id[item_id]["conflict"]


def test_ready_owing_a_brainstorm_is_a_contradiction(instance):
    assert _flag_of(instance, [_ready("needs-brainstorm")])


def test_ready_on_a_clearing_rung_is_fine(instance):
    assert _flag_of(instance, [_ready("has-plan", docs=["docs/x.md"])]) == ""


def test_ready_owing_nothing_is_fine(instance):
    assert _flag_of(instance, [_ready(None)]) == ""


def test_the_same_rung_in_todo_is_not_a_contradiction(instance):
    """Only `ready` claims pullability, so only ready can contradict it."""
    row = dict(_ready("needs-brainstorm"), status="todo")
    assert _flag_of(instance, [row]) == ""


def test_the_contradiction_is_never_silently_corrected(client, instance):
    """The flag is a view; the row on disk keeps saying what it said."""
    _board(instance, [_ready("needs-brainstorm")])
    client.get("/amik")
    import json
    with open(os.path.join(str(instance), "amik", "board.jsonl")) as f:
        row = json.loads(f.read().strip())
    assert row["planning"] == "needs-brainstorm" \
        and row["status"] == "ready"


def test_the_flag_reaches_the_card(client, instance):
    _board(instance, [_ready("needs-brainstorm")])
    assert "akconflict" in _card_html(client.get("/amik").text, "r1")


# ── the card face (D8, D9) ──────────────────────────────────────────────

def test_no_date_shows_on_the_card_face(client, instance):
    """65 of 139 rows carry the same triage date, so the date was the same
    string on 46% of cards, in the highest-contrast small text."""
    _board(instance, ROWS)
    body = client.get("/amik").text
    assert "2026-09-07" not in _card_html(body, "zombie")


def test_the_dates_reach_the_detail_block(client, instance):
    """The card face carries no date; the modal carries the real two."""
    _board(instance, [dict(ROWS[3], created_at="2026-08-12",
                           updated_at="2026-09-01")])
    detail = _detail_html(client, "zombie")
    assert "2026-08-12" in detail and "2026-09-01" in detail
    assert "2026-08-12" not in _card_html(client.get("/amik").text, "zombie")


def test_the_board_carries_no_unpark_field_at_all(client, instance):
    """The field is retired, not hidden. A card that still rendered one
    would be reading a key the writer no longer maintains."""
    _board(instance, ROWS)
    body = client.get("/amik").text
    assert "akunpark" not in body
    assert "data-unpark" not in body
    assert "unpark_when" not in body


# ── never raises ────────────────────────────────────────────────────────

def test_a_malformed_line_is_skipped_not_fatal(instance):
    _board(instance, [ROWS[0], "{not json at all", ROWS[1]])
    r = readers.amik(str(instance))
    assert r["ok"] is True
    assert r["data"]["total"] == 2 and r["data"]["skipped"] == 1


def test_blank_lines_are_not_counted_as_skipped(instance):
    _board(instance, [ROWS[0], "", "   ", ROWS[1]])
    assert readers.amik(str(instance))["data"]["skipped"] == 0


def test_a_row_with_no_status_is_skipped_not_crashed(instance):
    _board(instance, [ROWS[0], {"id": "x", "title": "No status"}])
    r = readers.amik(str(instance))
    assert r["ok"] is True and r["data"]["skipped"] == 1


def test_a_skipped_line_is_reported_on_the_page(client, instance):
    _board(instance, [ROWS[0], "{not json at all"])
    assert "could not be parsed" in client.get("/amik").text


# ── the fingerprint ─────────────────────────────────────────────────────

def test_the_board_carries_a_fingerprint(instance):
    _board(instance, ROWS)
    assert readers.amik(str(instance))["data"]["fingerprint"]


def test_the_fingerprint_changes_when_the_file_changes(instance):
    _board(instance, ROWS)
    before = readers.amik(str(instance))["data"]["fingerprint"]
    _board(instance, ROWS[:3])
    assert readers.amik(str(instance))["data"]["fingerprint"] != before


# ── the page ────────────────────────────────────────────────────────────

def test_page_renders_every_work_title(client, instance):
    _board(instance, ROWS)
    body = client.get("/amik").text
    for row in ROWS:
        if row.get("kind") != "reference":
            assert row["title"] in body


def test_body_prose_reaches_the_detail_block(client, instance):
    _board(instance, ROWS)
    assert "Two fetch steps are 60% of all cloud output." in (
        _detail_html(client, "watcher-cost"))


def test_a_ruling_stays_attached_to_the_body_it_reverses(client, instance):
    """`body` is verbatim history and can state a decision a ruling
    reversed. The ruling used to render above it in its own callout; it is
    now appended to the prose itself, which is stronger — the correction
    cannot be separated from the claim by any later layout change."""
    _board(instance, ROWS)
    raw = _detail_html(client, "effort-lever")
    assert raw.index("The low arm averaged higher") < raw.index("**Ruling.**")


def test_the_page_has_no_forms(client, instance):
    _board(instance, ROWS)
    assert "<form" not in client.get("/amik").text


def test_cards_get_a_unique_key_even_when_ids_collide(instance):
    """`id` is hand-authored, so two rows can share one. The modal keys
    off `n`, or a duplicate would open the wrong card."""
    _board(instance, [dict(ROWS[0], id="same"), dict(ROWS[3], id="same")])
    data = readers.amik(str(instance))["data"]
    keys = [c["n"] for col in data["columns"] for c in col["cards"]]
    assert len(keys) == len(set(keys)) == 2


# ── the ladder is a closed vocabulary ───────────────────────────────────

def _chip_of(instance, planning, status="todo"):
    _board(instance, [{"id": "t", "title": "T", "status": status,
                       "rank": 1, "planning": planning, "body": "x"}])
    cols = readers.amik(str(instance))["data"]["columns"]
    return next(c for c in cols
                if c["status"] == status)["cards"][0]["planning_chip"]


def test_every_rung_of_the_ladder_is_reported(instance):
    """Both rungs, including the one that CLEARS the way. `has-plan` is a
    declaration in its own right -- "planned" is not the same statement as
    N/A, which is merely unclassified."""
    for rung in ("needs-brainstorm", "has-plan"):
        assert _chip_of(instance, rung) == rung


def test_no_planning_value_is_na_and_shows_nothing(instance):
    assert _chip_of(instance, None) == ""
    assert _chip_of(instance, "") == ""


def test_only_the_first_rung_blocks(instance):
    """The chip is shown for every rung; `blocking` is what separates a
    warning from information, and only `needs-brainstorm` earns it."""
    assert readers.AMIK_BLOCKING == ("needs-brainstorm",)


def test_a_retired_token_is_not_a_rung(instance):
    """Spellings from either retired ladder are gone, not aliased. A row
    still carrying one shows no chip rather than a state of a ladder that
    no longer has it."""
    for old in ("needs-decision", "brainstormed", "needs-plan", "build",
                "brainstorm-needed", "decision-needed",
                "brainstorm-complete", "plan-exists", "build-ready",
                "just-do-it"):
        assert _chip_of(instance, old) == ""


def test_an_unknown_rung_shows_nothing(instance):
    """A typo'd value must not print as a state of the ladder."""
    assert _chip_of(instance, "banana") == ""
    assert _chip_of(instance, 7) == ""


# ── the collapse reaches the DOM (blocker 4) ────────────────────────────

def test_the_closed_columns_carry_the_collapsed_class(client, instance):
    _board(instance, ROWS)
    body = client.get("/amik").text
    for status in ("done", "someday", "abandoned"):
        assert "akcollapsed" in _column_html(body, status)


def test_the_working_columns_do_not(client, instance):
    _board(instance, ROWS)
    body = client.get("/amik").text
    for status in ("inbox", "todo", "ready", "doing"):
        assert "akcollapsed" not in _column_html(body, status)


def test_a_column_header_announces_whether_it_is_open(client, instance):
    _board(instance, ROWS)
    body = client.get("/amik").text
    assert 'aria-expanded="false"' in _column_html(body, "done")
    assert 'aria-expanded="true"' in _column_html(body, "todo")


def test_an_empty_closed_column_is_not_collapsed(client, instance):
    """Collapsing an empty column would hide nothing and cost a click."""
    _board(instance, [r for r in ROWS if r["status"] != "done"])
    assert "akcollapsed" not in _column_html(client.get("/amik").text, "done")


# ── the drop zone is the thing that looks droppable (blocker 2) ─────────

def test_the_empty_state_sits_inside_the_drop_zone(client, instance):
    """Ready's empty state tells you to drag onto it, so it has to BE the
    drop target — text outside .akdrop accepts a drag and commits nothing."""
    _board(instance, ROWS)
    col = _column_html(client.get("/amik").text, "ready")
    drop = col.split('class="akdrop"', 1)[1].split("</div>", 1)[0]
    assert "Drag here" in drop


def test_a_non_string_status_is_skipped_not_crashed(client, instance):
    """A list where a status should be is unhashable, and the move route
    builds a set of the board's statuses — so it 500s the POST path unless
    the row is refused at the door."""
    _board(instance, [ROWS[0], {"id": "bad", "title": "Bad", "kind": "work",
                                "status": ["a"], "rank": 1, "body": "x"}])
    r = readers.amik(str(instance))
    assert r["ok"] is True and r["data"]["skipped"] == 1
    assert client.get("/amik").status_code == 200


def test_a_bad_dates_list_does_not_take_the_page_down(instance):
    """Reader contract: {ok, data|reason}, never a raise. A bare year among
    the date strings used to make the sort raise."""
    _board(instance, [dict(ROWS[0], dates=["2026-01-01", 2026]),
                      dict(ROWS[3], id="d2", dates=5)])
    assert readers.amik(str(instance))["ok"] is True


# ── the add + edit UI ───────────────────────────────────────────────────

def test_the_board_offers_the_groups_already_in_use(instance):
    """The datalist is derived, so a new area appears the moment one row
    uses it — and a typo does not become a permanent suggestion."""
    _board(instance, ROWS)
    groups = readers.amik(str(instance))["data"]["groups"]
    assert "importer" in groups and "ui" in groups
    assert groups == sorted(set(groups))


def test_only_inbox_offers_the_add_button(client, instance):
    """A new thought always lands in inbox; offering + elsewhere would
    invite skipping the column that means a decision is owed. Derived from
    the reader's own columns, not a hand-copied list, so a column added to
    the axis later is covered without anyone remembering to extend this
    test."""
    _board(instance, ROWS)
    cols = readers.amik(str(instance))["data"]["columns"]
    body = client.get("/amik").text
    for col in cols:
        html = _column_html(body, col["status"])
        if col["status"] == "inbox":
            assert "addbtn" in html
        else:
            assert "addbtn" not in html, col["status"]


def test_the_add_button_keeps_its_accessible_name(client, instance):
    """An aria-label is not a tooltip: it is the accessible NAME of a
    glyph-only button, and nothing else names this control."""
    _board(instance, ROWS)
    add = _column_html(client.get("/amik").text, "inbox")
    assert 'aria-label="Add an item"' in add


def test_a_card_carries_its_editable_values_for_the_modal(client, instance):
    _board(instance, ROWS)
    detail = _detail_html(client, "merge-verb")
    assert 'data-planning="needs-brainstorm"' in detail
    assert 'data-group="importer"' in detail
    assert 'data-title="Add a merge verb to the importer"' in detail


def test_the_modal_carries_the_id_it_is_editing(client, instance):
    """The id names the row in the file, which is what you need when you
    are about to grep for it or point a `parent` at it."""
    _board(instance, ROWS)
    body = client.get("/amik").text
    assert 'id="akidtext"' in body
    assert 'data-id="merge-verb"' in _detail_html(client, "merge-verb")


def test_the_raw_body_is_available_to_the_editor(client, instance):
    """The editor needs the markdown source, not the rendered HTML — and
    no script can call the Jinja filter that rendered it."""
    _board(instance, ROWS)
    detail = _detail_html(client, "merge-verb")
    assert "akraw" in detail
    assert "The source produces duplicates by construction." in detail


def test_the_modal_has_its_three_fields_and_both_endings(client, instance):
    _board(instance, ROWS)
    body = client.get("/amik").text
    assert 'id="akfields"' in body
    for field in ("akf-title", "akf-planning", "akf-group"):
        assert 'id="' + field + '"' in body
    for action in ("aksave", "akclose", "akdelete"):
        assert 'id="' + action + '"' in body


def test_the_modal_shows_no_status_pill(client, instance):
    """No PILL. A pill restating the column you just clicked from is
    noise, and the board behind the modal already says it.

    The card's status does ride as a data attribute now: the Status
    SELECT has to open on the right option, and dragging across lanes is
    the one board gesture a phone makes worse. That control writes through
    `/amik/move` like the drag, so `move` is still the only writer of
    `status` — what changed is where the owner can reach it, not who owns
    the field."""
    _board(instance, ROWS)
    detail = _detail_html(client, "merge-verb")
    assert "ak-inbox-chip" not in detail
    assert 'data-status="inbox"' in detail


def test_the_modal_never_shows_a_field_and_its_chip_at_once(client,
                                                            instance):
    """Planning and Area read as chips and edit as selects, and the two
    are MODES — never a value rendered twice on one screen, which is a
    value that can look wrong. The chips belong to the view pane and the
    selects to the form, and the form arrives hidden."""
    _board(instance, ROWS)
    page = client.get("/amik").text
    dialog = page.split('<dialog id="akdlg"', 1)[1]
    view = dialog.split('id="akform"', 1)[0]
    form = dialog.split('id="akform"', 1)[1]
    assert 'id="akviewchips"' in view and 'id="akf-planning"' not in view
    assert 'id="akf-planning"' in form and 'id="akf-group"' in form
    assert dialog.split('id="akform"', 1)[1].lstrip().startswith("hidden")


def test_nothing_renders_above_the_body(client, instance):
    """The strip that used to sit here was either the modal's own editable
    fields said twice, or reference data that belongs in the prose where
    it can be edited. What is left in the data block is what the modal
    READS -- attributes, the editor's source, the dates -- not what it
    shows."""
    _board(instance, ROWS)
    body = client.get("/amik").text
    assert "akbodyslot" not in body
    detail = _detail_html(client, "effort-lever")
    above = detail.split('class="akraw"', 1)[0]
    for gone in ("akfact", "akmeta", "akclosed", "Parent", "Docs",
                 "Commits", "Related"):
        assert gone not in above, gone


def test_the_related_field_is_retired_everywhere(client, instance):
    """A connection between two cards is prose in their bodies. The field
    is gone from the page, and the delete guard no longer consults it."""
    _board(instance, ROWS + [{"id": "peer", "title": "A peer",
                              "status": "todo", "rank": 9,
                              "planning": None, "related": ["zombie"],
                              "body": "x"}])
    assert "Related" not in client.get("/amik").text
    from amik.core import edit as amik_edit
    assert "related" not in amik_edit.EDITABLE


def test_the_planning_select_offers_the_whole_ladder_and_nothing_else(
        client, instance):
    _board(instance, ROWS)
    select = client.get("/amik").text.split('id="akf-planning"', 1)[1]
    select = select.split("</select>", 1)[0]
    for rung in readers.AMIK_PLANNING:
        assert rung in select
    assert ">N/A<" in select                       # the default, spelled out
    assert "banana" not in select
    for old in ("needs-decision", "brainstormed", "brainstorm-needed",
                "decision-needed", "plan-exists", "just-do-it"):
        assert old not in select


def test_the_board_never_uses_a_native_browser_dialog():
    """After a few window.confirm()s a browser offers to block all dialogs
    from the page, and one click would take the discard prompt with it.
    base.html's ask() and a real <dialog> are the house answer."""
    import os
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
    for name in ("amik.js", "quickadd.js"):
        js = open(os.path.join(here, "static", name)).read()
        for banned in ("window.confirm(", "window.prompt(",
                       "window.alert(", "alert("):
            assert banned not in js, name + ": " + banned


def test_the_quick_add_box_still_has_an_accessible_name(client, instance):
    """The visible label went with the chrome, so the only thing naming
    this input is its aria-label. A glyph-or-placeholder-only control is
    unnamed to a screen reader."""
    _board(instance, ROWS)
    dlg = client.get("/amik").text.split('id="aknew"', 1)[1]
    assert 'aria-label="Title of the new item"' in dlg.split("</dialog>")[0]


def test_the_quick_add_opens_on_the_keyboard():
    """Cmd/Ctrl+K, with preventDefault -- which is required rather than
    tidy, because the browser owns that chord (Chrome puts the omnibox
    into search mode) and would take it first."""
    js = _js("quickadd.js")
    chord = js.split("document.addEventListener('keydown'", 1)[1]
    assert "metaKey" in chord and "ctrlKey" in chord
    assert "preventDefault" in chord
    assert "open()" in chord


def test_the_chord_stands_down_wherever_a_key_already_means_something():
    """A global chord that eats typing is worse than no global chord. It
    yields to any open dialog, any field, and anything inside a
    CodeMirror editor, where Cmd+K is the editor's own."""
    js = _js("quickadd.js")
    guard = js.split("function typing(", 1)[1].split("}", 1)[0]
    assert "isContentEditable" in guard
    for tag in ("INPUT", "TEXTAREA", "SELECT"):
        assert tag in guard
    assert "cm-editor" in js
    chord = js.split("document.addEventListener('keydown'", 1)[1]
    assert "dialog[open]" in chord
    assert "typing(document.activeElement)" in chord


def test_the_plus_and_the_chord_share_one_entry_point():
    """Two ways in, one behaviour. A second copy of the create path on the
    board page is how a button and a shortcut drift apart."""
    assert "window.amikQuickAdd" in _js("quickadd.js")
    board = _js("amik.js")
    assert "window.amikQuickAdd" in board
    assert "'/amik/add'" not in board      # the POST lives in one file
    assert "aknew" not in board               # and so does the dialog


# ── the reader's contract, under a hand-edited file ─────────────────────

def test_a_null_title_does_not_take_the_page_down(client, instance):
    """`title` is rendered through inline_md, which calls html.escape —
    None has no such method. One bad line must not blank the board."""
    _board(instance, [ROWS[3], {"id": "bad", "title": None, "kind": "work",
                                "status": "todo", "rank": 9, "body": "x"}])
    r = readers.amik(str(instance))
    assert r["ok"] is True and r["data"]["skipped"] == 1
    assert client.get("/amik").status_code == 200


def test_a_non_string_title_is_skipped_not_rendered(client, instance):
    for bad in ({"a": 1}, 7, ["x"]):
        _board(instance, [ROWS[3], {"id": "bad", "title": bad, "kind": "work",
                                    "status": "todo", "rank": 9, "body": "x"}])
        assert readers.amik(str(instance))["data"]["skipped"] == 1
        assert client.get("/amik").status_code == 200


def test_a_non_utf8_byte_does_not_raise(instance):
    """The reader contracts to {ok, data|reason} and never to raise.
    UnicodeDecodeError is a ValueError, which `except OSError` misses."""
    import os
    path = os.path.join(str(instance), "amik", "board.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b'{"id": "a", "title": "A\xff", "status": "todo"}\n')
    r = readers.amik(str(instance))
    assert r["ok"] is False and "reason" in r


def test_a_non_utf8_board_404s_rather_than_500s(client, instance):
    import os
    path = os.path.join(str(instance), "amik", "board.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b'{"id": "a", "title": "A\xff", "status": "todo"}\n')
    assert client.get("/amik").status_code == 404


# ── the markup the JS depends on (mutation survivors) ───────────────────

def test_cards_are_draggable(client, instance):
    """The branch's headline interaction. Nothing else asserted it."""
    _board(instance, ROWS)
    assert 'draggable="true"' in _card_html(client.get("/amik").text,
                                            "zombie")


def test_the_failure_banner_exists_for_the_script_to_find(client, instance):
    """Every failure path in amik.js is `if (stale)`-guarded, so a
    renamed id turns every refused drag and save silent."""
    _board(instance, ROWS)
    assert 'id="akstale"' in client.get("/amik").text


def test_detail_blocks_are_hidden(client, instance):
    """139 blocks of rendered facts and raw markdown sit in the document.
    One attribute holds them back and no CSS rule backs it up."""
    _board(instance, ROWS)
    for chunk in client.get("/amik").text.split('class="akdata"')[1:]:
        assert "hidden" in chunk.split(">", 1)[0]


def test_the_area_control_is_a_select_over_the_areas_in_use(client,
                                                            instance):
    """A datalist only reveals itself on typing or on a hairline arrow,
    which is why the old input+datalist read as broken. A select shows
    what it has."""
    _board(instance, ROWS)
    body = client.get("/amik").text
    assert "akgroups" not in body                  # the datalist is gone
    assert "<datalist" not in body
    select = body.split('id="akf-group"', 1)[1].split("</select>", 1)[0]
    for area in ("importer", "observability", "productization", "ui"):
        assert '<option value="' + area + '">' in select
    assert '<option value="none">' in select        # -- none --
    assert '<option value="__new__">' in select    # the escape hatch


def test_the_new_area_box_exists_and_starts_hidden(client, instance):
    """Areas are added deliberately and rarely, so the box is out of the
    way until "New area..." asks for it."""
    _board(instance, ROWS)
    body = client.get("/amik").text
    row = body.split('id="akf-newgroup-row"', 1)[1].split(">", 1)[0]
    assert "hidden" in row
    assert 'id="akf-newgroup"' in body


def test_detail_blocks_have_a_css_backstop():
    """`hidden` is one attribute and any display rule beats it — which is
    exactly how the field strip's row leaked. Every card's rendered facts
    and raw markdown ride on this one."""
    import os
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
    css = open(os.path.join(here, "static", "amik.css")).read()
    assert ".akdata[hidden]" in css


# ── the board's geometry ────────────────────────────────────────────────
# Three CSS laws, each of which failed in the browser before it was
# written down. pytest cannot see a layout, but it can see whether the
# rule that fixes one is still in the file.

def _css():
    import os
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
    return open(os.path.join(here, "static", "amik.css")).read()


def _js(name="amik.js"):
    import os
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
    return open(os.path.join(here, "static", name)).read()


def _here():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")


def test_a_column_can_actually_shrink_to_its_declared_width():
    """`flex:0 0 280px` is NOT enough on its own. A flex item's default
    min-width:auto resolves to its MIN-CONTENT width and silently
    overrides flex-basis, so one long unbreakable string in a card used to
    stretch its whole column past 900px — which is what Someday did. Both
    halves are load-bearing: the column has to be allowed to shrink, and
    the card's text has to be allowed to break."""
    css = _css()
    col = css.split("\n.akcol {", 1)[1].split("}", 1)[0]
    assert "min-width:0" in col
    card = css.split("\n.akcard {", 1)[1].split("}", 1)[0]
    assert "overflow-wrap:anywhere" in card
    assert "min-width:0" in card


def test_the_heading_leaves_the_page_but_not_the_document(client, instance):
    """Clipped, not display:none — which would take it from screen readers
    too and leave the page with no heading at all."""
    _board(instance, ROWS)
    assert "<h1>Amik</h1>" in client.get("/amik").text
    rule = _css().split("body.akpage h1 {", 1)[1].split("}", 1)[0]
    assert "clip-path" in rule
    assert "display:none" not in rule


def test_an_empty_column_shows_no_count_pill(client, instance):
    """A "0" is the one number that says nothing the words do not."""
    _board(instance, ROWS)
    body = client.get("/amik").text
    ready = _column_html(body, "ready")
    pill = ready.split('class="akcount"', 1)[1].split(">", 1)[0]
    assert "hidden" in pill
    todo = _column_html(body, "todo")
    assert "hidden" not in todo.split('class="akcount"', 1)[1].split(">", 1)[0]
    assert ".akcount[hidden]" in _css()      # display rules beat [hidden]


def test_a_date_only_stamp_still_renders_an_age(instance):
    """`time_ago` needs a time component — by design, and with its own
    tests — so a bare date renders as an EMPTY age. Every row written
    before timestamps carries one, which would have left "Created ·
    Updated" with two blanks on 125 of 125 cards. Normalised on read, the
    same way a host application would handle its own timestamps."""
    _board(instance, [{"id": "old", "title": "An older row",
                       "status": "todo", "rank": 1, "planning": None,
                       "body": "x", "created_at": "2026-08-01",
                       "updated_at": "2026-09-09"}])
    card = readers.amik(str(instance))["data"]["columns"]
    card = next(c for c in card if c["status"] == "todo")["cards"][0]
    assert card["created_at"] == "2026-08-01T12:00:00"
    from amik.app.render import time_ago
    assert time_ago(card["created_at"])
    assert time_ago(card["updated_at"])


def test_a_stamp_that_already_has_a_time_is_left_alone(instance):
    _board(instance, [{"id": "new", "title": "A new row", "status": "todo",
                       "rank": 1, "planning": None, "body": "x",
                       "created_at": "2026-09-10T16:05:00",
                       "updated_at": "2026-09-10T16:05:00"}])
    cols = readers.amik(str(instance))["data"]["columns"]
    card = next(c for c in cols if c["status"] == "todo")["cards"][0]
    assert card["created_at"] == "2026-09-10T16:05:00"


def test_a_missing_stamp_stays_empty_rather_than_becoming_a_date(instance):
    """A row with no created_at renders no Created line at all — inventing
    one would date a row from the day someone looked at it."""
    _board(instance, [{"id": "bare", "title": "No stamps", "status": "todo",
                       "rank": 1, "planning": None, "body": "x"}])
    cols = readers.amik(str(instance))["data"]["columns"]
    card = next(c for c in cols if c["status"] == "todo")["cards"][0]
    assert card["created_at"] == "" and card["updated_at"] == ""


# ── the quick-add is global, and gated ──────────────────────────────────
# Embedded, it rides the host's own layout, so it appears on every page
# that layout renders. That is only acceptable because the gate is the
# SAME predicate that 404s /amik: an instance with no board carries none
# of this, rather than carrying it hidden.

def test_the_quick_add_is_on_every_page_of_this_instance(client, instance):
    _board(instance, ROWS)
    # Paths a host might mount around a board. Most 404 against this
    # fixture and are skipped; the point is that any page which DOES
    # render carries the control, and "/amik" always does.
    for path in ("/", "/projects", "/reports", "/settings", "/amik"):
        r = client.get(path)
        if r.status_code != 200:
            continue                      # a page this fixture cannot render
        assert 'id="aknew"' in r.text, path
        assert "quickadd.js" in r.text, path


def test_an_instance_with_no_board_carries_none_of_it(client, instance):
    """The whole reason this is allowed to be global. A ported install has
    no amik/board.jsonl, so the dialog, the script and the keybinding do
    not exist -- not hidden, absent."""
    for path in ("/", "/status", "/settings"):
        r = client.get(path)
        if r.status_code != 200:
            continue
        assert 'id="aknew"' not in r.text, path
        assert "quickadd.js" not in r.text, path
        assert "akquick" not in r.text, path
    assert client.get("/amik").status_code == 404


def test_the_gate_is_the_same_predicate_that_hides_the_route(instance):
    """One predicate, so the page and the chord cannot disagree about
    whether this instance has a board. Existence rather than a parse,
    because it runs on every page render."""
    assert readers.has_amik(str(instance)) is False
    assert readers.amik(str(instance))["ok"] is False
    _board(instance, ROWS)
    assert readers.has_amik(str(instance)) is True
    assert readers.amik(str(instance))["ok"] is True


def test_every_route_hides_on_an_instance_with_no_board(instance):
    """`has_amik` gates the board and its writes; the prototype route
    answers to a DIFFERENT predicate, `amik_project()`, over a different
    file. Naming the routes by hand is exactly how one of those gates
    went unchecked, so this walks the surface's own list instead — every
    route must 404 on an instance holding neither file, whichever
    predicate happens to be guarding it."""
    from amik.app.handle import ROUTES, handle
    for method, shape in ROUTES:
        path = shape.replace("{id}", "x").replace("{file}", "amik.css")
        status, _, _ = handle(method, "/amik" + path.rstrip("/"),
                              None, b"", root=instance, base="/amik")
        # static is Amik's own asset, served whatever the instance holds
        expect = 200 if shape.startswith("/static") else 404
        assert status == expect, (method, shape, status)


def test_every_listed_route_actually_answers(scenario):
    """The other half, and the reason the list can be trusted: an entry
    that no longer resolves would make the test above pass for the wrong
    reason — a route that 404s because it is GONE, not because it is
    gated."""
    from amik.app.handle import ROUTES, handle
    import os
    root = scenario("ready_plain")
    os.makedirs(os.path.join(root, "amik", "prototypes", "p1"))
    with open(os.path.join(root, "amik", "prototypes", "p1",
                           "index.html"), "w") as f:
        f.write("<html></html>")
    with open(os.path.join(root, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\n')
    ids = {"/cards/{id}/prototype": "p1"}
    for method, shape in ROUTES:
        path = shape.replace("{id}", ids.get(shape, "rename-the-export-button"))
        path = path.replace("{file}", "amik.css")
        status, _, _ = handle(method, "/amik" + path.rstrip("/"), None,
                              b"to_status=doing&to_index=0&title=x",
                              root=root, base="/amik")
        assert status != 404, (method, shape)


def test_the_board_page_does_not_ship_a_second_dialog(client, instance):
    """base.html already provides it. Two dialogs with one id is how a
    button ends up wired to the copy that is not on screen."""
    _board(instance, ROWS)
    assert client.get("/amik").text.count('id="aknew"') == 1


def test_the_dialog_is_only_a_flex_column_when_it_is_open():
    """A bare `display:flex` on the dialog beats the UA's own
    `dialog:not([open]) { display:none }` and leaves the modal on screen
    permanently. Every display rule on a thing the browser hides by
    default has to say [open] — the same trap as .akdata[hidden]."""
    css = _css()
    assert "#akdlg[open] { display:flex" in css
    bare = css.split("\n#akdlg {", 1)[1].split("}", 1)[0]
    assert "display:flex" not in bare


def test_the_focus_ring_is_one_rule_for_every_focusable_type():
    """CLAUDE.md's own law: when a rule is an enumeration, assume
    something falls off it. The ring is declared once over a named list,
    and a type missing from that list is a control that focuses
    invisibly."""
    block = _css().split(".chip:focus-visible", 1)[1].split("}", 1)[0]
    # `summary` joined the list when the board header became a <details>:
    # a <summary> is keyboard-focusable by default, so it is a control
    # that can focus invisibly like any other. It was already in the CSS
    # and in neither test, which is the enumeration falling off the guard
    # rather than off the rule.
    for kind in ("input", "select", "textarea", "button", "a", "summary"):
        assert kind + ":focus-visible" in block or block.startswith(kind), \
            kind


def _rules():
    """Every (selectors, body) pair in the stylesheet, comments stripped.
    A comment can hold a brace and a property that is not declared."""
    import re
    css = re.sub(r"/\*.*?\*/", "", _css(), flags=re.S)
    return [(m.group(1).strip(), m.group(2))
            for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css)]


def _scrollers():
    """The selectors that actually scroll — derived from the CSS, never
    listed here. A list written in the test is a second place to forget a
    new scroller, which is the failure this guard exists to catch."""
    import re
    out = []
    for sel, body in _rules():
        if re.search(r"overflow(-[xy])?:\s*(auto|scroll)", body):
            out.extend(s.strip() for s in sel.split(","))
    return out


def _card_file(root, item_id, text):
    import os
    path = os.path.join(str(root), "amik", "cards", item_id + ".md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    return path


def _body_of(instance, item_id):
    cols = readers.amik(str(instance))["data"]["columns"]
    by_id = {c["id"]: c for col in cols for c in col["cards"]}
    return by_id[item_id]["body"]


def test_a_card_file_supplies_the_body(instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1", "Prose from the card file.\n")
    assert _body_of(instance, "c1") == "Prose from the card file.\n"


def test_an_inline_body_is_ignored_now_that_the_migration_is_done(instance):
    """The fallback existed so the data could move in its own commit. It
    is gone: a line carrying prose is a line the migration missed, and
    honouring it would let a stale copy win somewhere."""
    _board(instance, [json.dumps({"id": "c1", "title": "A card",
                                  "status": "todo", "rank": 1,
                                  "planning": None,
                                  "body": "stale inline"})])
    assert _body_of(instance, "c1") == ""


def test_no_body_anywhere_is_an_empty_string_not_a_crash(instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    assert _body_of(instance, "c1") == ""


def test_an_unreadable_card_file_is_an_empty_body_not_a_raise(instance):
    """Readers contract never to raise. A non-UTF-8 byte in a card file
    must cost that card its prose, not the whole page."""
    import os
    path = os.path.join(str(instance), "amik", "cards", "c1.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"fine\n\xff\xfe not utf-8\n")
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    data = readers.amik(str(instance))
    assert data["ok"] is True
    assert _body_of(instance, "c1") == ""


def test_a_card_id_cannot_escape_the_cards_directory(instance):
    """`id` is hand-authored, so it is untrusted input to a path join. A
    traversal must read nothing rather than reach outside amik/cards/.

    Both the cards directory and the traversal's target must actually
    exist, or `open()` fails on the missing parent before `..` is ever
    resolved and this would pass whether or not the guard does anything.
    So both are created, and the marker's absence from the body — not
    just an empty string — is what proves nothing leaked.
    """
    cards_dir = os.path.join(str(instance), "amik", "cards")
    os.makedirs(cards_dir, exist_ok=True)
    marker = "MARKER-DO-NOT-LEAK-6f1c2a"
    with open(os.path.join(str(instance), "CLAUDE.md"), "w") as f:
        f.write(marker)
    _board(instance, [{"id": "../../CLAUDE", "title": "Escape",
                       "status": "todo", "rank": 1, "planning": None}])
    body = _body_of(instance, "../../CLAUDE")
    assert body == ""
    assert marker not in body


def test_the_live_board_has_moved_into_amik():
    """The board is a dev-tree file, so this asserts on the real one. The
    guard against the old board file's path reappearing lives in
    test_amik_naming.py instead, which is exempt from this repo's
    site-wide retired-name scan that this file is not."""
    import os
    from conftest import INSTANCE as ROOT
    assert os.path.isfile(os.path.join(ROOT, "amik", "board.jsonl"))


def test_no_live_card_keeps_its_prose_in_the_line():
    """Prose moved to amik/cards/. A line still carrying `body` is a card
    the migration missed, and the reader would prefer the file anyway —
    so the line's copy could silently go stale."""
    import json
    import os
    from conftest import INSTANCE as ROOT
    with open(os.path.join(ROOT, "amik", "board.jsonl")) as f:
        rows = [json.loads(l) for l in f if l.strip()]
    assert rows, "the live board should not be empty"
    assert [r["id"] for r in rows if "body" in r] == []


def test_no_card_file_is_orphaned():
    """A card file whose id matches no row is prose with nothing pointing
    to it. Left in place, a later card that reuses the same id would
    silently inherit someone else's old body — orphans must be caught,
    not just tolerated."""
    import json
    import os
    from conftest import INSTANCE as ROOT
    with open(os.path.join(ROOT, "amik", "board.jsonl")) as f:
        ids = [json.loads(l)["id"] for l in f if l.strip()]
    cards = os.path.join(ROOT, "amik", "cards")
    orphans = [f[:-3] for f in os.listdir(cards)
               if f.endswith(".md") and f[:-3] not in ids]
    assert orphans == [], f"card files with no card: {orphans}"


def test_no_live_card_file_is_empty():
    """write_prose removes a file rather than leaving it empty, so an
    empty card file on disk means a write was interrupted partway
    through rather than completing or removing cleanly."""
    import os
    from conftest import INSTANCE as ROOT
    cards = os.path.join(ROOT, "amik", "cards")
    empty = [f for f in os.listdir(cards)
             if f.endswith(".md")
             and os.path.getsize(os.path.join(cards, f)) == 0]
    assert empty == [], f"empty card files: {empty}"


def test_the_two_new_columns_ship_empty(instance):
    """Nothing may fill them. They are written by an agent that does not
    exist yet, and until it does an empty column is the honest state."""
    assert not any(r["status"] in ("blocked", "review") for r in ROWS)
    _board(instance, ROWS)
    cols = {c["status"]: c
            for c in readers.amik(str(instance))["data"]["columns"]}
    for s in ("blocked", "review"):
        assert cols[s]["count"] == 0 and cols[s]["cards"] == []


def test_a_card_can_be_dragged_into_the_new_columns(client, instance):
    """The move route validates against the columns the reader built, so
    a column that renders is a column that accepts a drop. Asserting it
    keeps the two from drifting apart."""
    _board(instance, ROWS)
    fp = readers.amik(str(instance))["data"]["fingerprint"]
    for status in ("blocked", "review"):
        res = client.patch("/amik/cards/watcher-cost/position", data={ "to_status": status, "to_index": 0,
            "fingerprint": fp})
        assert res.status_code == 200, (status, res.text)
        fp = readers.amik(str(instance))["data"]["fingerprint"]
    rows = readers.amik(str(instance))["data"]["columns"]
    review = next(c for c in rows if c["status"] == "review")
    assert [c["id"] for c in review["cards"]] == ["watcher-cost"]


# ── a has-plan row that names no plan ───────────────────────────────


def _conflict_of(instance, row):
    _board(instance, [row])
    cols = readers.amik(str(instance))["data"]["columns"]
    card = next(c for col in cols for c in col["cards"])
    return card["conflict"], card["conflict_label"]


def test_plan_exists_with_no_docs_is_a_contradiction(instance):
    """The rung claims a written plan. With nothing in `docs` the claim
    names no document, so it cannot be checked or read — which is the
    whole reason the rung is worth declaring."""
    sentence, label = _conflict_of(instance, {
        "id": "p1", "title": "A card", "status": "todo", "rank": 1,
        "planning": "has-plan"})
    assert "plan" in sentence.lower()
    assert label == "plan not named"


def test_plan_exists_with_docs_is_no_contradiction(instance):
    sentence, label = _conflict_of(instance, {
        "id": "p1", "title": "A card", "status": "todo", "rank": 1,
        "planning": "has-plan", "docs": ["docs/some-plan.md"]})
    assert (sentence, label) == ("", "")


def test_an_empty_docs_list_names_no_document_either(instance):
    """`docs: []` is the shape a cleared field leaves behind, and it is
    the same claim as no field at all."""
    sentence, _ = _conflict_of(instance, {
        "id": "p1", "title": "A card", "status": "todo", "rank": 1,
        "planning": "has-plan", "docs": []})
    assert sentence != ""


def test_a_closed_row_is_never_asked_for_its_plan(instance):
    """A closed row owes nothing — a rung left on something that already
    shipped is stale by definition, which is why the chip is blanked for
    one. The guard matches the chip's own rule in `_amik_planning_chip`
    rather than inventing a second one, and it starts to matter the day a
    card ships carrying `has-plan` with it into `done` — a plan that
    shipped the work is not a plan nobody can read."""
    for status in ("done", "abandoned"):
        sentence, label = _conflict_of(instance, {
            "id": "p1", "title": "A card", "status": status, "rank": 1,
            "planning": "has-plan"})
        assert (sentence, label) == ("", ""), status


def test_the_ready_contradiction_still_wins_its_own_case(instance):
    """The rung that fires the older branch is a blocking one, and
    has-plan is not blocking, so the two can never contend. Pinned
    because adding a second branch to a function that returns ONE pair is
    where that would stop being true."""
    sentence, label = _conflict_of(instance, {
        "id": "p1", "title": "A card", "status": "ready", "rank": 1,
        "planning": "needs-brainstorm"})
    assert label == "ready but blocked"


# ── a card's questions are headings in its prose ────────────────────────
# Under `## Questions`, each `###` is a question and the prose beneath it
# is the answer. An empty section is an unanswered question. That one rule
# is the whole machine, so these tests are mostly about where it STOPS.

QUESTIONS_CARD = """Some opening prose about the card.

## Questions

### Should merge keep both timelines, or drop the loser's?

Keep both, dedup by date and text. A duplicate entry is worse than a
long page.

### What happens to a page with no timeline at all?

## Notes

Not a question section.
"""


def test_a_question_is_a_heading_and_its_answer_is_the_prose_beneath():
    qs = readers._card_questions(QUESTIONS_CARD)
    assert [q["heading"] for q in qs] == [
        "Should merge keep both timelines, or drop the loser's?",
        "What happens to a page with no timeline at all?"]
    assert qs[0]["answer"].startswith("Keep both, dedup by date")
    assert qs[0]["answered"] is True


def test_an_empty_section_is_an_unanswered_question():
    """The rule the whole machine rests on. A heading with nothing under
    it is the agent having asked and nobody having answered."""
    qs = readers._card_questions(QUESTIONS_CARD)
    assert qs[1]["answer"] == ""
    assert qs[1]["answered"] is False


def test_a_heading_after_a_later_section_is_not_a_question():
    """A `###` under a later `##` is not a question. `QUESTIONS_CARD` has
    no heading after its `## Notes`, so it can't show this: without the
    terminator, a `###` anywhere later in the card would still be read as
    a question, and this fixture puts one there to prove it's excluded."""
    qs = readers._card_questions(
        "## Questions\n\n### A real question?\n\n## Notes\n\n"
        "### Not a question, it is under Notes\n")
    assert [q["heading"] for q in qs] == ["A real question?"]


def test_headings_outside_the_questions_section_are_not_questions():
    """A `###` ABOVE `## Questions` is not a question -- this is the
    `if not inside: continue` gate, not the early no-`## Questions`-at-all
    guard, so the fixture must carry a real `## Questions` section for the
    gate to be the thing that excludes it."""
    qs = readers._card_questions(
        "### Before?\n\n## Questions\n\n### Real?\n\nans\n")
    assert [q["heading"] for q in qs] == ["Real?"]


def test_a_card_with_no_questions_section_has_no_questions():
    assert readers._card_questions("Just prose.\n") == []


def test_whitespace_is_not_an_answer():
    """A section holding only blank lines is the same claim as an empty
    one, and a trailing newline is not prose."""
    qs = readers._card_questions("## Questions\n\n### Q\n\n   \n\n")
    assert qs[0]["answered"] is False


def test_the_parser_never_raises_on_junk():
    """Readers contract never to raise, and a card file is hand-edited
    markdown — the parser has to survive whatever is in it."""
    for junk in ("", "## Questions", "## Questions\n###\n", "#" * 200,
                 "## questions\n### lowercase heading\n"):
        assert isinstance(readers._card_questions(junk), list)


def test_the_section_heading_is_matched_exactly():
    """`## questions` in lowercase is a different heading. Matching it
    loosely would make an ordinary prose heading start blocking a card."""
    assert readers._card_questions("## questions\n\n### Q\n") == []


def test_a_fenced_heading_does_not_become_a_question():
    """Reproduced before this existed: the code line became a second
    question AND truncated the real answer at that line."""
    from amik.core import board as readers
    qs = readers._card_questions(
        "## Questions\n\n### Real?\n\n```\n### fake\n```\n\nstill the answer\n")
    assert [q["heading"] for q in qs] == ["Real?"]
    assert "still the answer" in qs[0]["answer"]


def test_a_row_carries_its_questions_and_an_unanswered_count(instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1", QUESTIONS_CARD)
    cols = readers.amik(str(instance))["data"]["columns"]
    card = next(c for col in cols for c in col["cards"])
    assert len(card["questions"]) == 2
    assert card["unanswered"] == 1


def test_a_row_with_no_card_file_has_no_questions(instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    cols = readers.amik(str(instance))["data"]["columns"]
    card = next(c for col in cols for c in col["cards"])
    assert card["questions"] == [] and card["unanswered"] == 0


# ── the column and the prose can disagree, and that is reported ────────


def _question_flag(instance, status, prose):
    _board(instance, [{"id": "c1", "title": "A card", "status": status,
                       "rank": 1, "planning": None}])
    if prose is not None:
        _card_file(instance, "c1", prose)
    cols = readers.amik(str(instance))["data"]["columns"]
    card = next(c for col in cols for c in col["cards"])
    return card["question_flag"], card["question_flag_label"]


UNANSWERED = "## Questions\n\n### An open question\n"
ANSWERED = "## Questions\n\n### An open question\n\nAn answer.\n"


def test_an_unanswered_question_outside_blocked_is_reported(instance):
    """The card is waiting on the owner and its column does not say so,
    which is the case the column exists to make visible."""
    sentence, label = _question_flag(instance, "doing", UNANSWERED)
    assert "question" in sentence.lower()
    assert label == "question waiting"


def test_blocked_with_nothing_unanswered_is_reported(instance):
    """Either the question was answered and the card can move, or it is
    blocked on something its prose does not mention."""
    sentence, label = _question_flag(instance, "blocked", ANSWERED)
    assert sentence
    assert label == "blocked, no question"


def test_blocked_with_an_unanswered_question_agrees(instance):
    sentence, label = _question_flag(instance, "blocked", UNANSWERED)
    assert (sentence, label) == ("", "")


def test_a_card_with_no_questions_outside_blocked_agrees(instance):
    sentence, label = _question_flag(instance, "todo", "Just prose.\n")
    assert (sentence, label) == ("", "")


def test_a_closed_row_is_never_asked_about_its_questions(instance):
    """A closed row owes nothing. A question left unanswered on something
    that already shipped was overtaken by events, not ignored."""
    for status in ("done", "abandoned"):
        assert _question_flag(instance, status, UNANSWERED) == ("", ""), status


def test_the_mismatch_never_moves_the_card(instance):
    """The whole point, and it is two claims, not one: the disagreement is
    actually DETECTED (the label fires), and the card stays where the
    owner put it regardless. An owner can block a card for a reason that
    lives nowhere in its prose — a person, a vendor, an upstream
    dependency — so the reporter's job is to say the two disagree, never
    to reconcile them. A test asserting only the second claim would pass
    just as happily on a card with no mismatch at all, so both are here."""
    _board(instance, [{"id": "c1", "title": "A card", "status": "blocked",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1", ANSWERED)
    cols = readers.amik(str(instance))["data"]["columns"]
    blocked = next(c for c in cols if c["status"] == "blocked")
    card = next(c for c in blocked["cards"] if c["id"] == "c1")
    assert card["question_flag_label"] == "blocked, no question"
    assert [c["id"] for c in blocked["cards"]] == ["c1"]


def test_the_older_contradiction_still_reports_alongside_it(instance):
    """Two reporters, because one pair cannot carry two disagreements.
    A row can owe a plan AND have a question waiting."""
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": "has-plan"}])
    _card_file(instance, "c1", UNANSWERED)
    cols = readers.amik(str(instance))["data"]["columns"]
    card = next(c for col in cols for c in col["cards"])
    assert card["conflict_label"] == "plan not named"
    assert card["question_flag_label"] == "question waiting"


# ── the question mismatch gets a face ──────────────────────────────────


def test_a_card_waiting_on_an_answer_says_so(client, instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "doing",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1", "## Questions\n\n### An open question\n")
    card = _card_html(client.get("/amik").text, "c1")
    # The chip's own text, not the block that also carries its tooltip:
    # "question waiting" is a substring of the sentence the tooltip
    # holds, so a membership check against the whole card would pass
    # even with an empty label.
    assert _chip_text(card, "akquestion") == "question waiting"


def test_a_card_that_agrees_carries_no_question_chip(client, instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1", "Just prose.\n")
    assert "akquestion" not in _card_html(client.get("/amik").text, "c1")


def test_both_chips_can_show_at_once(client, instance):
    """The two reporters are separate so that neither hides the other.
    A row can owe a plan AND have a question waiting, and the card has to
    say both."""
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": "has-plan"}])
    _card_file(instance, "c1", "## Questions\n\n### An open question\n")
    card = _card_html(client.get("/amik").text, "c1")
    assert "plan not named" in card
    assert _chip_text(card, "akquestion") == "question waiting"


# ── the modal offers one box per question ──────────────────────────────


def test_the_modal_block_carries_each_question(client, instance):
    """Derived server-side and rendered, never parsed in the browser —
    the page reads what the reader worked out and recomputes none of it.

    Checked against the rendered `data-heading` nodes, not a bare
    substring: the raw markdown already rides along in `.akraw` for the
    editor, so "First?" and "Answered." appear in the page regardless of
    whether this block renders anything at all."""
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1",
               "## Questions\n\n### First?\n\nAnswered.\n\n### Second?\n")
    detail = _detail_html(client, "c1")
    assert 'data-heading="First?"' in detail
    assert 'data-heading="Second?"' in detail
    first_block = detail.split('data-heading="First?"', 1)[1].split(
        "akqsrc", 1)[0]
    assert "Answered." in first_block


def test_a_question_block_says_which_are_waiting(client, instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1",
               "## Questions\n\n### First?\n\nAnswered.\n\n### Second?\n")
    detail = _detail_html(client, "c1")
    waiting = detail.split('data-answered="false"')
    assert len(waiting) == 2, "exactly one question is waiting"


def test_a_card_with_no_questions_renders_no_question_block(client, instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1", "Just prose.\n")
    assert "akqsrc" not in _detail_html(client, "c1")


def test_the_question_source_is_the_heading_not_an_index(client, instance):
    """The box posts its heading, because that is what the writer targets.
    An index would break the moment a question is added above it."""
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1", "## Questions\n\n### Only one?\n")
    detail = _detail_html(client, "c1")
    assert 'data-heading="Only one?"' in detail


# ── a duplicate heading is surfaced, never corrected ────────────────────


def test_two_questions_sharing_a_heading_are_surfaced(client, instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1",
               "## Questions\n\n### Same?\n\nOne.\n\n### Same?\n\nTwo.\n")
    card = _card_html(client.get("/amik").text, "c1")
    assert "akdup" in card


def test_distinct_headings_carry_no_duplicate_chip(client, instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1",
               "## Questions\n\n### First?\n\nOne.\n\n### Second?\n\nTwo.\n")
    assert "akdup" not in _card_html(client.get("/amik").text, "c1")


def test_a_heading_quoted_in_a_fence_is_not_a_duplicate(client, instance):
    """An answer that shows what a question looks like is not a second
    question. This holds by construction -- the flag counts what the
    reader counts, and the reader skips fenced lines -- but the rule is
    stated as law in the folder's guide, and a rule nothing tests is one
    refactor away from being false."""
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    _card_file(instance, "c1",
               "## Questions\n\n### Same?\n\nAsk it like this:\n\n"
               "```\n### Same?\n```\n")
    assert "akdup" not in _card_html(client.get("/amik").text, "c1")


def test_the_duplicate_is_not_corrected(instance):
    """Surfaced, never fixed. Which of the two was meant is the owner's
    call — the machine cannot know, and guessing would lose an answer."""
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    prose = "## Questions\n\n### Same?\n\nOne.\n\n### Same?\n\nTwo.\n"
    _card_file(instance, "c1", prose)
    readers.amik(str(instance))
    assert readers._card_prose(str(instance), "c1") == prose


# ── a card says which branch it was built on ───────────────────────────


def test_a_card_with_a_branch_shows_it(client, instance):
    """A realised branch is a fact, not an instruction — the icon stays,
    the name moves to the tooltip that carries it."""
    _board(instance, [{"id": "c1", "title": "A card", "status": "review",
                       "rank": 1, "planning": None, "branch": "card/c1"}])
    card = _card_html(client.get("/amik").text, "c1")
    assert 'class="chip akbranch tip"' in card
    assert 'data-tip="card/c1"' in card


def test_a_card_with_no_branch_shows_no_branch_chip(client, instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    assert "akbranch" not in _card_html(client.get("/amik").text, "c1")


def test_a_whitespace_only_branch_shows_no_branch_chip(client, instance):
    """The reader and the finalise queue share one predicate for what
    counts as a branch -- a whitespace-only string is not a name either
    of them acts on, and the card must not show a chip the finalise
    queue would never list."""
    _board(instance, [{"id": "c1", "title": "A card", "status": "review",
                       "rank": 1, "planning": None, "branch": "   "}])
    assert "akbranch" not in _card_html(client.get("/amik").text, "c1")


# ── the design-pass flag reaches the modal ─────────────────────────────


def test_a_card_that_wants_a_design_pass_says_so(client, instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None,
                       "requires_prototype": True}])
    assert 'data-requires-prototype="true"' in \
        _detail_html(client, "c1")


def test_a_card_that_does_not_says_so_too(client, instance):
    """The modal needs an answer either way — a toggle with no state
    reads as off, which is a claim the card never made."""
    _board(instance, [{"id": "c1", "title": "A card", "status": "todo",
                       "rank": 1, "planning": None}])
    assert 'data-requires-prototype="false"' in \
        _detail_html(client, "c1")


# ── a card with a prototype links to it ─────────────────────────────────


def _open_fn():
    """The body of amik.js's own `fill(b)` — everything the modal shows
    for one card — so a test can prove the modal actually WIRES something
    rather than merely that a slot for it exists, the gap the original
    version of this test missed.

    `fill` and `open` are separate because a card that changed underneath
    a reader is refilled in place, and `showModal()` on an open dialog
    throws. Almost every test here is about the filling; the one that is
    about OPENING takes `_opening_fn` below.
    """
    js = _js("amik.js")
    return js.split("function fill(b) {", 1)[1].split(
        "\n  }\n\n  function open(b)", 1)[0]


def _opening_fn():
    """The body of `open(b)` — what happens on top of a fill when a card
    is actually being put on screen: the dialog, and where focus lands."""
    js = _js("amik.js")
    return js.split("function open(b) {", 1)[1].split("\n  }\n", 1)[0]


def test_a_card_with_a_prototype_reaches_the_modal(client, instance):
    """The original assertion here read `.akdata`, the hidden block —
    its own docstring says so — so it proved the href was RENDERED, not
    that anything links to it, and it stayed green while the link sat
    unreachable behind `[hidden]` with nothing to lift it out.

    This one checks the two things that together prove it reaches the
    dialog: a real slot exists inside `#akdlg` for the link to land in,
    and `open()` itself is what fills that slot from `.akproto`. Neither
    alone would catch the original bug — a slot with nothing wiring it
    is exactly what the hidden block was."""
    import os
    _board(instance, [{"id": "c1", "title": "A card", "status": "doing",
                       "rank": 1, "planning": None}])
    os.makedirs(os.path.join(str(instance), "amik", "prototypes", "c1"))
    with open(os.path.join(str(instance), "amik", "prototypes", "c1",
                           "index.html"), "w") as f:
        f.write("<html></html>")
    body = client.get("/amik").text
    dlg = body.split('id="akdlg"', 1)[1].split("</dialog>", 1)[0]
    assert 'id="akf-protolink"' in dlg              # the modal's own socket
    open_fn = _open_fn()
    assert "protoLink.hidden = !proto;" in open_fn
    assert "querySelector('.akproto a')" in open_fn  # what it fills it from
    assert "protoLink.href = proto.getAttribute('href');" in open_fn
    assert "/amik/cards/c1/prototype" in _detail_html(client, "c1")   # the source


def test_a_card_without_one_leaves_no_stale_link(client, instance):
    """A card with no prototype has nothing in its own data block to read
    — and `open()`'s own fallback REMOVES the href rather than leaving it
    alone, which is what stops the previously opened card's link surviving
    into this one behind a `hidden` attribute."""
    _board(instance, [{"id": "c1", "title": "A card", "status": "doing",
                       "rank": 1, "planning": None}])
    body = client.get("/amik").text
    assert "/amik/prototype/" not in \
        _detail_html(client, "c1")
    open_fn = _open_fn()
    assert "else { protoLink.removeAttribute('href'); }" in open_fn


# ── a prototype says so on the card face ───────────────────────────────


def _with_prototype(instance, **extra):
    """A card whose prototype directory exists. The flag is derived from
    the disk, so a fixture that only writes the row proves nothing."""
    import os
    row = {"id": "c1", "title": "A card", "status": "doing", "rank": 1,
           "planning": None}
    row.update(extra)
    _board(instance, [row])
    os.makedirs(os.path.join(str(instance), "amik", "prototypes", "c1"))


def test_a_card_with_a_prototype_wears_a_chip(client, instance):
    """A realised prototype is a fact, not an instruction — the icon
    stays, the word moves to the tooltip that carries it."""
    _with_prototype(instance)
    card = _card_html(client.get("/amik").text, "c1")
    assert 'class="chip akhasproto tip"' in card
    chip = card.split('class="chip akhasproto', 1)[1].split("</span>", 1)[0]
    assert 'data-tip="' in chip


def test_the_chip_is_not_a_link(client, instance):
    """Inert on purpose: the modal holds the one way in. A chip that
    navigated would be a second door, and a card face is also a drag
    handle -- an anchor inside it fights the drag."""
    _with_prototype(instance)
    card = _card_html(client.get("/amik").text, "c1")
    chip = card.split('class="chip akhasproto', 1)[1].split("</span>", 1)[0]
    assert "href" not in chip


def test_a_prototype_alone_opens_the_chip_row(client, instance):
    """The wrapper is gated on an enumeration of what makes a card
    distinctive, and a chip added without widening that gate renders
    nowhere. This gate has already been missed once."""
    _with_prototype(instance)
    card = _card_html(client.get("/amik").text, "c1")
    assert 'class="akchips"' in card


def test_a_card_with_no_prototype_shows_no_chip(client, instance):
    _board(instance, [{"id": "c1", "title": "A card", "status": "doing",
                       "rank": 1, "planning": None}])
    assert "akhasproto" not in _card_html(client.get("/amik").text, "c1")


# ── the question tabs ──────────────────────────────────────────────────


def test_a_card_with_no_questions_gets_no_tab_strip():
    """Most cards ask nothing, and `Details` alone is a tab that cannot be
    left. The strip ships hidden and the modal only fills it when the card
    has questions, so the common card renders exactly as it did."""
    page = open(os.path.join(_here(), "templates", "board.html")).read()
    assert 'id="aktabs"' in page
    assert 'role="tablist"' in page
    strip = page[page.index('id="aktabs"'):page.index('id="aktabs"') + 200]
    assert "hidden" in strip
    js = _js()
    # `extra` is questions plus an outcome: the strip is worth having once
    # there is somewhere to go, and Details alone is a tab that cannot be
    # left.
    assert "tabs.hidden = extra === 0;" in js
    assert "b.querySelector('.akoutsrc') ? 1 : 0" in js


def test_the_modal_opens_on_the_first_question_still_waiting():
    """Landing on the fields is how the answer box got missed: it sat
    under an editor tall enough to hide it. A card with nothing waiting is
    there to be read, so that one opens on Details."""
    js = _js()
    assert "node.dataset.answered === 'false'" in js
    assert "showTab(waiting < 0 ? 0 : waiting + 1);" in js


def test_every_answer_box_stays_under_the_list_the_save_path_reads():
    """The panes live inside `#akqlist` so the save path goes on reading
    every `.akqbox` under it without knowing tabs exist. Building them
    anywhere else would silently drop the answers on the hidden tabs."""
    js = _js()
    assert "qList.appendChild(wrap);" in js
    assert "qList.querySelectorAll('.akqbox')" in js


def test_a_built_prototype_cannot_be_toggled_away(client, instance):
    """Turning `requires_prototype` off while the directory exists orphans
    it: only the sweep over CLOSED cards looks for stray prototypes, so an
    open card that dropped the flag would leave one nothing ever reports.
    Once it is built the control stops being a toggle and becomes the link
    to what it built — the button goes, its state stays, because the save
    posts that state and the halt is forced from it."""
    import os
    _board(instance, [{"id": "c1", "title": "A card", "status": "doing",
                       "rank": 1, "planning": None,
                       "requires_prototype": True}])
    os.makedirs(os.path.join(str(instance), "amik", "prototypes", "c1"))
    with open(os.path.join(str(instance), "amik", "prototypes", "c1",
                           "index.html"), "w") as f:
        f.write("<html></html>")
    client.get("/amik")
    open_fn = _open_fn()
    assert "f.prototype.hidden = !!proto;" in open_fn
    # The link is a sibling of the button, never nested inside it.
    dlg = client.get("/amik").text.split('id="akdlg"', 1)[1]
    row = dlg.split('class="akftoggles"', 1)[1].split("</div>", 1)[0]
    assert 'id="akf-protolink"' in row
    assert "<a" in row.split('id="akf-prototype"', 1)[1]
    assert "<button" not in row.split('id="akf-protolink"', 1)[1]


def test_a_card_that_only_asked_for_a_prototype_keeps_its_toggle():
    """Changing your mind before the work exists is a decision, not an
    orphan — the lock keys off the directory being there, never off the
    flag being set."""
    open_fn = _open_fn()
    assert "var proto = b.querySelector('.akproto a');" in open_fn
    assert "requiresPrototype" not in open_fn.split("protoLink.hidden", 1)[1]


def test_the_modal_focuses_what_the_card_was_opened_for():
    """`showModal` focuses the first focusable thing it finds, which since
    the tabs arrived is the Details tab — so a card opening on a question
    drew a focus ring around a tab that was not even the selected one.
    Focus belongs on the answer box on a question, and on the pencil
    otherwise — the title it used to land on now opens hidden behind
    view mode, and focusing a hidden field focuses nothing at all."""
    open_fn = _opening_fn()
    assert "qList.querySelector('.akq:not([hidden]) .akqbox')" in open_fn
    assert "(pane || editBtn).focus();" in open_fn
    assert open_fn.index("dlg.showModal()") < open_fn.index(".focus()")


def test_a_question_pane_carries_no_waiting_pill():
    """Same rule as the modal's status pill: a pill restating what you
    already know is noise. The question's own TAB carries a dot when it is
    unanswered, and the board card carries the chip — a third copy inside
    the pane you reached by clicking that tab says nothing the other two
    did not."""
    build = _js().split("function buildQuestions(b) {", 1)[1] \
                 .split("\n  }", 1)[0]
    # The mechanism, not the word: the pill was a chip appended to the
    # heading, and the comment saying it is gone contains "waiting"
    # itself, so matching on that matches the explanation.
    assert "chip akquestion" not in build
    assert "head.appendChild" not in build
    # the dot is what replaced it, and it is built from the same field
    assert "node.dataset.answered === 'false'" in _js()


def test_every_control_the_script_hides_can_ACTUALLY_hide():
    """One enumeration, replacing six copies of the same assertion.

    A class that sets `display` beats the browser's own `[hidden]` rule,
    so `el.hidden = true` does nothing and the control stays on screen.
    This is not a styling preference: "Discard the work" showed on every
    card, including every card with no branch to discard, and the New
    area box showed on all of them.

    It has been paid for five times -- `.akpencil`, `.akftoggle`,
    `.akfield`, `.akq` and `.btn` -- which is what makes it an
    enumeration, and this board's own law about enumerations is to
    assume something falls off. The list cannot be derived: these are
    hidden by the script at runtime, not by a `hidden` attribute in a
    template, so there is nothing static to walk. Add to it whenever a
    rule sets `display` on something the script hides.
    """
    css = _css()
    for selector in (".akpencil", ".akftoggle", ".akfield", ".akq", ".btn",
                     ".akqlist", ".akdata"):
        assert selector + "[hidden]" in css, selector
