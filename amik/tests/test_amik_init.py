"""`amik init` puts the starter board into a project.

It refuses an instance that already has one. Overwriting somebody's
board with seven example cards is the single most destructive thing
this tool could do, and it is one mistyped command away -- so the check
is the first line and a refusal writes nothing at all.
"""

import json
import os

from amik.core import init


def _board(root):
    return os.path.join(root, "amik", "board.jsonl")


def test_it_creates_the_board_and_every_card(tmp_path):
    root = str(tmp_path)
    res = init.init(root)
    assert res["ok"], res
    rows = [json.loads(l) for l in open(_board(root)) if l.strip()]
    assert len(rows) == 7
    for r in rows:
        assert os.path.isfile(os.path.join(
            root, "amik", "cards", r["id"] + ".md")), r["id"]


def test_it_writes_a_config_under_its_WORKING_name(tmp_path):
    """The `.example` suffix is for the repository. A project gets a
    file it can edit, not one it has to rename first."""
    root = str(tmp_path)
    init.init(root)
    assert os.path.isfile(os.path.join(root, "amik", "amik.toml"))
    assert not os.path.exists(
        os.path.join(root, "amik", "amik.toml.example"))


def test_the_new_board_is_readable_by_the_reader(tmp_path):
    """The one check that matters: what it wrote is a board Amik can
    open, not seven files that happen to be on disk."""
    from amik.core import board
    root = str(tmp_path)
    init.init(root)
    data = board.amik(root)
    assert data["ok"], data
    seen = [c["title"] for col in data["data"]["columns"]
            for c in col["cards"]]
    assert len(seen) == 7


def test_it_REFUSES_an_instance_that_already_has_a_board(tmp_path):
    root = str(tmp_path)
    init.init(root)
    again = init.init(root)
    assert again["ok"] is False
    assert "already" in again["reason"]


def test_a_refusal_changes_NOTHING(tmp_path):
    """The destructive case, stated as the thing it must not do."""
    root = str(tmp_path)
    init.init(root)
    with open(_board(root), "w") as f:
        f.write('{"id": "mine", "title": "Real work", "status": "todo",'
                ' "rank": 1}\n')
    os.remove(os.path.join(root, "amik", "amik.toml"))
    init.init(root)
    assert "Real work" in open(_board(root)).read(), "it overwrote a board"
    assert not os.path.exists(os.path.join(root, "amik", "amik.toml")), \
        "a refusal wrote something anyway"


def test_it_works_in_a_directory_that_does_not_exist_yet(tmp_path):
    root = os.path.join(str(tmp_path), "brand", "new")
    assert init.init(root)["ok"]
    assert os.path.isfile(_board(root))


def test_it_is_reachable_from_the_command_line(tmp_path):
    """By RUNNING it. Grepping `main` for the string "init" passed while
    the subcommand was wired to nothing."""
    from amik.__main__ import main
    root = str(tmp_path)
    assert main(["--root", root, "init"]) == 0
    assert os.path.isfile(_board(root))


# ── what else is already in the folder ──────────────────────────────

def test_it_REFUSES_cards_that_have_no_board(tmp_path):
    """A card file with no row is a CONTRADICTION, and this board's law
    is that a contradiction is reported rather than repaired. It is also
    the destructive case the board check alone misses: `copytree` writes
    over a matching filename, so prose survives losing its board only if
    the guard asks about prose too."""
    root = str(tmp_path)
    cards = os.path.join(root, "amik", "cards")
    os.makedirs(cards)
    with open(os.path.join(cards, "this-card-is-already-done.md"), "w") as f:
        f.write("my own prose, on a card id the starter also uses\n")
    res = init.init(root)
    assert res["ok"] is False
    assert "cards" in res["reason"]
    assert "my own prose" in open(
        os.path.join(cards, "this-card-is-already-done.md")).read(), \
        "it wrote over prose"
    assert not os.path.exists(_board(root)), "a refusal wrote a board"


def test_it_does_not_write_over_a_config_that_is_already_there(tmp_path):
    """The fresh clone of a repository that TRACKS its config and
    ignores its board is exactly this state, so it is reachable by the
    ordinary way in rather than by a mistake."""
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "amik"))
    with open(os.path.join(root, "amik", "amik.toml"), "w") as f:
        f.write('verify = "my-own-tests"\n')
    res = init.init(root)
    assert res["ok"], res
    assert "my-own-tests" in open(
        os.path.join(root, "amik", "amik.toml")).read(), \
        "it replaced a config somebody wrote"
    assert os.path.isfile(_board(root)), "it refused instead of seeding"
