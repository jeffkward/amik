"""Amik's own test suite — no host application, no face.

An Amik instance is a directory with `amik/board.jsonl` in it. That is
the whole bootstrap, which is the point: nothing here knows what project
Amik is embedded in.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from amik.core import edit                             # noqa: E402

# Two roots, and confusing them is the easiest mistake here. PACKAGE is
# where Amik's own code lives; INSTANCE is the directory HOLDING an
# `amik/` folder, which is what every reader and writer takes as `root`.
PACKAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCE = os.path.dirname(PACKAGE)
# The REPOSITORY, where LICENSE, pyproject.toml and .gitignore live.
# A third thing, and only since the package stopped being the whole
# repository: `INSTANCE` is whatever directory holds an `amik/`, and
# for this checkout that happens to be the repository too. Tests
# about PACKAGING must say REPO, or they pass here and fail in every
# project that installs Amik rather than containing it.
REPO = INSTANCE

TOML = '''verify = "true"
laws = "LAWS.md"
branch = "card/"
armed = false
'''


def write_board(root, rows, prose=None):
    """Lay a board down the way the doors would have.

    Rows go to `board.jsonl` verbatim — a test that needs a malformed
    line passes a raw string and it is written untouched. Prose goes
    through `write_prose`, so a card file is never created by a route the
    real writer does not use.
    """
    folder = os.path.join(root, "amik")
    os.makedirs(os.path.join(folder, "cards"), exist_ok=True)
    lines = [r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
             for r in rows]
    with open(os.path.join(folder, "board.jsonl"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    for item_id, body in (prose or {}).items():
        edit.write_prose(root, item_id, body)
    return root


@pytest.fixture()
def instance(tmp_path):
    """A BARE directory — no `amik/` at all.

    That is deliberate and it is what most tests want: "this instance has
    no board" is a real state with real behaviour (every route 404s), and
    a fixture that quietly created one would make those tests impossible
    to write. Tests that want a board call `write_board` or take
    `scenario`.
    """
    return str(tmp_path)


@pytest.fixture()
def empty_board(instance):
    """An instance holding a board with no cards on it — different from
    having no board, and the difference is the whole point of the
    fixture above."""
    return write_board(instance, [])


@pytest.fixture()
def project(empty_board):
    """A board whose project also declares itself. `verify` has no
    default, so a project that has not declared cannot be agent-worked —
    which makes the declaration a separate fact from the board, and this
    a separate fixture."""
    with open(os.path.join(empty_board, "amik", "amik.toml"), "w",
              encoding="utf-8") as f:
        f.write(TOML)
    return empty_board


@pytest.fixture()
def scenario(instance):
    """`scenario("ready_plain", "blocked_unanswered")` → a board holding
    exactly those, from `scenarios.py`. No argument means every one."""
    import scenarios

    def build(*names):
        rows, prose = scenarios.board(*names)
        return write_board(instance, rows, prose)
    return build


class _Response:
    """What a test needs from a response: the status and the text."""

    def __init__(self, status, headers, body):
        self.status_code = status
        self.headers = headers
        self.content = body
        self.text = body.decode("utf-8", "replace")

    def json(self):
        import json
        return json.loads(self.text)


class Client:
    """A test client over `handle()` — no server, no host, no framework.

    It speaks the embedded shape (`base="/amik"`), because that is the
    mode with a prefix to get wrong; standalone is covered directly in
    `test_handle.py`. Form bodies are encoded here so a test can pass a
    dict the way it would to any HTTP client.
    """

    def __init__(self, root, base="/amik"):
        self.root = root
        self.base = base

    def _call(self, method, path, data=None):
        import urllib.parse
        from amik.app.handle import handle
        body = urllib.parse.urlencode(data or {}).encode("utf-8")
        return _Response(*handle(method, path, None, body,
                                 root=self.root, base=self.base))

    def get(self, path):
        return self._call("GET", path)

    def post(self, path, data=None):
        return self._call("POST", path, data)

    def patch(self, path, data=None):
        return self._call("PATCH", path, data)

    def delete(self, path, data=None):
        return self._call("DELETE", path, data)


@pytest.fixture()
def client(instance):
    return Client(instance)


@pytest.fixture()
def repo_with_card(instance):
    """An instance that is a real git repository with one card already
    placed on its own branch.

    The verbs under test act on refs, so mocking git here would test the
    mock. The cost is one `git init` per test, which is milliseconds.
    """
    import subprocess
    root = str(instance)
    write_board(root, [{"id": "a-card", "title": "A card",
                        "status": "review", "planning": None, "rank": 1,
                        "created_at": "2026-01-01T00:00:00",
                        "updated_at": "2026-01-01T00:00:00"}])
    with open(os.path.join(root, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\ntrunk = "main"\n')
    for args in (["init", "-q", "-b", "main", root],):
        subprocess.run(["git", *args], check=True)
    for args in (["config", "user.email", "t@t"], ["config", "user.name", "t"],
                 ["add", "-A"], ["commit", "-qm", "first"]):
        subprocess.run(["git", "-C", root, *args], check=True)
    from amik.core import git
    git.start(root, "a-card", "main", [])
    with open(os.path.join(root, "work.py"), "w") as f:
        f.write("done = True\n")
    subprocess.run(["git", "-C", root, "add", "-A"], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "the work"],
                   check=True)
    git.finish(root, "main", [])
    return root
