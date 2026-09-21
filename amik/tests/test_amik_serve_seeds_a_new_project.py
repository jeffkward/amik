"""`amik serve` on a project with nothing in it lays the starter down.

The install is `pip install`, `cd`, `amik serve` — and a board appears.
Making somebody run a second command to see anything at all is the step
that gets skipped and then asked about.

It seeds through `init` rather than through a copy of init's logic: one
writer for "put a starter board down", and init's guard is what decides
whether there is anything to put it next to.

Two things it must NOT do. It never writes over prose — cards present
with no board is a contradiction, reported and not repaired. And it
never seeds a root that does not exist: a mistyped `--root` would
otherwise build a whole board tree somewhere nobody meant, which this
machine came within a case-insensitive filesystem of doing.
"""

import inspect
import os

from amik.app import server
from amik.core import init


def _cards(root):
    return os.path.join(root, "amik", "cards")


def _board(root):
    return os.path.join(root, "amik", "board.jsonl")


# ── when it seeds ───────────────────────────────────────────────────

def test_a_bare_directory_gets_the_starter_board(tmp_path):
    root = str(tmp_path)
    res = init.seed_if_empty(root)
    assert res["ok"], res
    assert res["data"]["seeded"] is True
    assert os.path.isfile(_board(root))
    assert len(os.listdir(_cards(root))) == 7


def test_a_board_that_is_already_there_is_left_alone_and_QUIETLY(tmp_path):
    """Nothing happened and nothing is worth saying. A line every single
    start is a line nobody reads by the third one."""
    root = str(tmp_path)
    init.seed_if_empty(root)
    with open(_board(root), "w") as f:
        f.write('{"id": "mine", "title": "Real work", "status": "todo",'
                ' "rank": 1}\n')
    again = init.seed_if_empty(root)
    assert again["ok"], again
    assert again["data"]["seeded"] is False
    assert "Real work" in open(_board(root)).read()


def test_a_root_that_does_not_exist_is_NOT_seeded(tmp_path):
    """The typo guard. A `--root` naming `code/thing` where the real
    directory is `Code/thing` builds a board nobody asked for, and the
    install flow this exists for is `cd myproject && amik serve`, where
    the root is the working directory and cannot be missing."""
    root = os.path.join(str(tmp_path), "no-such-directory")
    res = init.seed_if_empty(root)
    assert res["ok"] is False
    assert "does not exist" in res["reason"]
    assert not os.path.exists(root), "it created the directory anyway"


def test_serving_a_bare_directory_leaves_a_board_behind(tmp_path, capsys):
    root = str(tmp_path)
    assert server.serve(root, port=0, loop=False, forever=False) is True
    assert os.path.isfile(_board(root))
    assert "starter board" in capsys.readouterr().out


def test_a_refusal_to_seed_is_SAID_not_swallowed(tmp_path, capsys):
    root = str(tmp_path)
    os.makedirs(_cards(root))
    with open(os.path.join(_cards(root), "mine.md"), "w") as f:
        f.write("prose\n")
    server.serve(root, port=0, loop=False, forever=False)
    assert "cards" in capsys.readouterr().out
