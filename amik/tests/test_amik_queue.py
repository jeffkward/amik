"""Which card an agent would take next, and why not the others.

Read-only. Nothing here dispatches anything, moves a card, or writes a
file — it answers a question the owner can also answer by looking, which
is the point: the queue and the board must never disagree.
"""
import json
import os

from amik.core import board as readers
from tests.test_amik_page import _card_file


def _board(root, rows):
    path = os.path.join(str(root), "amik", "board.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return path


def _row(id_, rank, planning, status="ready", **extra):
    return {"id": id_, "title": "Card " + id_, "status": status,
            "rank": rank, "planning": planning, **extra}


def test_it_takes_the_lowest_ranked_eligible_card(instance):
    """Written in reverse file order on purpose. The queue does not sort
    — it walks the `ready` list exactly as `amik()` hands it over, already
    ordered by `rank`. Writing the rows in rank order left the ordering
    untested: file order and rank order agreed, so a queue that just took
    the first row would have passed too. Reversed, the two disagree —
    only a queue that honours `amik()`'s rank order still picks "a"."""
    _board(instance, [_row("b", 2, "has-plan"),
                      _row("a", 1, "has-plan")])
    data = readers.amik_queue(str(instance))["data"]
    assert data["take"]["id"] == "a"


def test_rank_one_is_passed_over_when_it_does_not_qualify(instance):
    """Rank orders the column, but the ladder decides eligibility. The
    next one down that qualifies is taken, and the skip is named."""
    _board(instance, [_row("a", 1, "needs-brainstorm"),
                      _row("b", 2, "has-plan")])
    data = readers.amik_queue(str(instance))["data"]
    assert data["take"]["id"] == "b"
    assert [s["id"] for s in data["skipped"]] == ["a"]


def test_cards_outside_ready_are_not_in_the_queue_at_all(instance):
    """Only Ready is a queue. A todo card with a perfect rung is not
    waiting to be worked — the owner has not pulled it."""
    _board(instance, [_row("a", 1, "has-plan", status="todo"),
                      _row("b", 1, "has-plan", status="doing"),
                      _row("c", 1, "has-plan", status="done")])
    data = readers.amik_queue(str(instance))["data"]
    assert data["take"] is None
    assert data["skipped"] == []


def test_the_blocking_rungs_are_pinned():
    """The one rung that means something is still OWED. Everything else
    in Ready is takeable, because the column already said go — so this
    is the whole of what can hold a card back."""
    assert readers.AMIK_BLOCKS_READY == ("needs-brainstorm",)


def test_a_card_with_no_rung_is_takeable(instance):
    """Ready is the declaration. An absent rung is unclassified, and
    unclassified is not a claim that anything is owed — the owner already
    said go by dragging it here."""
    _board(instance, [_row("a", 1, None)])
    assert readers.amik_queue(str(instance))["data"]["take"]["id"] == "a"


def test_a_clearing_rung_is_takeable(instance):
    _board(instance, [_row("a", 1, "has-plan")])
    data = readers.amik_queue(str(instance))["data"]
    assert data["take"] is not None
    assert data["skipped"] == []


def test_an_open_question_holds_a_ready_card(instance):
    """The chip says the owner is blocking this. A queue that took the
    card anyway would make the chip a lie."""
    _board(instance, [_row("a", 1, None)])
    _card_file(instance, "a", "## Questions\n\n### Still open?\n")
    data = readers.amik_queue(str(instance))["data"]
    assert data["take"] is None
    assert [s["id"] for s in data["skipped"]] == ["a"]
    assert "question" in data["skipped"][0]["reason"].lower()


def test_an_answered_question_does_not_hold_it(instance):
    _board(instance, [_row("a", 1, None)])
    _card_file(instance, "a", "## Questions\n\n### Settled?\n\nYes.\n")
    assert readers.amik_queue(str(instance))["data"]["take"]["id"] == "a"


def test_n_a_is_an_answer(instance):
    """An escape hatch the owner asked for, and it already works: any
    non-empty prose answers. It keeps the record that a fork was seen and
    dismissed, which deleting the question would erase."""
    for reply in ("n/a", "skip", "does not matter"):
        _board(instance, [_row("a", 1, None)])
        _card_file(instance, "a", f"## Questions\n\n### Open?\n\n{reply}\n")
        assert readers.amik_queue(str(instance))["data"]["take"] is not None, reply


def test_one_open_question_among_several_still_holds_it(instance):
    _board(instance, [_row("a", 1, None)])
    _card_file(instance, "a",
               "## Questions\n\n### First?\n\nYes.\n\n### Second?\n")
    assert readers.amik_queue(str(instance))["data"]["take"] is None


def test_a_held_card_is_never_moved(instance):
    """Skipped and NAMED, never relocated — the owner may be mid-answer,
    and a card yanked out from under them is worse than a chip."""
    _board(instance, [_row("a", 1, None)])
    _card_file(instance, "a", "## Questions\n\n### Open?\n")
    readers.amik_queue(str(instance))
    cols = readers.amik(str(instance))["data"]["columns"]
    ready = next(c for c in cols if c["status"] == "ready")
    assert [c["id"] for c in ready["cards"]] == ["a"]


def test_the_cards_behind_the_take_are_queued(instance):
    """They are the owner's priority queue, which is most of the point of
    having one — not an edge case."""
    _board(instance, [_row("a", 1, None), _row("b", 2, None),
                      _row("c", 3, "has-plan")])
    data = readers.amik_queue(str(instance))["data"]
    assert data["take"]["id"] == "a"
    assert [q["id"] for q in data["queued"]] == ["b", "c"]
    assert data["skipped"] == []


def test_queued_keeps_rank_order(instance):
    _board(instance, [_row("c", 3, None), _row("a", 1, None),
                      _row("b", 2, None)])
    data = readers.amik_queue(str(instance))["data"]
    assert data["take"]["id"] == "a"
    assert [q["id"] for q in data["queued"]] == ["b", "c"]


def test_a_blocked_card_is_skipped_not_queued(instance):
    """The two lists mean different things: queued is waiting its turn,
    skipped is not takeable at all. A card in both would be a lie."""
    _board(instance, [_row("a", 1, None), _row("b", 2, "needs-brainstorm")])
    data = readers.amik_queue(str(instance))["data"]
    assert [q["id"] for q in data["queued"]] == []
    assert [s["id"] for s in data["skipped"]] == ["b"]


def test_every_ready_card_lands_in_exactly_one_bucket(instance):
    """The report must account for the whole column — the gap this
    replaces was a card that appeared in neither."""
    rows = [_row("a", 1, None), _row("b", 2, "has-plan"),
            _row("c", 3, "needs-brainstorm"), _row("d", 4, "has-plan")]
    _board(instance, rows)
    data = readers.amik_queue(str(instance))["data"]
    seen = ([data["take"]["id"]] + [q["id"] for q in data["queued"]]
            + [s["id"] for s in data["skipped"]])
    assert sorted(seen) == ["a", "b", "c", "d"]
    assert len(seen) == len(set(seen)), "a card appeared twice"


def test_no_board_is_a_refusal_not_a_raise(instance):
    res = readers.amik_queue(str(instance))
    assert res["ok"] is False


def test_the_queue_never_moves_anything(instance):
    """A forward guard, not proof a write was attempted and survived: the
    read path here has no write call to trigger in the first place, so
    this pins a wrong nobody has committed yet. It is meant to stay green
    forever, and it is meant to redden the day a future change gives the
    queue a reason to touch the board on disk."""
    path = _board(instance, [_row("a", 1, None)])
    before = open(path, "rb").read()
    readers.amik_queue(str(instance))
    assert open(path, "rb").read() == before


def test_the_queue_agrees_with_the_board_it_was_derived_from():
    """A cross-check against the board itself, not a fixed count — the
    live board is the owner's, and pinning a number or an id would break
    the moment they classify a card. Both sides here are computed from
    `amik()`, independently of the queue's own control flow: the set of
    Ready ids held by a rung or an open question must equal what the
    queue calls `skipped`, and every Ready id the gate does not hold back
    must land exactly once across `take` and `queued`. That still reddens
    if the queue mis-orders its checks or drops a card, on whatever the
    board happens to hold today.

    The gate is the reason this cannot simply be "every unheld Ready
    card". A halt pauses everything ranked below it, so the expected set
    runs down the column and stops at the first halted card — including
    that card, which is queued before its own gate closes — and a halt on
    a card sitting in Review holds the whole column before Ready is
    walked at all. Held cards are still reported as `skipped` while
    paused, which is why the two halves are computed separately."""
    from conftest import INSTANCE as ROOT
    board = readers.amik(ROOT)["data"]

    def column(status):
        return next((c["cards"] for c in board["columns"]
                     if c["status"] == status), [])

    ready, review = column("ready"), column("review")

    def held(card):
        return (card.get("planning") in readers.AMIK_BLOCKS_READY
                or bool(card.get("unanswered")))

    expected = []
    if not any(c.get("halt") for c in review):
        for card in ready:
            if not held(card):
                expected.append(card["id"])
            if card.get("halt"):
                break

    data = readers.amik_queue(ROOT)["data"]
    assert {s["id"] for s in data["skipped"]} == {c["id"] for c in ready
                                                  if held(c)}
    takeable = ([data["take"]["id"]] if data["take"] else []) + \
        [q["id"] for q in data["queued"]]
    assert takeable == expected
    assert len(takeable) == len(set(takeable)), "a card appeared twice"


# ── what the owner has signed off and an agent still owes ──────────────


def test_a_done_card_with_a_branch_is_waiting_to_be_finalised(instance):
    _board(instance, [dict(_row("a", 1, None, status="done"),
                           branch="card/a")])
    data = readers.amik_finalise(str(instance))["data"]
    assert [c["id"] for c in data] == ["a"]
    assert data[0]["branch"] == "card/a"


def test_a_done_card_with_no_branch_is_already_finished(instance):
    """Deleting the branch is what marks the work shipped, so a done card
    without one has nothing left owing."""
    _board(instance, [_row("a", 1, None, status="done")])
    assert readers.amik_finalise(str(instance))["data"] == []


def test_a_card_still_in_review_is_not_waiting(instance):
    """Done is the owner's signal. A card in review carries a branch and
    is not finished — but nobody has said to merge it."""
    _board(instance, [dict(_row("a", 1, None, status="review"),
                           branch="card/a")])
    assert readers.amik_finalise(str(instance))["data"] == []


def test_no_board_is_a_refusal_for_the_finalise_queue(instance):
    assert readers.amik_finalise(str(instance))["ok"] is False


def test_a_whitespace_only_branch_is_not_waiting_to_be_finalised(instance):
    """A row can carry a branch that is only whitespace -- a stray hand
    edit, never a real name. The finalise queue and the card chip share
    one predicate for what counts as a branch, so this must not list."""
    _board(instance, [dict(_row("a", 1, None, status="done"),
                           branch="   ")])
    assert readers.amik_finalise(str(instance))["data"] == []


def test_it_runs_no_git(instance, monkeypatch):
    """The face runs no git. Whether the branch still exists is the
    agent's to reconcile — a face that shelled out would be making a
    claim about a tree it does not necessarily share.

    Patched at `subprocess.Popen`, not `subprocess.run`: `run`, `call`,
    `check_call` and `check_output` all resolve `Popen` by that global
    name inside the `subprocess` module, so one stub covers every way
    to shell out through it and cannot rot when a fifth helper is added.
    `os.system` and `os.popen` are a separate path to a shell and are
    stubbed alongside it."""
    import os
    import subprocess
    _board(instance, [dict(_row("a", 1, None, status="done"),
                           branch="card/does-not-exist")])
    called = []
    monkeypatch.setattr(subprocess, "Popen",
                        lambda *a, **k: called.append(("Popen", a)))
    monkeypatch.setattr(os, "system", lambda *a, **k: called.append(
        ("system", a)))
    monkeypatch.setattr(os, "popen", lambda *a, **k: called.append(
        ("popen", a)))
    data = readers.amik_finalise(str(instance))["data"]
    assert called == []
    assert data[0]["branch"] == "card/does-not-exist"


# ── the prototypes an agent owes a deletion ────────────────────────────


def _proto_dir(root, card_id):
    import os
    path = os.path.join(str(root), "amik", "prototypes", card_id)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "index.html"), "w") as f:
        f.write("<html></html>")
    return path


