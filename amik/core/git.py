"""Every git call Amik makes.

One module, so there is one place that knows how Amik treats a
repository and one place to read when it does something surprising.

Nothing here raises. Amik does not require git — a project without it
loses branch placement and keeps its board — so every failure is
`{ok: False, reason}` and the caller decides whether that is fatal.

The rule worth carrying out of here: **a card branch owns CODE and
nothing else.** Shared paths are protected for the life of a card so an
agent's `git add -A` cannot capture them, and the protection is lifted
before the tree moves, so an uncommitted change rides the checkout back
to the trunk the way git already carries one.
"""
import subprocess


def _ok(data):
    return {"ok": True, "data": data}


def _no(reason):
    return {"ok": False, "reason": reason}


def run(root, *args):
    """One git command. Never raises — a missing binary reads the same
    as a refusing one, because to the caller it is.

    `stdin=DEVNULL` because a subprocess inheriting this process's stdin
    is how a CLI ends up waiting on a pipe that will never close.
    """
    try:
        out = subprocess.run(["git", "--no-pager", "-C", str(root), *args],
                             capture_output=True, text=True, timeout=120,
                             stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return _no(f"git unavailable: {type(exc).__name__}")
    if out.returncode:
        return _no((out.stderr or out.stdout or "git refused").strip())
    return _ok(out.stdout.strip())


def is_repo(root):
    return run(root, "rev-parse", "--git-dir")["ok"]


def current_branch(root):
    return run(root, "rev-parse", "--abbrev-ref", "HEAD")


def branch_exists(root, name):
    return run(root, "rev-parse", "--verify", "--quiet", name)["ok"]


def _protect(root, shared, on):
    """`skip-worktree` on the shared paths, for the life of one card.

    This is the flag that stops `git add -A` staging a file, which is
    exactly the failure it is here to prevent: agents use `add -A`, and
    a card's close committed onto its own branch is invisible once the
    tree returns to the trunk.

    It has a reputation as a footgun, earned by living forever in a
    clone nobody remembers setting it in. Bounded to one card by a
    process holding a lock, that reputation does not apply — and
    `finish` lifts it before the tree moves, which is the half that
    keeps the bound true.

    Tracked files only: git rejects the flag for anything else, and an
    untracked path has nothing to protect.
    """
    flag = "--skip-worktree" if on else "--no-skip-worktree"
    for pattern in shared:
        listed = run(root, "ls-files", "-z", "--", pattern)
        if not listed["ok"] or not listed["data"]:
            continue
        for path in listed["data"].split("\0"):
            if path:
                run(root, "update-index", flag, "--", path)


def unprotect(root, shared):
    """Lift the protection without moving the tree.

    `skip-worktree` hides a file from `git status` as well as from
    `git add -A` — it is one mechanism, not two — so anything that needs
    to SEE what a card changed under the shared paths has to lift it
    first. `finish` lifts it again, harmlessly.
    """
    _protect(root, shared, False)


def protect(root, shared):
    """Put the protection back without moving the tree.

    For a card that lands PARKED on its branch. The tree stays there for
    the owner to look at, which can be days — and a bare shared path on
    a branch nobody is watching is captured by whatever commits next.
    The mechanism the parked state used to rely on was that git carries
    an uncommitted file across a checkout, which holds only for exactly
    as long as nobody commits.
    """
    _protect(root, shared, True)


def changed_under(root, paths):
    """Tracked files under `paths` that differ from HEAD, sorted."""
    if not paths:
        return []
    out = run(root, "status", "--porcelain", "--", *paths)
    if not out["ok"] or not out["data"]:
        return []
    names = []
    for line in out["data"].split("\n"):
        # NOT a fixed offset. Porcelain's status field is two columns
        # and a space (" M path"), but `run` strips its output, so the
        # leading space is already gone from the FIRST line and present
        # on every other one. Splitting on whitespace is indifferent to
        # which line this is; `line[3:]` silently ate a character.
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            names.append(parts[1].strip().strip('"'))
    return sorted(names)


def clear_all_protection(root):
    """Lift `skip-worktree` from every tracked file, unconditionally.

    The bit is INDEX state and it outlives the process that set it. A
    crash, a refused run, or a checkout between branches can strand it
    — and git reports a skip-worktree path as OUTSIDE THE SPARSE
    CHECKOUT, so `git add` then refuses it and the sweep dies. Which
    means one stranded bit halts every future card at placement, with
    a message about sparse-checkout that names nothing Amik ever
    configured.

    Measured: 746 files were stranded this way, and every card halted
    until they were cleared by hand.

    So `start` clears before it protects, over every tracked file
    rather than the declared ones — a bit stranded on a path that has
    since LEFT the `shared` list would otherwise be unreachable. `-z`
    because a tracked filename can contain anything.
    """
    listed = run(root, "ls-files", "-z")
    if not listed["ok"] or not listed["data"]:
        return
    paths = [p for p in listed["data"].split("\0") if p]
    for i in range(0, len(paths), 500):
        run(root, "update-index", "--no-skip-worktree", "--",
            *paths[i:i + 500])


def sweep(root, shared, message="chore: sync runtime state"):
    """Commit whatever the shared paths have drifted to, before a card
    starts. Returns the new commit's sha, or "" when nothing moved.

    Two jobs in one commit. It stops a night of watcher churn being
    swept into a card's commits and merged under that card's name — and
    it is the RESTORE POINT that makes a card touching shared state
    survivable, since undo is a checkout of those paths at this sha.
    """
    if not shared:
        return _ok("")
    if not changed_under(root, shared):
        return _ok("")
    added = run(root, "add", "--", *shared)
    if not added["ok"]:
        return added
    done = run(root, "commit", "-m", message, "--", *shared)
    if not done["ok"]:
        return done
    return run(root, "rev-parse", "HEAD")


def start(root, card_id, trunk, shared):
    """Put the tree where this card belongs.

    Come home, sweep, place, protect — in that order. Sweeping after
    placing would commit the drift onto the card's branch, which is the
    thing being prevented.
    """
    if not is_repo(root):
        return _no("not a git repository")
    if not trunk:
        return _no("no trunk: set `trunk` in amik.toml")
    # Before anything reads the index. A bit stranded by an earlier run
    # makes `git add` refuse the path, which kills the sweep below and
    # halts the card — so this is not tidiness, it is the difference
    # between self-healing and needing a person.
    clear_all_protection(root)
    # HOME FIRST. A card that landed in `review` leaves the tree parked
    # on its own branch, and the sweep below commits every live path —
    # the board among them — wherever the tree happens to be standing.
    # Sweeping there writes one card's board state onto a branch nobody
    # is watching, and the trunk's copy then disagrees about the very
    # card that was just worked.
    here = current_branch(root)
    if not here["ok"]:
        return here
    if here["data"] != trunk:
        home = run(root, "checkout", trunk)
        if not home["ok"]:
            return home
    swept = sweep(root, shared)
    if not swept["ok"]:
        return swept
    name = f"card/{card_id}"
    if branch_exists(root, name):
        # RESUME. Never `checkout -B`: a halted card keeps its branch,
        # and resetting it to the trunk would throw away the work that
        # halted — silently, and with every test still green.
        placed = run(root, "checkout", name)
    else:
        placed = run(root, "checkout", "-b", name, trunk)
    if not placed["ok"]:
        return placed
    _protect(root, shared, True)
    return _ok({"branch": name, "swept": swept["data"]})


def finish(root, trunk, shared):
    """Return the tree to the trunk.

    Unprotect FIRST. A `skip-worktree` file with local changes blocks a
    checkout, and a flag left set outlives the card — which is the only
    way this becomes the footgun it is reputed to be.
    """
    if not is_repo(root):
        return _no("not a git repository")
    if not trunk:
        return _no("no trunk: set `trunk` in amik.toml")
    _protect(root, shared, False)
    return run(root, "checkout", trunk)


def drop_branch(root, name):
    """Unname a branch.

    Its commits stay reachable through the reflog for about ninety days,
    which is what makes this routine rather than destruction.
    """
    return run(root, "branch", "-D", name)
