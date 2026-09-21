"""A change to shared state goes live the moment it is made.

A branch cannot isolate it -- the live writers keep writing those same
files on the trunk's schedule -- and deleting the branch undoes nothing,
because the change was never confined to it. So the rule is not
prevention, it is TELLING. A change that is live the instant it is made,
landing with nobody told, is the one outcome this must not produce.

What makes it survivable is the sweep before every card, which is the
restore point: undo is `git checkout <sweep-sha> -- <paths>`.
"""

import json
import os
import subprocess

import pytest

from amik import loop

ROWS = [{"id": "a-card", "title": "A card", "status": "ready",
         "planning": None, "rank": 1, "created_at": "2026-01-01T00:00:00",
         "updated_at": "2026-01-01T00:00:00"}]


@pytest.fixture()
def repo(instance):
    from conftest import write_board
    root = str(instance)
    write_board(root, ROWS)
    os.makedirs(os.path.join(root, "live"), exist_ok=True)
    with open(os.path.join(root, "live", "cursor.json"), "w") as f:
        f.write("{}\n")
    with open(os.path.join(root, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\narmed = true\ntrunk = "main"\n'
                '[agent]\ncommand = "the-agent"\n'
                '[state]\nshared = ["live", "amik/board.jsonl"]\n')
    subprocess.run(["git", "init", "-q", "-b", "main", root], check=True)
    subprocess.run(["git", "-C", root, "config", "user.email", "t@t"],
                   check=True)
    subprocess.run(["git", "-C", root, "config", "user.name", "t"],
                   check=True)
    subprocess.run(["git", "-C", root, "add", "-A"], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "first"], check=True)
    return root


def _tick(root, during=lambda root: None):
    import unittest.mock as mock

    def fake_agent(*a, **kw):
        during(root)
        return subprocess.CompletedProcess(["the-agent"], 0, "", "")

    with mock.patch.object(loop, "run_agent", side_effect=fake_agent):
        return loop.work_once(root)


def _row(root):
    for line in open(os.path.join(root, "amik", "board.jsonl")):
        if line.strip():
            return json.loads(line)


def _prose(root):
    path = os.path.join(root, "amik", "cards", "a-card.md")
    return open(path).read() if os.path.exists(path) else ""


def _close(status, touch=None):
    def during(root):
        from amik.core import edit
        if touch:
            with open(os.path.join(root, touch), "w") as f:
                f.write('{"moved": true}\n')
        edit.record_outcome(root, "a-card", "Built it.", model="test")
        edit.move(root, "a-card", status, 0)
    return during


def test_a_card_that_touched_nothing_shared_is_left_alone(repo):
    """The common case, and it has to stay quiet or the signal is
    worthless. The board itself changes on every card and does not
    count -- that is Amik's own bookkeeping, not the card's doing."""
    _tick(repo, _close("done"))
    row = _row(repo)
    assert row["status"] == "done"
    assert "halt" not in row
    assert "shared state" not in _prose(repo)


def test_changed_shared_paths_are_NAMED_on_the_card(repo):
    """Not "shared state changed" -- which paths. A vague card is one
    somebody has to go investigate."""
    _tick(repo, _close("done", touch="live/cursor.json"))
    assert "live/cursor.json" in _prose(repo)


def test_it_names_the_restore_point(repo):
    """Undo is a checkout of those paths at the sweep commit. Without
    the sha, the card says a thing happened and not how to undo it."""
    _tick(repo, _close("done", touch="live/cursor.json"))
    assert "git checkout" in _prose(repo)


def test_a_card_touching_shared_state_without_a_pause_is_halted(repo):
    _tick(repo, _close("done", touch="live/cursor.json"))
    row = _row(repo)
    assert row["halt"] is True
    assert row["status"] == "review"


def test_a_card_that_ALREADY_asked_for_a_pause_is_not_moved_again(repo):
    """Reporting an owner's own halt as though the loop imposed it is
    misleading -- they asked."""
    import json as _json
    path = os.path.join(repo, "amik", "board.jsonl")
    rows = [_json.loads(l) for l in open(path) if l.strip()]
    rows[0]["halt"] = True
    with open(path, "w") as f:
        for r in rows:
            f.write(_json.dumps(r) + "\n")
    _tick(repo, _close("review", touch="live/cursor.json"))
    assert "live/cursor.json" in _prose(repo)
    assert _row(repo)["status"] == "review"


