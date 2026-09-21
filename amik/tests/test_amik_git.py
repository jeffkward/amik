"""Amik's whole git surface.

Every call degrades: a directory that is not a repository, a missing
`git`, a command that refuses -- each returns {ok: False, reason} and
none of them raises. Amik does not require git, and a project without it
must lose branch placement rather than lose the board.

The one rule worth carrying out of here: a card branch owns CODE and
nothing else.
"""

import os
import subprocess

from amik.core import git


def _repo(tmp_path, branch="main"):
    root = str(tmp_path)
    subprocess.run(["git", "init", "-q", "-b", branch, root], check=True)
    subprocess.run(["git", "-C", root, "config", "user.email", "t@t"],
                   check=True)
    subprocess.run(["git", "-C", root, "config", "user.name", "t"],
                   check=True)
    os.makedirs(os.path.join(root, "amik"), exist_ok=True)
    with open(os.path.join(root, "amik", "board.jsonl"), "w") as f:
        f.write('{"id": "c1", "status": "ready"}\n')
    with open(os.path.join(root, "code.py"), "w") as f:
        f.write("x = 1\n")
    subprocess.run(["git", "-C", root, "add", "-A"], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "first"], check=True)
    return root


def _staged(root):
    return subprocess.run(["git", "-C", root, "diff", "--cached",
                           "--name-only"], capture_output=True,
                          text=True).stdout


# ── it degrades ─────────────────────────────────────────────────────

def test_a_non_repo_is_a_refusal_not_an_exception(tmp_path):
    assert git.is_repo(str(tmp_path)) is False
    res = git.current_branch(str(tmp_path))
    assert res["ok"] is False and res["reason"]


def test_start_refuses_outside_a_repository(tmp_path):
    res = git.start(str(tmp_path), "c1", "main", [])
    assert res["ok"] is False
    assert "git repository" in res["reason"]


def test_start_refuses_with_no_trunk(tmp_path):
    """Empty trunk means detection found nothing. Refuse rather than
    branch from whatever HEAD happens to be."""
    res = git.start(_repo(tmp_path), "c1", "", [])
    assert res["ok"] is False
    assert "trunk" in res["reason"]


# ── placement ───────────────────────────────────────────────────────

def test_current_branch(tmp_path):
    assert git.current_branch(_repo(tmp_path))["data"] == "main"


def test_start_creates_the_card_branch(tmp_path):
    root = _repo(tmp_path)
    assert git.start(root, "c1", "main", [])["ok"]
    assert git.current_branch(root)["data"] == "card/c1"


def test_start_RESUMES_an_existing_branch_rather_than_resetting_it(tmp_path):
    """The `-B` defect, and the one bug here that destroys work.

    A halted card keeps its branch and waits in Review. When it returns
    to Ready and is worked again, `git checkout -B card/<id> <trunk>`
    would silently reset that branch to the trunk and throw away the
    commits that halted. Re-working RESUMES; discarding is a deliberate
    verb and never a side effect of starting.
    """
    root = _repo(tmp_path)
    git.start(root, "c1", "main", [])
    with open(os.path.join(root, "onbranch.py"), "w") as f:
        f.write("y = 2\n")
    subprocess.run(["git", "-C", root, "add", "-A"], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "work"], check=True)
    git.finish(root, "main", [])

    git.start(root, "c1", "main", [])
    assert os.path.exists(os.path.join(root, "onbranch.py")), \
        "the branch was reset and the halted work is gone"


def test_finish_returns_to_the_trunk(tmp_path):
    root = _repo(tmp_path)
    git.start(root, "c1", "main", [])
    assert git.finish(root, "main", [])["ok"]
    assert git.current_branch(root)["data"] == "main"


# ── shared paths ────────────────────────────────────────────────────

def test_a_shared_path_is_not_carried_onto_the_branch_by_add_all(tmp_path):
    """A card's close committed on its branch is invisible once the tree
    returns to the trunk, and the loop re-picks the card it just
    finished. Agents use `git add -A`; this is what stops it."""
    root = _repo(tmp_path)
    git.start(root, "c1", "main", ["amik/board.jsonl"])
    with open(os.path.join(root, "amik", "board.jsonl"), "w") as f:
        f.write('{"id": "c1", "status": "done"}\n')
    subprocess.run(["git", "-C", root, "add", "-A"], check=True)
    assert "board.jsonl" not in _staged(root), _staged(root)


def test_a_NON_shared_path_is_still_staged(tmp_path):
    """The protection is narrow. A card that could not commit its own
    code would be worse than one that commits the board."""
    root = _repo(tmp_path)
    git.start(root, "c1", "main", ["amik/board.jsonl"])
    with open(os.path.join(root, "code.py"), "w") as f:
        f.write("x = 2\n")
    subprocess.run(["git", "-C", root, "add", "-A"], check=True)
    assert "code.py" in _staged(root)