def test_a_done_card_with_a_prototype_is_owed_a_deletion(instance):
    _board(instance, [_row("a", 1, None, status="done")])
    _proto_dir(instance, "a")
    data = readers.amik_prototypes(str(instance))["data"]
    assert [c["id"] for c in data] == ["a"]


def test_a_done_card_with_no_prototype_owes_nothing(instance):
    _board(instance, [_row("a", 1, None, status="done")])
    assert readers.amik_prototypes(str(instance))["data"] == []


def test_it_deletes_nothing(instance):
    """Naming the chore is what makes it rememberable. Performing it is
    an agent's, for the same reason the face does not merge a branch."""
    import os
    _board(instance, [_row("a", 1, None, status="done")])
    path = _proto_dir(instance, "a")
    readers.amik_prototypes(str(instance))
    assert os.path.isdir(path)


def test_no_board_is_a_refusal_for_the_prototype_sweep(instance):
    assert readers.amik_prototypes(str(instance))["ok"] is False


def test_a_card_in_flight_keeps_its_prototype(instance):
    for status in ("ready", "doing", "blocked", "review"):
        _board(instance, [_row("a", 1, None, status=status)])
        _proto_dir(instance, "a")
        assert readers.amik_prototypes(str(instance))["data"] == [], status


# ── what an ABANDONED card owes, and what it does not ───────────────────
#
# Ruled by the owner: keep the branch ("it's cheap"), sweep the prototype
# ("yes"). The two closing queues therefore scope DIFFERENTLY on purpose,
# and the asymmetry is one word in each — widening `amik_finalise` to
# AMIK_CLOSED would hand an agent "delete an unmerged branch", a
# destructive verb on work nobody reviewed, and nothing would fail.

