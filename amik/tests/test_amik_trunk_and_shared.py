"""Two declarations, because Amik cannot guess either.

The trunk is what a card branches FROM and returns TO. Most repositories
call it `main`, some `master`, some neither, and an instance with no
remote has nothing to ask. Guessing wrong is silent and expensive -- a
card branched from the wrong base merges the wrong thing -- so an
undetectable trunk is empty and the caller refuses.

`shared` names paths a branch must not own. Amik does not know what they
are; it knows only that a branch may not take them hostage. ABSENT MEANS
NOTHING IS SHARED, which is correct for almost every repository -- most
have no live state in their tree at all, and for them this is inert.
That inertness is the portability property.
"""

import os
import subprocess

from amik.core import board


def _write(root, text):
    with open(os.path.join(root, "amik", "amik.toml"), "w") as f:
        f.write(text)


def _git_init(root, branch="main"):
    subprocess.run(["git", "init", "-q", "-b", branch, root], check=True)
    subprocess.run(["git", "-C", root, "config", "user.email", "t@t"],
                   check=True)
    subprocess.run(["git", "-C", root, "config", "user.name", "t"],
                   check=True)
    open(os.path.join(root, "seed"), "w").close()
    subprocess.run(["git", "-C", root, "add", "-A"], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "first"], check=True)


def test_an_explicit_trunk_wins(project):
    _write(project, 'verify = "true"\ntrunk = "develop"\n')
    assert board.amik_project(project)["data"]["trunk"] == "develop"


def test_shared_defaults_to_empty(project):
    """Inert without a declaration — a repository that says nothing
    behaves exactly as it does today."""
    _write(project, 'verify = "true"\n')
    assert board.amik_project(project)["data"]["shared"] == []


def test_shared_is_read_as_a_list(project):
    _write(project, 'verify = "true"\n[state]\nshared = ["a/b", "c/*.json"]\n')
    assert board.amik_project(project)["data"]["shared"] == ["a/b", "c/*.json"]


def test_a_malformed_shared_falls_back_to_NOTHING(project):
    """A typo means nothing is shared rather than everything. The cheap
    direction of a mistake here is a branch owning a file it should not;
    the expensive one is Amik refusing to let a card edit anything
    because a malformed key made the whole tree look shared."""
    _write(project, 'verify = "true"\n[state]\nshared = "one/path"\n')
    assert board.amik_project(project)["data"]["shared"] == []


def test_non_string_entries_are_dropped(project):
    _write(project, 'verify = "true"\n[state]\nshared = ["a", 3, "", "b"]\n')
    assert board.amik_project(project)["data"]["shared"] == ["a", "b"]


def test_the_trunk_is_DETECTED_when_absent(tmp_path):
    """No remote here, so the local-branch fallback is the path that
    actually runs in this instance."""
    root = str(tmp_path)
    _git_init(root, "main")
    os.makedirs(os.path.join(root, "amik"), exist_ok=True)
    open(os.path.join(root, "amik", "board.jsonl"), "w").close()
    _write(root, 'verify = "true"\n')
    assert board.amik_project(root)["data"]["trunk"] == "main"


def test_master_is_detected_too(tmp_path):
    root = str(tmp_path)
    _git_init(root, "master")
    os.makedirs(os.path.join(root, "amik"), exist_ok=True)
    open(os.path.join(root, "amik", "board.jsonl"), "w").close()
    _write(root, 'verify = "true"\n')
    assert board.amik_project(root)["data"]["trunk"] == "master"


def test_an_undetectable_trunk_is_EMPTY_not_a_guess(project):
    """Not a git repository at all. Empty, so the caller refuses --
    never a default that quietly branches from something."""
    _write(project, 'verify = "true"\n')
    assert board.amik_project(project)["data"]["trunk"] == ""

