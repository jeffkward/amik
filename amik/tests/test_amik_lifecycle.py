"""Several cards, moving through a board, one door call at a time.

Everything else in this suite tests a law against a board written
straight to disk: a hand-made snapshot, one operation, one assertion.
That proves each law. It does not prove the WIRING between the doors
and the laws, and an audit on 2026-09-20 found what that costs -- three
tests in the whole suite make more than two mutating calls, and every
one of them acts on a single card. No test anywhere moved two cards
through anything.

So this file is the other shape. It plays a realistic sequence through
the real doors and checks, after EVERY step, the two invariants that
every view assumes and nothing was asserting across a sequence:

  * every column is ranked 1..n with no gaps and no repeats
  * every row is in exactly one column, and none has gone missing

and then the queue's own answer, which is what the loop acts on.

Renumbering is the invariant most likely to rot, because it is bulk: a
single drag rewrites a whole column, and a gap left behind is invisible
until something sorts by it.
"""

import os

import pytest

from amik.core import board, edit

TOML = ('verify = "true"\narmed = true\ntrunk = "main"\n'
        '[agent]\ncommand = "an-agent"\n')


@pytest.fixture()
def desk(instance):
    """A board with nothing on it, and a project that declares itself."""
    from conftest import write_board
    root = write_board(instance, [])
    with open(os.path.join(root, "amik", "amik.toml"), "w",
              encoding="utf-8") as f:
        f.write(TOML)
    return root


# ── the invariants, checked after every single step ─────────────────

def _columns(root):
    data = board.amik(root)
    assert data["ok"], data
    return {c["status"]: [r["id"] for r in c["cards"]]
            for c in data["data"]["columns"]}


def _check(root, step):
    """Contiguity and completeness, named by the step that broke them."""
    data = board.amik(root)
    assert data["ok"], (step, data)
    seen = []
    for col in data["data"]["columns"]:
        ranks = [r.get("rank") for r in col["cards"]]
        assert ranks == list(range(1, len(ranks) + 1)), \
            "{}: {} is ranked {}".format(step, col["status"], ranks)
        assert col["count"] == len(col["cards"]), step
        seen += [r["id"] for r in col["cards"]]
    assert len(seen) == len(set(seen)), "{}: a card is in two columns".format(step)
    assert len(seen) == data["data"]["total"], \
        "{}: a row is not in any column".format(step)
    return seen


def _take(root):
    q = board.amik_queue(root)
    assert q["ok"], q
    return (q["data"]["take"] or {}).get("id")


def _skipped(root):
    q = board.amik_queue(root)
    return {s["id"]: s["reason"] for s in q["data"]["skipped"]}


# ── the run ─────────────────────────────────────────────────────────

