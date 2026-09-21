"""Landing brings the tree home before it merges.

The fault this closes, lived: a card carrying a forced halt landed in
`review`, which parks the tree on that card's branch ON PURPOSE -- the
work worth looking at is there. The owner then moved the card to Done,
which is not an unusual thing to do. It is the ONLY thing they can do:
`amik_agent_may_close` refuses a card carrying a prototype flag, and the
card's own prose says it "cannot be closed without you".

Nothing un-parked the tree. `land` refuses to merge while standing
anywhere but the trunk -- correctly, because git merges INTO the
current branch, and merging a card into another card's branch is worse
than not merging at all. So every tick refused, silently, and finished
work piled up unmerged. Two commits were made on the parked branch by
somebody who assumed they were on the trunk.

The parking is still right while a card sits in `review`. It stops
being right the moment that card is Done, because then the branch is
owed a merge and the tree standing on it is the only thing preventing
one. So: owed work comes first, and only then does the tree come home.
"""

import os
import subprocess

from amik import loop
from amik.core import git
from tests.test_amik_land import landing, _rows  # noqa: F401  (fixture)


def _branch(root):
    return git.current_branch(root)["data"]


def test_it_comes_home_when_a_merge_is_owed(landing):
    """The whole fix. Parked on a card branch, with work owed, landing
    walks back to the trunk and does its job."""
    git.run(landing, "checkout", "card/one")
    res = loop.land(landing)
    assert res["ok"], res
    assert sorted(res["data"]["landed"]) == ["one", "two"]
    assert _branch(landing) == "main"


def test_the_merge_lands_on_the_TRUNK_not_the_parked_branch(landing):
    """What the old refusal was protecting against, now protected by
    moving rather than by declining."""
    git.run(landing, "checkout", "card/one")
    loop.land(landing)
    for cid in ("one", "two"):
        assert os.path.exists(os.path.join(landing, cid + ".py"))
    on_trunk = git.run(landing, "log", "--oneline", "main")["data"]
    assert "two" in on_trunk


def test_a_PARKED_TREE_IS_LEFT_ALONE_when_nothing_is_owed(landing):
    """The parking exists so a halted card's work is in front of you.
    A card still sitting in `review` owes no merge, so landing has no
    business moving the tree out from under it."""
    loop.land(landing)                       # clears what is owed
    git.run(landing, "checkout", "card/one") if git.branch_exists(
        landing, "card/one") else None
    git.run(landing, "checkout", "-b", "card/parked", "main")
    res = loop.land(landing)
    assert res["ok"], res
    assert res["data"]["landed"] == []
    assert _branch(landing) == "card/parked", "it moved a parked tree"


def test_it_REFUSES_when_it_cannot_come_home(landing):
    """A tree it cannot move is still a tree it must not merge from.
    The refusal survives -- what changed is that it is now the last
    resort rather than the first answer."""
    git.run(landing, "checkout", "card/one")
    path = os.path.join(landing, "one.py")
    with open(path, "w") as f:
        f.write("uncommitted work nobody asked to lose\n")
    res = loop.land(landing)
    assert res["ok"] is False
    assert "trunk" in res["reason"]
    assert _branch(landing) == "card/one"
    assert "nobody asked to lose" in open(path).read()


# ── the refusal is said out loud ────────────────────────────────────

def test_a_refused_landing_is_PRINTED_by_the_ticker(landing, capsys):
    """It refused every tick for an hour and said nothing. A refusal is
    an answer, and most are boring -- but "finished work is not being
    merged" is not one of the boring ones."""
    with open(os.path.join(landing, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\ntrunk = "main"\narmed = true\n')
    git.run(landing, "checkout", "card/one")
    with open(os.path.join(landing, "one.py"), "w") as f:
        f.write("dirty\n")
    loop.tick_forever(landing, sleep=0, rounds=1)
    assert "trunk" in capsys.readouterr().err


def test_the_SAME_refusal_is_not_repeated_every_tick(landing, capsys):
    """A tick is a second long. A merge conflict that printed on every
    one of them would be the reason nobody reads this log."""
    with open(os.path.join(landing, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\ntrunk = "main"\narmed = true\n')
    git.run(landing, "checkout", "card/one")
    with open(os.path.join(landing, "one.py"), "w") as f:
        f.write("dirty\n")
    loop.tick_forever(landing, sleep=0, rounds=4)
    assert capsys.readouterr().err.count("trunk") == 1