def test_the_board_change_SURVIVES_the_return_to_the_trunk(tmp_path):
    """The other half, and the half that actually matters: protecting
    the file is worthless if the change is lost on the way back."""
    root = _repo(tmp_path)
    shared = ["amik/board.jsonl"]
    git.start(root, "c1", "main", shared)
    with open(os.path.join(root, "amik", "board.jsonl"), "w") as f:
        f.write('{"id": "c1", "status": "done"}\n')
    git.finish(root, "main", shared)
    assert "done" in open(os.path.join(root, "amik", "board.jsonl")).read()


def test_finish_lifts_the_protection(tmp_path):
    """Left set, the flag outlives the card -- which is the only way it
    becomes the footgun it is reputed to be."""
    root = _repo(tmp_path)
    shared = ["amik/board.jsonl"]
    git.start(root, "c1", "main", shared)
    git.finish(root, "main", shared)
    out = subprocess.run(["git", "-C", root, "ls-files", "-v", "--",
                          "amik/board.jsonl"], capture_output=True,
                         text=True).stdout
    assert not out.startswith("S"), out


def test_an_untracked_shared_path_is_simply_skipped(tmp_path):
    """git rejects skip-worktree on anything untracked, and an untracked
    file needs no protection from `git add -A` anyway... except it does,
    so this asserts only that it does not RAISE."""
    root = _repo(tmp_path)
    assert git.start(root, "c1", "main", ["nothing/here", "amik/*.jsonl"])["ok"]


# ── the sweep ───────────────────────────────────────────────────────

def test_the_sweep_commits_drift_before_the_branch_is_cut(tmp_path):
    root = _repo(tmp_path)
    with open(os.path.join(root, "amik", "board.jsonl"), "w") as f:
        f.write('{"id": "c1", "status": "drifted"}\n')
    res = git.start(root, "c1", "main", ["amik/board.jsonl"])
    assert res["ok"]
    assert res["data"]["swept"], "the sweep sha is the restore point"
    log = subprocess.run(["git", "-C", root, "log", "main", "--oneline"],
                         capture_output=True, text=True).stdout
    assert "sync runtime state" in log


def test_a_clean_tree_sweeps_nothing(tmp_path):
    root = _repo(tmp_path)
    res = git.start(root, "c1", "main", ["amik/board.jsonl"])
    assert res["ok"] and res["data"]["swept"] == ""


def test_changed_under_names_what_moved(tmp_path):
    root = _repo(tmp_path)
    with open(os.path.join(root, "amik", "board.jsonl"), "w") as f:
        f.write("changed\n")
    assert git.changed_under(root, ["amik"]) == ["amik/board.jsonl"]
    assert git.changed_under(root, ["nothing"]) == []
    assert git.changed_under(root, []) == []


# ── dropping ────────────────────────────────────────────────────────

def test_dropping_the_branch_you_are_standing_on_refuses(tmp_path):
    root = _repo(tmp_path)
    git.start(root, "c1", "main", [])
    res = git.drop_branch(root, "card/c1")
    assert res["ok"] is False, "git refuses this and so must we"


def test_dropping_works_from_the_trunk(tmp_path):
    root = _repo(tmp_path)
    git.start(root, "c1", "main", [])
    git.finish(root, "main", [])
    assert git.drop_branch(root, "card/c1")["ok"]
    assert not git.run(root, "rev-parse", "--verify", "--quiet",
                       "card/c1")["ok"]


def test_a_STRANDED_protection_bit_does_not_halt_the_next_card(tmp_path):
    """`skip-worktree` is INDEX state and it outlives the process that
    set it. Git reports such a path as outside the sparse checkout, so
    `git add` refuses it, the sweep dies and `start` returns a refusal
    naming sparse-checkout -- something Amik never configured.

    Measured live: 746 files were stranded this way and every card
    halted at placement until they were cleared by hand. `start`
    clears first now, so one crashed run cannot wedge the board.
    """
    root = _repo(tmp_path)
    shared = ["amik/board.jsonl"]
    # Strand it, the way a crash between protect and finish would.
    git._protect(root, shared, True)
    with open(os.path.join(root, "amik", "board.jsonl"), "w") as f:
        f.write('{"id": "c1", "status": "drifted"}\n')

    res = git.start(root, "c2", "main", shared)
    assert res["ok"], res
    assert git.current_branch(root)["data"] == "card/c2"


def test_it_clears_bits_on_paths_that_have_LEFT_the_shared_list(tmp_path):
    """Clearing only the declared paths would leave a bit unreachable
    the moment someone edits `shared` -- which is exactly when nobody
    is looking for one."""
    root = _repo(tmp_path)
    git._protect(root, ["code.py"], True)
    assert git.run(root, "ls-files", "-v", "--", "code.py"
                   )["data"].startswith("S")
    git.clear_all_protection(root)
    assert not git.run(root, "ls-files", "-v", "--", "code.py"
                       )["data"].startswith("S")