def test_an_abandoned_card_s_prototype_is_swept(instance):
    """A design pass is finished the moment a card leaves play, ship or
    not, so its directory is owed a deletion either way."""
    _board(instance, [_row("a", 1, None, status="abandoned")])
    _proto_dir(instance, "a")
    assert [c["id"] for c in
            readers.amik_prototypes(str(instance))["data"]] == ["a"]


def test_an_abandoned_card_s_branch_is_NOT_owed_a_merge(instance):
    """The half that must not follow. A branch is kept regardless of how
    a card closed, so no agent is ever handed an unmerged branch to
    delete — the owner's reason was that keeping it is cheap."""
    _board(instance, [dict(_row("a", 1, None, status="abandoned"),
                           branch="card/a")])
    assert readers.amik_finalise(str(instance))["data"] == []


def test_the_two_queues_disagree_about_an_abandoned_card(instance):
    """Stated as one assertion, because the point is the DIFFERENCE. A
    change that made them agree would pass both tests above only if it
    broke one of them, and this says which direction is wrong."""
    _board(instance, [dict(_row("a", 1, None, status="abandoned"),
                           branch="card/a"),
                      dict(_row("b", 1, None, status="done"),
                           branch="card/b")])
    _proto_dir(instance, "a")
    _proto_dir(instance, "b")
    assert sorted(c["id"] for c in
                  readers.amik_prototypes(str(instance))["data"]) == ["a", "b"]
    assert [c["id"] for c in
            readers.amik_finalise(str(instance))["data"]] == ["b"]


