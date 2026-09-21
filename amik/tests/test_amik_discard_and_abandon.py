"""Two verbs, because discarding a BUILD is not abandoning a CARD.

The idea is still good and the attempt is not: that card loses its
branch and its prototype and goes back to Ready for another run.
Sending it to `abandoned` would say the opposite.

This case barely existed when only toggled cards branched. Under
every-card-branches it is the common one.

Deleting an unmerged branch is UNNAMING, not destruction -- the reflog
keeps its commits reachable for about ninety days, which is what makes
`git branch -D` routine rather than dangerous.
"""

import json
import os

from amik.core import board, edit, git


def _row(root):
    for line in open(os.path.join(root, "amik", "board.jsonl")):
        if line.strip():
            return json.loads(line)


def _proto(root, card_id="a-card"):
    d = os.path.join(root, "amik", "prototypes", card_id)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.html"), "w") as f:
        f.write("<p>x</p>")
    return d


# ── discard ─────────────────────────────────────────────────────────

def test_discard_returns_the_card_to_READY(repo_with_card):
    """The button says Try Again, and one that says that and then does
    not try again is lying. The owner can drag it to To-Do if they want
    to think first."""
    assert edit.discard(repo_with_card, "a-card", "main")["ok"]
    assert _row(repo_with_card)["status"] == "ready"


def test_discard_drops_the_branch(repo_with_card):
    edit.discard(repo_with_card, "a-card", "main")
    assert not git.branch_exists(repo_with_card, "card/a-card")


def test_discard_sweeps_the_prototype(repo_with_card):
    d = _proto(repo_with_card)
    edit.discard(repo_with_card, "a-card", "main")
    assert not os.path.exists(d)


def test_discard_clears_the_branch_field(repo_with_card):
    edit.set_branch(repo_with_card, "a-card", "card/a-card")
    edit.discard(repo_with_card, "a-card", "main")
    assert not _row(repo_with_card).get("branch")


def test_the_work_is_UNNAMED_not_destroyed(repo_with_card):
    """The reflog is what makes this routine. If the commits were
    actually gone, discarding would need a confirmation this design
    does not give it."""
    edit.discard(repo_with_card, "a-card", "main")
    out = git.run(repo_with_card, "reflog", "--all")
    assert "the work" in (out["data"] or ""), out


# ── abandon ─────────────────────────────────────────────────────────

def test_abandon_closes_the_card(repo_with_card):
    assert edit.abandon(repo_with_card, "a-card", "main")["ok"]
    assert _row(repo_with_card)["status"] == "abandoned"


def test_abandon_drops_the_branch_too(repo_with_card):
    """The owner's 2026-09-17 revision of the 09-14 ruling: "we
    abandoned it, don't need it. And like you say we have 90 days"."""
    edit.abandon(repo_with_card, "a-card", "main")
    assert not git.branch_exists(repo_with_card, "card/a-card")


def test_abandon_sweeps_the_prototype(repo_with_card):
    d = _proto(repo_with_card)
    edit.abandon(repo_with_card, "a-card", "main")
    assert not os.path.exists(d)


# ── refusals ────────────────────────────────────────────────────────

def test_it_steps_OFF_the_branch_before_dropping_it(repo_with_card):
    """git will not delete the branch you are standing on, and a halted
    card leaves the tree exactly there -- so refusing would mean
    knowing to check out the trunk before pressing a button that closes
    the card."""
    git.run(repo_with_card, "checkout", "card/a-card")
    assert edit.discard(repo_with_card, "a-card", "main")["ok"]
    assert git.current_branch(repo_with_card)["data"] == "main"
    assert not git.branch_exists(repo_with_card, "card/a-card")


def test_a_dirty_tree_still_stops_it(repo_with_card):
    """The checkout remains the gate. An uncommitted change that would
    be overwritten refuses, and the refusal is reported rather than
    forced."""
    git.run(repo_with_card, "checkout", "card/a-card")
    with open(os.path.join(repo_with_card, "work.py"), "w") as f:
        f.write("uncommitted = True\n")
    res = edit.abandon(repo_with_card, "a-card", "main")
    assert res["ok"] is False, res
    assert _row(repo_with_card)["status"] == "review", "the card moved anyway"
    assert git.branch_exists(repo_with_card, "card/a-card")


def test_no_trunk_on_its_own_branch_is_a_named_refusal(repo_with_card):
    """Not a traceback, and not a silent no-op: there is nowhere to
    step to, and the message says which line fixes it."""
    git.run(repo_with_card, "checkout", "card/a-card")
    res = edit.discard(repo_with_card, "a-card", "")
    assert res["ok"] is False
    assert "trunk" in res["reason"]


