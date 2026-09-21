"""A prototype's lifetime is its card's, and nothing was enforcing it.

`amik_prototypes` has always NAMED closed cards whose directory survives
-- its own docstring says "performing it is an agent's" -- and nothing
ever performed it. That was survivable while prototypes were tracked,
because a branch delete or a checkout tidied them incidentally.

Once they are gitignored, NOTHING IN GIT REMOVES THEM. The sweep stops
being housekeeping and becomes the only mechanism there is.
"""

import os

from amik.core import board, edit


def _proto(root, card_id):
    d = os.path.join(root, "amik", "prototypes", card_id)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.html"), "w") as f:
        f.write("<p>x</p>")
    return d


def test_the_directory_is_ignored():
    # The PACKAGE's own .gitignore, not the repository's. The folder's
    # runtime rules travel with the folder -- a rule left at a root does
    # not follow it into somebody else's project.
    from conftest import PACKAGE
    path = os.path.join(PACKAGE, ".gitignore")
    assert "prototypes/" in open(path).read()


def test_discarding_removes_the_directory(scenario):
    root = scenario("ready_plain")
    d = _proto(root, "rename-the-export-button")
    assert edit.discard_prototype(root, "rename-the-export-button")["ok"]
    assert not os.path.exists(d)


def test_discarding_one_that_is_not_there_is_fine(scenario):
    """Idempotent: every close path calls this and most cards never had
    one. A refusal would make the common case an error."""
    res = edit.discard_prototype(scenario("ready_plain"), "no-such-card")
    assert res["ok"] is True and res["data"]["removed"] is False


def test_it_cannot_escape_the_prototypes_directory(scenario):
    """A card id is hand-authored and reaches a path join. The reader
    already guards this shape; a verb that DELETES earns it more."""
    root = scenario("ready_plain")
    for bad in ("../../etc", "a/b", "", ".", "..", None):
        res = edit.discard_prototype(root, bad)
        assert res["ok"] is False, bad


def test_the_sweep_names_what_is_owed_and_stops_once_it_is_gone(scenario):
    root = scenario("ready_plain")
    _proto(root, "rename-the-export-button")
    edit.move(root, "rename-the-export-button", "done", 0)
    owed = [c["id"] for c in board.amik_prototypes(root)["data"]]
    assert "rename-the-export-button" in owed
    edit.discard_prototype(root, "rename-the-export-button")
    assert board.amik_prototypes(root)["data"] == []

