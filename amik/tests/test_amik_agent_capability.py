"""Whether an agent can work this board, and who is allowed to say so.

A board with no agent is still a board -- the shipped config promises it
in as many words -- so the answer to "nothing is declared" is never to
refuse to render. It is to SAY so, in the one place someone is looking:
the page.

Two questions, and conflating them is the bug this file exists to stop.

**Capable** is "could an agent ever work a card here": a verify command
and an agent command, both declared. **Will work** is capable AND armed.

They come apart at exactly one point, and it is the point that matters.
Pausing stops the loop TAKING anything new; a card already in Doing runs
to the end, and the page says so itself when you pause it. So a paused
board must keep showing that card as worked. Gating the spinner on
`will_work` would erase a card that is genuinely running, which is worse
than the lie it was written to fix.
"""

import inspect
import os

from amik.core import board

TOML = 'verify = "true"\narmed = true\n[agent]\ncommand = "an-agent"\n'


def _toml(root, text):
    with open(os.path.join(root, "amik", "amik.toml"), "w",
              encoding="utf-8") as f:
        f.write(text)
    return root


# ── capable: could an agent EVER work here ──────────────────────────

def test_an_instance_with_no_config_at_all_names_the_missing_file(empty_board):
    """Not "no verify": there is nowhere to put one yet, and naming the
    key would send somebody looking for a file that is not there."""
    res = board.amik_agent_capable(empty_board)
    assert res["ok"] is False
    assert "amik.toml" in res["reason"]


def test_a_config_that_declares_no_verify_names_verify(empty_board):
    _toml(empty_board, "armed = true\n")
    res = board.amik_agent_capable(empty_board)
    assert res["ok"] is False
    assert "verify" in res["reason"]


def test_a_verify_with_no_agent_is_not_capable(empty_board):
    """Two gates, and the reason must name the one that is shut. "No"
    on its own sends somebody to the code."""
    _toml(empty_board, 'verify = "true"\narmed = true\n')
    res = board.amik_agent_capable(empty_board)
    assert res["ok"] is False
    assert "agent" in res["reason"]


def test_both_declared_is_capable(empty_board):
    _toml(empty_board, TOML)
    assert board.amik_agent_capable(empty_board)["ok"] is True


def test_PAUSING_DOES_NOT_MAKE_A_BOARD_INCAPABLE(empty_board):
    """The distinction this file is about. A paused board still has an
    agent and still has a card finishing in Doing."""
    _toml(empty_board, 'verify = "true"\narmed = false\n'
                       '[agent]\ncommand = "an-agent"\n')
    assert board.amik_agent_capable(empty_board)["ok"] is True


# ── will work: capable AND armed ────────────────────────────────────

def test_a_capable_armed_board_will_work(empty_board):
    _toml(empty_board, TOML)
    assert board.amik_will_work(empty_board)["ok"] is True


def test_a_capable_paused_board_will_NOT_work_and_says_armed(empty_board):
    _toml(empty_board, 'verify = "true"\narmed = false\n'
                       '[agent]\ncommand = "an-agent"\n')
    res = board.amik_will_work(empty_board)
    assert res["ok"] is False
    assert "armed" in res["reason"]


def test_an_incapable_board_gives_the_SAME_reason_either_way(empty_board):
    """One ladder. If the two functions could word this differently,
    the banner and the page would eventually disagree about one board."""
    _toml(empty_board, 'armed = true\n')
    assert (board.amik_will_work(empty_board)["reason"]
            == board.amik_agent_capable(empty_board)["reason"])


# ── one copy of the ladder ──────────────────────────────────────────

def test_the_banner_asks_the_reader_rather_than_deciding(empty_board):
    """The reason lived in the banner and in `status`, worded almost the
    same. A third copy on the page is how one board comes to have two
    accounts of itself."""
    from amik.app import server
    src = inspect.getsource(server._banner)
    assert "amik_will_work" in src
    assert "armed is not true" not in src, "the banner still carries the ladder"



# ── a trunk it cannot find ──────────────────────────────────────────

def _repo(root, branch):
    import subprocess
    subprocess.run(["git", "init", "-q", "-b", branch, root], check=True)
    for args in (["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", root, *args], check=True)
    with open(os.path.join(root, "a.txt"), "w") as f:
        f.write("x\n")
    subprocess.run(["git", "-C", root, "add", "-A"], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "first"], check=True)
    return root


def test_a_repo_with_no_findable_trunk_will_NOT_work(empty_board):
    """Detection reads the remote's default, then a local `main`, then
    `master`. A repository on `develop` with no remote answers none of
    them -- and every card would halt at placement, one at a time, each
    discovering it separately. Say it at boot instead."""
    _toml(empty_board, TOML)
    _repo(empty_board, "develop")
    res = board.amik_will_work(empty_board)
    assert res["ok"] is False
    assert "trunk" in res["reason"]


def test_a_findable_trunk_is_no_obstacle(empty_board):
    _toml(empty_board, TOML)
    _repo(empty_board, "main")
    assert board.amik_will_work(empty_board)["ok"] is True


def test_a_DECLARED_trunk_settles_it(empty_board):
    """The key is an override, not a requirement. Declaring it is how a
    repository that cannot be guessed about says so once."""
    # ABOVE the table, or it becomes `agent.trunk` — the footgun this
    # config's own comments warn about, and which this test walked into.
    _toml(empty_board, 'trunk = "develop"\n' + TOML)
    _repo(empty_board, "develop")
    assert board.amik_will_work(empty_board)["ok"] is True


def test_a_project_that_is_NOT_A_REPOSITORY_is_left_alone(empty_board):
    """Amik works boards in directories that are not checkouts at all --
    losing branch placement, not the board. An undetectable trunk is
    only a problem where there is a repository to place a branch in."""
    _toml(empty_board, TOML)
    assert board.amik_will_work(empty_board)["ok"] is True


def test_the_trunk_check_stays_OFF_the_page_render(empty_board):
    """`amik_agent_capable` is asked on every board read and must not
    shell out to git -- detection is up to three subprocesses. The
    banner asks once, at boot, which is where this belongs."""
    _toml(empty_board, TOML)
    _repo(empty_board, "develop")
    assert board.amik_agent_capable(empty_board)["ok"] is True


def test_STATUS_and_the_BANNER_never_disagree(empty_board):
    """Two surfaces, one reader. `status` used to answer "did the config
    parse" while the banner answered "will cards be worked", which are
    different questions -- so a board with no findable trunk reported
    ready on one and refused on the other."""
    import json
    import subprocess
    import sys
    from amik.app import server
    _toml(empty_board, TOML)
    _repo(empty_board, "develop")
    out = subprocess.run([sys.executable, "-m", "amik", "--root",
                          empty_board, "status"],
                         capture_output=True, text=True).stdout
    said = json.loads(out)
    banner = server._banner(empty_board, 4455)
    assert said["ready_to_work"] is False
    assert "working cards: no" in banner
    assert said["why_not"] in banner