def test_an_instance_declaring_NO_shared_never_halts_for_this(repo):
    """The portability property: inert without a declaration."""
    with open(os.path.join(repo, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\narmed = true\ntrunk = "main"\n'
                '[agent]\ncommand = "the-agent"\n')
    _tick(repo, _close("done", touch="live/cursor.json"))
    row = _row(repo)
    assert row["status"] == "done" and "halt" not in row


# ── churn: shared, but not the card's doing ─────────────────────────

def test_a_churn_path_is_not_the_cards_doing(repo):
    """Found live, on the first probe. The hourly watchers fired
    mid-card and wrote two cursors; the card was halted for writes its
    agent never made, because git cannot tell one writer from another.

    A project names its own churn. Nothing else can.
    """
    with open(os.path.join(repo, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\narmed = true\ntrunk = "main"\n'
                '[agent]\ncommand = "the-agent"\n'
                '[state]\nshared = ["live", "amik/board.jsonl"]\n'
                'churn = ["live/cursor.json"]\n')
    _tick(repo, _close("done", touch="live/cursor.json"))
    row = _row(repo)
    assert row["status"] == "done", "halted for the watchers' write"
    assert "halt" not in row
    assert "shared state" not in _prose(repo)


def test_churn_does_not_exempt_everything_shared(repo):
    """It is a subset, not an off switch. A card editing content still
    reports, even when a cursor moved in the same run."""
    os.makedirs(os.path.join(repo, "live", "data"), exist_ok=True)
    with open(os.path.join(repo, "live", "data", "page.md"), "w") as f:
        f.write("before\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-qm", "live data"], check=True)
    with open(os.path.join(repo, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\narmed = true\ntrunk = "main"\n'
                '[agent]\ncommand = "the-agent"\n'
                '[state]\nshared = ["live", "amik/board.jsonl"]\n'
                'churn = ["live/cursor.json"]\n')

    def during(root):
        from amik.core import edit
        with open(os.path.join(root, "live", "cursor.json"), "w") as f:
            f.write("{}\n")
        with open(os.path.join(root, "live", "data", "page.md"), "w") as f:
            f.write("after\n")
        edit.record_outcome(root, "a-card", "Built it.", model="test")
        edit.move(root, "a-card", "done", 0)

    _tick(repo, during)
    prose = _prose(repo)
    assert "live/data/page.md" in prose
    assert "live/cursor.json" not in prose
    assert _row(repo)["halt"] is True


def test_amiks_own_board_needs_no_declaration(repo):
    """Amik knows it writes the board — moving a card is bookkeeping.
    Making every project remember to say so would be Amik asking to be
    told something it already knows."""
    with open(os.path.join(repo, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\narmed = true\ntrunk = "main"\n'
                '[agent]\ncommand = "the-agent"\n'
                '[state]\nshared = ["amik/board.jsonl"]\n')
    _tick(repo, _close("done"))
    assert _row(repo)["status"] == "done"


# ── a parked tree keeps its protection ──────────────────────────────


def _protected(root):
    """Which tracked paths carry `skip-worktree`. `ls-files -v` tags
    one `S`; every other letter is some other index state."""
    out = subprocess.run(["git", "-C", root, "ls-files", "-v"],
                         capture_output=True, text=True, check=True)
    return sorted(line[2:] for line in out.stdout.splitlines()
                  if line[:1] == "S")


def _branch(root):
    out = subprocess.run(["git", "-C", root, "rev-parse", "--abbrev-ref",
                          "HEAD"], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _committed(root, ref="HEAD"):
    out = subprocess.run(["git", "-C", root, "show", "--name-only",
                          "--format=", ref],
                         capture_output=True, text=True, check=True)
    return [p for p in out.stdout.split() if p]


def test_a_review_landing_leaves_the_shared_paths_PROTECTED(repo):
    """The tree is parked on the card's branch for as long as the owner
    takes to look at it. Bare shared paths there are captured by
    whatever commits next -- and the board is the one that matters,
    because the trunk then disagrees about the card just worked and the
    loop takes it again."""
    _tick(repo, _close("review"))
    assert _branch(repo) == "card/a-card"
    protected = _protected(repo)
    assert "amik/board.jsonl" in protected
    assert "live/cursor.json" in protected


def test_a_commit_on_the_parked_branch_captures_no_shared_path(repo):
    """The property, stated as the thing that actually went wrong: a
    commit made on the parked branch by anything at all -- another
    session, a hand `git add -A`, the next card's sweep."""
    _tick(repo, _close("review"))
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-qm", "somebody else"],
                   check=True)
    captured = _committed(repo)
    assert captured, "nothing was committed, so this proves nothing"
    assert "amik/board.jsonl" not in captured
    assert not [p for p in captured if p.startswith("live/")]


def test_the_next_cards_sweep_does_not_run_on_the_parked_branch(repo):
    """The half that would have undone the other one. `start` clears
    every protection bit before it sweeps, so a sweep taken where the
    tree happens to stand is a sweep onto the parked branch -- which is
    how the board got there in the first place."""
    import json as _json
    path = os.path.join(repo, "amik", "board.jsonl")
    rows = [_json.loads(l) for l in open(path) if l.strip()]
    rows.append(dict(rows[0], id="b-card", title="B card", rank=2))
    with open(path, "w") as f:
        for r in rows:
            f.write(_json.dumps(r) + "\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-qm", "two cards"],
                   check=True)

    _tick(repo, _close("review"))
    assert _branch(repo) == "card/a-card"

    def close_b(root):
        from amik.core import edit
        edit.record_outcome(root, "b-card", "Built it.", model="test")
        edit.move(root, "b-card", "done", 0)

    _tick(repo, close_b)

    out = subprocess.run(["git", "-C", repo, "log", "--format=%H",
                          "main..card/a-card"],
                         capture_output=True, text=True, check=True)
    for sha in out.stdout.split():
        assert "amik/board.jsonl" not in _committed(repo, sha), (
            "the sweep committed the board onto the parked branch")


def test_closing_a_parked_card_lifts_the_protection(repo):
    """The trunk must never be left holding a flag. `finish` covers the
    loop's own way home; this is the other one -- the owner pressing a
    button on a card whose tree is still parked."""
    from amik.core import edit
    _tick(repo, _close("review"))
    assert _protected(repo)
    assert edit.abandon(repo, "a-card", "main")["ok"]
    assert _branch(repo) == "main"
    assert _protected(repo) == []


def test_a_landing_that_is_not_review_comes_home_unprotected(repo):
    """The ordinary case is unchanged: home, and nothing left set."""
    _tick(repo, _close("done"))
    assert _branch(repo) == "main"
    assert _protected(repo) == []


def test_amiks_WHOLE_FOLDER_is_exempt_from_the_report(repo):
    """Not just the board. A card's prose is a board artifact too, and
    every card that closes writes its own outcome -- so reporting
    `amik/cards/<id>.md` as shared state a card changed would fire on
    every single card and mean nothing.

    The report is about the PROJECT's shared state. Amik's own writes
    are bookkeeping.
    """
    os.makedirs(os.path.join(repo, "amik", "cards"), exist_ok=True)
    with open(os.path.join(repo, "amik", "cards", "a-card.md"), "w") as f:
        f.write("Existing prose.\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-qm", "prose"], check=True)
    with open(os.path.join(repo, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\narmed = true\ntrunk = "main"\n'
                '[agent]\ncommand = "the-agent"\n'
                '[state]\nshared = ["live", "amik/board.jsonl",'
                ' "amik/cards"]\n')
    _tick(repo, _close("done"))
    row = _row(repo)
    assert row["status"] == "done", "halted for writing its own outcome"
    assert "halt" not in row


def test_a_cards_PROSE_reaches_the_trunk_not_the_branch(repo):
    """The fault this closes: the row said `done` on the trunk while
    the outcome explaining it sat on a branch nobody had merged. State
    and prose are both the board's, so both have to land in the same
    place."""
    with open(os.path.join(repo, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\narmed = true\ntrunk = "main"\n'
                '[agent]\ncommand = "the-agent"\n'
                '[state]\nshared = ["amik/board.jsonl", "amik/cards"]\n')
    _tick(repo, _close("done"))
    # Back on the trunk, and the prose came with it rather than being
    # committed onto a branch.
    assert "Built it." in _prose(repo)
    out = subprocess.run(["git", "-C", repo, "rev-parse", "--abbrev-ref",
                          "HEAD"], capture_output=True, text=True)
    assert out.stdout.strip() == "main"