def test_an_unknown_card_is_refused(repo_with_card):
    assert edit.discard(repo_with_card, "no-such-card", "main")["ok"] is False


def test_a_card_with_no_branch_is_still_discardable(repo_with_card):
    """Not every card has a ref — one worked before this landed, or in
    a project with no git. The verb is about the CARD."""
    git.drop_branch(repo_with_card, "card/a-card")
    assert edit.discard(repo_with_card, "a-card", "main")["ok"]
    assert _row(repo_with_card)["status"] == "ready"


# ── the queues are still not allowed to do this ─────────────────────

def test_THE_QUEUES_STILL_NEVER_DELETE_A_REF():
    """The three existing guards, restated as one claim.

    `amik_finalise` names cards owed a MERGE and stays done-only; an
    abandoned card is owed a DELETE, which is a different thing and a
    different queue. Nothing that ENUMERATES cards may destroy
    anything -- only a named verb acting on one card.
    """
    import inspect
    for fn in (board.amik_finalise, board.amik_prototypes, board.amik_queue):
        src = inspect.getsource(fn)
        assert "drop_branch" not in src, fn.__name__
        assert "rmtree" not in src, fn.__name__
        assert "discard" not in src, fn.__name__


# ── what a discard does NOT reset ───────────────────────────────────

def _prose(root, cid="a-card"):
    path = os.path.join(root, "amik", "cards", cid + ".md")
    return open(path).read() if os.path.exists(path) else ""


def test_the_owners_answers_SURVIVE_a_discard(repo_with_card):
    """An answer is the OWNER's work, not the attempt's. Clearing it
    would make the next agent re-ask what they already decided."""
    edit.ask(repo_with_card, "a-card", "Which way?", context="A or B.")
    edit.replace_section_body  # the writer exists
    path = os.path.join(repo_with_card, "amik", "cards", "a-card.md")
    text = open(path).read().replace("### Which way?",
                                     "### Which way?\n\nB, definitely.")
    with open(path, "w") as f:
        f.write(text)
    edit.discard(repo_with_card, "a-card", "main")
    assert "B, definitely." in _prose(repo_with_card)


def test_the_outcome_is_APPENDED_TO_not_cleared(repo_with_card):
    """An agent reading "attempt 1 did X, discarded" will not do X
    again. That is the whole reason not to wipe it."""
    edit.record_outcome(repo_with_card, "a-card",
                        "Rewrote the parser.", model="test")
    edit.discard(repo_with_card, "a-card", "main")
    prose = _prose(repo_with_card)
    assert "Rewrote the parser." in prose, "the record was wiped"
    assert "was discarded" in prose
    assert prose.index("Rewrote the parser.") < prose.index("was discarded")


# ── the owner's feedback, on the card ───────────────────────────────

def test_feedback_lands_on_the_body_as_round_one(repo_with_card):
    edit.discard(repo_with_card, "a-card", "main",
                 feedback="You built the whole page. I wanted the toggle.")
    prose = _prose(repo_with_card)
    assert "## User Feedback: Round 1" in prose
    assert "I wanted the toggle." in prose


def test_a_second_round_does_not_overwrite_the_first(repo_with_card):
    """A card tried three times carries three notes, in order. The
    agent reads every wrong turn rather than only the latest, which is
    the entire reason not to keep one slot and rewrite it."""
    edit.discard(repo_with_card, "a-card", "main", feedback="Too broad.")
    from amik.core import git
    git.start(repo_with_card, "a-card", "main", [])
    git.finish(repo_with_card, "main", [])
    edit.discard(repo_with_card, "a-card", "main", feedback="Still too broad.")
    prose = _prose(repo_with_card)
    assert "Round 1" in prose and "Round 2" in prose
    assert "Too broad." in prose and "Still too broad." in prose
    assert prose.index("Round 1") < prose.index("Round 2")


def test_no_feedback_writes_no_round(repo_with_card):
    """Optional. A retry the owner already understands should not need
    an explanation typed to be allowed."""
    edit.discard(repo_with_card, "a-card", "main", feedback="   ")
    assert "User Feedback" not in _prose(repo_with_card)


def test_feedback_survives_the_discard_it_came_with(repo_with_card):
    """It is written AFTER the card moves, so a refused discard must
    not leave feedback on a card that was never reset."""
    from amik.core import git
    git.run(repo_with_card, "checkout", "card/a-card")
    with open(os.path.join(repo_with_card, "work.py"), "w") as f:
        f.write("uncommitted = True\n")
    edit.discard(repo_with_card, "a-card", "", feedback="never mind")
    assert "never mind" not in _prose(repo_with_card)
