"""The board says what branch the tree is on, and what just happened.

With most work landing on master unreviewed, the commit list IS the
review surface — the thing that makes giving up the per-card gate
informed rather than blind. And the branch name answers a question that
cost a real confusion: whether the work you are looking for is even in
the tree the face is serving.
"""
import subprocess

from amik.core import board as readers


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True)


def _repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "f.txt").write_text("one\n")
    _git(tmp_path, "add", "f.txt")
    _git(tmp_path, "commit", "-qm", "the first thing")
    return tmp_path


def test_it_names_the_branch(tmp_path):
    out = readers.git_status(str(_repo(tmp_path)))
    assert out["ok"]
    assert out["data"]["branch"] in ("main", "master")


def test_it_lists_recent_commits_newest_first(tmp_path):
    root = _repo(tmp_path)
    (root / "f.txt").write_text("two\n")
    _git(root, "commit", "-aqm", "the second thing")
    subjects = [c["subject"] for c in
                readers.git_status(str(root))["data"]["commits"]]
    assert subjects == ["the second thing", "the first thing"]


def test_it_is_bounded(tmp_path):
    root = _repo(tmp_path)
    for i in range(10):
        (root / "f.txt").write_text(f"{i}\n")
        _git(root, "commit", "-aqm", f"commit {i}")
    assert len(readers.git_status(str(root), n=7)["data"]["commits"]) == 7


def test_a_directory_that_is_not_a_repo_is_not_an_error(tmp_path):
    """Readers never raise. A ported instance may not be a git checkout
    at all, and the board still has to render."""
    out = readers.git_status(str(tmp_path))
    assert out["ok"] is False
    assert out["reason"]


def test_the_board_renders_the_line(instance, client):
    """The line is derived from the REPOSITORY, not the board, so a
    fixture directory has to actually be one — a bare temp dir renders
    nothing here, and rightly."""
    import subprocess
    from test_amik_page import _board
    _board(instance, [{"id": "a", "title": "T", "status": "ready",
                       "planning": None, "rank": 1,
                       "created_at": "2026-09-14",
                       "updated_at": "2026-09-14"}])
    assert "akgit" not in client.get("/amik").text
    for cmd in (["init", "-q"], ["config", "user.email", "t@example.com"],
                ["config", "user.name", "T"], ["add", "-A"],
                ["commit", "-qm", "first"]):
        subprocess.run(["git", "-C", instance] + cmd, check=True,
                       capture_output=True)
    assert "akgit" in client.get("/amik").text