# ── a halt pauses the QUEUE, not just its own card ──────────────────────
#
# A gated card is the owner's barrier. Working past it would build later
# cards on master while the gate's own work sits unmerged on a branch —
# a foundation that is not there. Stopping is correctness, not tidiness,
# and it makes `rank` a scheduling primitive: a halt at rank 3 parks
# everything from 4 down until they have looked.

def test_a_halted_card_is_still_the_take(instance):
    """It is the next work to do. The halt is about what comes AFTER."""
    _board(instance, [dict(_row("a", 1, None), halt=True),
                      _row("b", 2, None)])
    q = readers.amik_queue(str(instance))["data"]
    assert q["take"]["id"] == "a"


def test_nothing_behind_a_halt_is_queued(instance):
    _board(instance, [dict(_row("a", 1, None), halt=True),
                      _row("b", 2, None), _row("c", 3, None)])
    q = readers.amik_queue(str(instance))["data"]
    assert q["queued"] == []
    assert q["halted"]["id"] == "a"


def test_cards_before_a_halt_are_queued_normally(instance):
    _board(instance, [_row("a", 1, None), _row("b", 2, None),
                      dict(_row("c", 3, None), halt=True),
                      _row("d", 4, None)])
    q = readers.amik_queue(str(instance))["data"]
    assert q["take"]["id"] == "a"
    assert [c["id"] for c in q["queued"]] == ["b", "c"]
    assert q["halted"]["id"] == "c"