def test_four_cards_through_a_whole_board(desk):
    """The long one. Every assertion here is about a card's state AFTER
    a door call, never about a row somebody wrote by hand."""
    root = desk

    # ── they arrive in Inbox, newest on top ──────────────────────────
    ids = []
    for title in ("Cache the search index", "Rename the export button",
                  "Split the settings page", "Retry failed uploads"):
        res = edit.create(root, title, by="user")
        assert res["ok"], res
        ids.append(res["data"]["id"])
        _check(root, "create " + title)
    cache, rename, split, retry = ids
    # A new idea lands at the TOP of Inbox, so the order is reversed.
    assert _columns(root)["inbox"] == [retry, split, rename, cache]
    assert _take(root) is None, "nothing is in Ready yet"

    # ── triage: two to To-Do, one shelved, one abandoned ─────────────
    assert edit.move(root, cache, "todo", 0, by="user")["ok"]
    _check(root, "cache to todo")
    assert edit.move(root, rename, "todo", 1, by="user")["ok"]
    _check(root, "rename to todo")
    assert _columns(root)["todo"] == [cache, rename]
    # The column Inbox LEFT closes its gap. This is the assertion the
    # suite never made across a sequence: two removals from one column,
    # and it is still 1..n afterwards.
    assert _columns(root)["inbox"] == [retry, split]

    assert edit.move(root, split, "someday", 0, by="user")["ok"]
    _check(root, "split shelved")
    assert _take(root) is None, "someday is not a queue"

    # ── the owner pulls one to Ready ─────────────────────────────────
    assert edit.move(root, cache, "ready", 0, by="user")["ok"]
    _check(root, "cache pulled to ready")
    assert _take(root) == cache, "the pull did not reach the queue"
    assert _columns(root)["todo"] == [rename], "todo did not close its gap"

    # ── a question holds it, even from Ready ─────────────────────────
    assert edit.ask(root, cache, "Which index?", by="agent")["ok"]
    _check(root, "question asked")
    assert _take(root) is None, "an unanswered question did not hold the card"
    assert "question" in _skipped(root)[cache]

    # ── answering releases it ────────────────────────────────────────
    prose = board._card_prose(root, cache)
    answered = prose.replace("### Which index?\n",
                             "### Which index?\n\nThe inverted one.\n")
    assert edit.update(root, cache, {"body": answered}, by="user")["ok"]
    _check(root, "question answered")
    assert _take(root) == cache, "answering did not release the card"

    # ── a second card joins Ready behind it ──────────────────────────
    assert edit.move(root, rename, "ready", 1, by="user")["ok"]
    _check(root, "rename to ready")
    assert _columns(root)["ready"] == [cache, rename]
    assert _take(root) == cache, "the take is the TOP of Ready, not the newest"

    # ── the loop takes the top one ───────────────────────────────────
    assert edit.move(root, cache, "doing", 0, by="amik")["ok"]
    _check(root, "cache to doing")
    assert _take(root) == rename, "the next card did not become the take"

    # ── it halts itself into Review, and pauses what is below ────────
    assert edit.record_outcome(root, cache, "Verify failed on three tests.",
                               model="a-model", by="agent")["ok"]
    assert edit.update(root, cache, {"halt": True}, by="agent")["ok"]
    assert edit.move(root, cache, "review", 0, by="agent")["ok"]
    _check(root, "cache halted into review")
    assert _take(root) is None, "a halt did not pause the queue"
    q = board.amik_queue(root)
    assert (q["data"]["halted"] or {}).get("id") == cache, \
        "the queue does not name the card that paused it"

    # ── the owner clears the halt, and the queue resumes ─────────────
    assert edit.update(root, cache, {"halt": False}, by="user")["ok"]
    _check(root, "halt cleared")
    assert _take(root) == rename, "clearing the halt did not resume the queue"

    # ── the halted card closes; the other is abandoned ───────────────
    assert edit.move(root, cache, "done", 0, by="user")["ok"]
    _check(root, "cache done")
    assert edit.move(root, rename, "abandoned", 0, by="user")["ok"]
    _check(root, "rename abandoned")
    assert _take(root) is None, "an abandoned card is not work"

    # ── and the board still accounts for every card ──────────────────
    seen = _check(root, "the end")
    assert sorted(seen) == sorted(ids)
    cols = _columns(root)
    assert cols["done"] == [cache]
    assert cols["abandoned"] == [rename]
    assert cols["someday"] == [split]
    assert cols["inbox"] == [retry]
    assert cols["ready"] == [] and cols["doing"] == [] and cols["todo"] == []


def test_a_deletion_mid_sequence_closes_the_gap_behind_it(desk):
    """Delete is the one door that removes a row rather than moving it,
    so the column it leaves has to renumber with nothing to renumber
    around."""
    root = desk
    made = [edit.create(root, t, by="user")["data"]["id"]
            for t in ("One", "Two", "Three", "Four")]
    for cid in made[:3]:
        assert edit.move(root, cid, "todo", 99, by="user")["ok"]
    _check(root, "three in todo")
    middle = _columns(root)["todo"][1]
    assert edit.delete(root, middle, by="user")["ok"]
    _check(root, "the middle one deleted")
    assert middle not in _columns(root)["todo"]
    assert len(_columns(root)["todo"]) == 2


def test_the_queue_and_the_board_never_disagree_during_a_run(desk):
    """Derived twice from one file. The queue is what the loop acts on
    and the board is what a person sees, so a disagreement is the loop
    working a card nobody can find."""
    root = desk
    made = [edit.create(root, t, by="user")["data"]["id"]
            for t in ("One", "Two", "Three")]
    for i, cid in enumerate(made):
        assert edit.move(root, cid, "ready", i, by="user")["ok"]
        ready = _columns(root)["ready"]
        q = board.amik_queue(root)["data"]
        assert (q["take"] or {}).get("id") == ready[0]
        # Everything in Ready is accounted for by exactly one bucket.
        named = ([(q["take"] or {}).get("id")]
                 + [c["id"] for c in q["queued"]]
                 + [s["id"] for s in q["skipped"]])
        assert sorted(n for n in named if n) == sorted(ready)
