"""Putting the starter board into a project.

`starter/` ships with the package and is never touched: it is a
template, and a template that can be edited by the thing it seeds is
not one.

Two ways in, one writer. `amik init` is the deliberate one. `amik serve`
calls `seed_if_empty` on a project with nothing in it, so the install is
`pip install`, `cd`, `serve` — a second command to see anything at all
is the step that gets skipped and then asked about. Both arrive here,
because a copy of the condition in the server would be a second answer
to one question.
"""
import os
import shutil


STARTER = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "starter")


def _prose(root):
    """Card files in the folder, whether or not a board names them.

    The guard below asks about these as well as about the board, because
    `copytree` writes over a matching filename and the starter's seven
    ids are the likeliest ones to match. A project that lost its board
    and kept its prose is exactly where the board check alone would let
    seven example cards land on top of somebody's writing.
    """
    try:
        return sorted(n for n in os.listdir(os.path.join(root, "amik",
                                                         "cards"))
                      if n.endswith(".md"))
    except OSError:
        return []


def init(root):
    """Copy the starter board into `<root>/amik/`.

    REFUSES an instance that already has a board, or card prose with no
    board to name it. Overwriting somebody's work with seven example
    cards is the most destructive thing this tool can do, and it is one
    mistyped command away — so the checks come before anything is
    created, and a refusal writes nothing at all rather than leaving a
    half-seeded folder.

    Prose without a board is a CONTRADICTION, and this board's law is
    that a contradiction is reported rather than repaired. Which of the
    two — the missing board or the surviving cards — was meant is the
    owner's call.

    The config arrives under its WORKING name. The `.example` suffix is
    for the repository, where it sits beside a real one; a project
    should get a file it can edit rather than one it has to rename
    before anything reads it. An existing one is LEFT ALONE: the guard
    above is about the board, so a project that tracks its config and
    ignores its board — which is what this repository now does — reaches
    here by the ordinary way in rather than by a mistake, and finding
    its verify command replaced by the example would be this function
    doing the one thing it exists to prevent.
    """
    here = os.path.join(root, "amik")
    board = os.path.join(here, "board.jsonl")
    if os.path.exists(board):
        return {"ok": False,
                "reason": f"{board} already exists — this instance has a "
                          f"board, and init will not write over one"}
    stray = _prose(root)
    if stray:
        return {"ok": False,
                "reason": f"{os.path.join(here, 'cards')} holds card prose "
                          f"({', '.join(stray[:3])}"
                          f"{' and more' if len(stray) > 3 else ''}) but "
                          f"there is no board naming it — that is a "
                          f"contradiction, and init will not write over "
                          f"prose to resolve one"}
    config = os.path.join(here, "amik.toml")
    wrote_config = not os.path.exists(config)
    try:
        os.makedirs(here, exist_ok=True)
        shutil.copy(os.path.join(STARTER, "board.jsonl"), board)
        shutil.copytree(os.path.join(STARTER, "cards"),
                        os.path.join(here, "cards"), dirs_exist_ok=True)
        if wrote_config:
            shutil.copy(os.path.join(STARTER, "amik.toml.example"), config)
    except (OSError, shutil.Error) as exc:
        return {"ok": False, "reason": f"could not write: {exc}"}
    return {"ok": True, "data": {"root": root, "board": board,
                                 "cards": len(_prose(root)),
                                 "config": wrote_config}}


def seed_if_empty(root):
    """A board for a project that has none, on the way to serving it.

    Three answers, and they are different on purpose. Seeded: files
    appeared in somebody's repository, which is the loudest thing this
    tool does on a first run and has to be said. Not seeded: a board was
    already there, nothing happened, and a line about it on every single
    start is a line nobody reads by the third one. Refused: something is
    in the way that a person has to look at.

    **A root that does not exist is never seeded.** A mistyped `--root`
    would otherwise build a whole board tree somewhere nobody meant, and
    a daemon pointed at `code/amik` where the directory is `Code/amik`
    is a case-insensitive filesystem away from being exactly that
    mistake. `init` still creates what it needs, because asking for a
    board is different from happening to start a server.
    """
    if not os.path.isdir(root):
        return {"ok": False,
                "reason": f"{root} does not exist, so no starter board was "
                          f"written — check the path before creating it"}
    if os.path.exists(os.path.join(root, "amik", "board.jsonl")):
        return {"ok": True, "data": {"seeded": False}}
    res = init(root)
    if not res["ok"]:
        return res
    return {"ok": True, "data": dict(res["data"], seeded=True)}