def test_no_halt_means_no_halted_card(instance):
    _board(instance, [_row("a", 1, None), _row("b", 2, None)])
    q = readers.amik_queue(str(instance))["data"]
    assert q["halted"] is None
    assert [c["id"] for c in q["queued"]] == ["b"]


def test_a_skipped_card_does_not_halt_the_queue(instance):
    """A card held by its own rung is stuck; the queue is not. Only a
    declared halt stops the ones behind it."""
    _board(instance, [_row("a", 1, "needs-brainstorm"),
                      _row("b", 2, None), _row("c", 3, None)])
    q = readers.amik_queue(str(instance))["data"]
    assert q["take"]["id"] == "b"
    assert [c["id"] for c in q["queued"]] == ["c"]
    assert q["halted"] is None


# ── the gate is Review, because that is where clearing it happens ──────
#
# A halt on a Ready card would evaporate the instant an agent does the
# very thing it exists to gate: build the card and move it to Review.
# The gate has to live where the built-but-unmerged work actually sits,
# or it opens at exactly the moment it is meant to bite.

def test_a_halted_card_in_review_pauses_the_whole_queue(instance):
    """Regression: reading only the Ready column made a Review halt
    invisible, so the queue kept handing out work built on top of an
    unmerged foundation the moment the gated card left Ready."""
    _board(instance, [dict(_row("z", 1, None, status="review"), halt=True),
                      _row("a", 1, None), _row("b", 2, None)])
    q = readers.amik_queue(str(instance))["data"]
    assert q["take"] is None
    assert q["queued"] == []
    assert q["halted"]["id"] == "z"


def test_moving_the_halted_card_out_of_review_resumes_the_queue(instance):
    """Resume is derived, never a button: nothing here is told the gate
    cleared, it just stops finding a halted card in Review once the
    owner has dragged it anywhere else."""
    _board(instance, [dict(_row("z", 1, None, status="done"), halt=True),
                      _row("a", 1, None), _row("b", 2, None)])
    q = readers.amik_queue(str(instance))["data"]
    assert q["take"]["id"] == "a"
    assert [c["id"] for c in q["queued"]] == ["b"]
    assert q["halted"] is None


def test_a_ready_card_can_be_both_skipped_and_the_halt(instance):
    """A rung-blocked card is still a barrier if the owner marked it one
    — being stuck is not the same as being harmless. It must show up
    both ways, and nothing behind it may be queued."""
    _board(instance, [dict(_row("a", 1, "needs-brainstorm"), halt=True),
                      _row("b", 2, None), _row("c", 3, None)])
    q = readers.amik_queue(str(instance))["data"]
    assert [s["id"] for s in q["skipped"]] == ["a"]
    assert q["halted"]["id"] == "a"
    assert q["queued"] == []


def test_a_review_halt_still_reports_readys_own_skips(instance):
    """Pausing the queue must not blind the owner to why a Ready card is
    separately stuck on its own rung — those are two different facts."""
    _board(instance, [dict(_row("z", 1, None, status="review"), halt=True),
                      _row("a", 1, "needs-brainstorm")])
    q = readers.amik_queue(str(instance))["data"]
    assert [s["id"] for s in q["skipped"]] == ["a"]
    assert q["halted"]["id"] == "z"
