"""Amik may not name the project it grew up in.

It is going to be copied into other repositories, so a stray reference to
this one is a bug that only shows up in someone else's checkout — long
after it is cheap to fix. The guard runs here rather than in review
because a name is exactly the kind of thing a careful reader stops
seeing.

Two things are exempt and both deliberately: `amik.toml` is the file
whose whole job is to name host-specific things, and the board and its
cards are this project's own content rather than Amik's code.
"""
import os
import re

from conftest import PACKAGE

# What would be wrong in ANY other checkout. Two kinds, and the first
# is the one that keeps mattering.
#
# MACHINE PATHS: an absolute home directory, or a `~/Capitalised` path.
# These are the leaks a public repository will actually produce, and
# they are wrong for everyone rather than wrong for one person.
#
# BORROWED NAMES: the project Amik was extracted from. Kept as a short
# regression list rather than deleted -- the extraction is how these
# got in, and a name is exactly the kind of thing a careful reader
# stops seeing. The pattern once caught `makwa` and `jeff` and stayed
# green while `cd workspaces/face && ...` sat in a docstring, because a
# leak does not have to say anybody's name to be one.
#
# Add to it when a new one earns the right to be here, never by
# widening into something that matches ordinary prose.
# TWO patterns, because they need different case rules and folding them
# into one silently broke the first: `~/[A-Z]` under `re.I` matches a
# lowercase letter too, so `cd ~/your-project` — the README's own
# example — read as a leak. The guard below caught it.
PATHS = re.compile(r"/Users/|/home/[a-z]|~/[A-Z]")
NAMES = re.compile(r"\bmakwa\b|\bjeff\b|workspaces/|data/brain|face-venv",
                   re.I)
# VOCABULARY, not names -- and this half was added after the first half
# missed a whole application's worth of it. A dead `[[wikilink]]`
# resolver shipped in a published release: it called a module that does
# not exist here, its docstring named a real person, and a stylesheet
# class called `brain-article` was styling this board's own prose. None
# of it said "makwa" or a path, so none of it tripped the guard above.
#
# A leak is a WORD from somewhere else, not only a name from somewhere
# else. These are the ones that were actually found; add to the list
# when another is.
VOCAB = re.compile(r"\bbrain\b|\bvault\b|\bobsidian\b"
                   r"|\[\[[a-z][a-z0-9-]*\]\]|wl-miss|wl-preview",
                   re.I)


def foreign(line):
    """True when a line names a machine, a borrowed project, or borrowed
    vocabulary."""
    return bool(PATHS.search(line) or NAMES.search(line)
                or VOCAB.search(line))

EXEMPT = {
    # its purpose is to carry this project's own paths and commands
    "amik.toml",
    # this file has to name what it forbids
    "test_amik_is_portable.py",
    # ATTRIBUTION is not a leak. The author's name in a licence and in
    # a package's author field is the point of both files -- and it is
    # the only place the name should appear, which is what makes the
    # rest of the pattern meaningful rather than pedantic.
    "LICENSE",
    "pyproject.toml",
}

EXEMPT_DIRS = {"cards", "prototypes", "runs", "__pycache__"}


def _sources():
    for base, dirs, files in os.walk(PACKAGE):
        dirs[:] = [d for d in dirs if d not in EXEMPT_DIRS]
        for name in files:
            if name in EXEMPT or name == "board.jsonl":
                continue
            if not name.endswith((".py", ".md", ".html", ".css", ".js",
                                  ".toml")):
                continue
            yield os.path.join(base, name)


def test_nothing_in_amik_names_the_project_it_grew_up_in():
    offenders = {}
    for path in _sources():
        with open(path, encoding="utf-8", errors="replace") as f:
            hits = [i + 1 for i, line in enumerate(f) if foreign(line)]
        if hits:
            offenders[os.path.relpath(path, PACKAGE)] = hits
    assert not offenders, (
        "Amik names the project it grew up in, which is a bug in any other "
        "checkout: {}".format(offenders))


def test_the_guard_can_actually_see_a_violation(tmp_path):
    """The guard on the guard. A walk that matched nothing would pass
    silently forever, which is the failure this file exists to prevent."""
    assert foreign("/Users/someone/code/amik"), "an absolute home"
    assert foreign("run it from ~/Makwa/amik"), "a capitalised home path"
    assert foreign("the makwa face embeds it"), "a borrowed name"
    assert not foreign("the board is a folder you copy"), "ordinary prose"
    # The README's own install line. It read as a leak while the two
    # patterns were one, which is what this guard is for.
    assert not foreign("cd ~/your-project && amik serve"), "a generic path"
    # Vocabulary, which the guard did not see until it had already
    # shipped a whole feature's worth of somebody else's words.
    assert foreign("the brain sidebar renders it"), "a borrowed noun"
    assert foreign('href="/brain/person/dave"'), "a borrowed route"
    assert foreign("resolve [[some-page]] against the vault"), "wiki syntax"
    assert not foreign("a card owing needs-brainstorm is held"), "our own rung"


def test_the_engine_imports_nothing_outside_the_standard_library():
    """`amik/core` is what a project with no web UI gets. Jinja belongs to
    the app; a dependency creeping into the engine would put a pip
    install between someone and reading their own board."""
    import ast
    core = os.path.join(PACKAGE, "core")
    allowed = {"os", "json", "re", "tomllib", "subprocess", "datetime",
               "shutil",
               "time", "shlex"}
    for name in os.listdir(core):
        if not name.endswith(".py"):
            continue
        tree = ast.parse(open(os.path.join(core, name)).read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert a.name.split(".")[0] in allowed, (name, a.name)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                assert (node.module or "").split(".")[0] in allowed, (
                    name, node.module)


def test_runtime_state_is_ignored_and_the_rule_travels():
    """The ignore lives in `amik/.gitignore`, not the repository root.

    A rule left behind at the root is a lock file committed on someone
    else's first run — and they would have no idea why their checkout
    thinks a card is permanently being worked.

    `prototypes/` joined the list on 2026-09-17. A tracked design pass
    lives on one branch and is invisible from every other, which is how
    one went missing and a branch switcher got proposed to find it.
    """
    path = os.path.join(PACKAGE, ".gitignore")
    assert os.path.isfile(path), "amik/ carries no .gitignore of its own"
    rules = open(path, encoding="utf-8").read()
    for name in (".lock", ".seen", ".verify", "runs/", "prototypes/"):
        assert name in rules, name

