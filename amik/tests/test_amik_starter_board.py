"""The starter board is the onboarding, so every card must be the thing
it says it is.

A card claiming a mechanic and not carrying it is worse than no starter
board at all: the first thing a new user learns is that the board lies.
"""

import json
import os
import tomllib

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STARTER = os.path.join(HERE, "starter")


def _rows():
    with open(os.path.join(STARTER, "board.jsonl")) as f:
        return [json.loads(l) for l in f if l.strip()]


def _by(fragment):
    for r in _rows():
        if fragment in r["title"]:
            return r
    raise AssertionError("no starter card matching " + fragment)


def _prose(row):
    with open(os.path.join(STARTER, "cards", row["id"] + ".md")) as f:
        return f.read()


# ── the board and its files agree ───────────────────────────────────

def test_every_row_has_its_card_file():
    for r in _rows():
        assert os.path.isfile(
            os.path.join(STARTER, "cards", r["id"] + ".md")), r["id"]


def test_no_orphan_card_files():
    ids = {r["id"] for r in _rows()}
    for name in os.listdir(os.path.join(STARTER, "cards")):
        assert name[:-3] in ids, name


def test_ranks_are_contiguous_within_each_column():
    from collections import defaultdict
    cols = defaultdict(list)
    for r in _rows():
        cols[r["status"]].append(r["rank"])
    for status, ranks in cols.items():
        assert sorted(ranks) == list(range(1, len(ranks) + 1)), status


# ── each card is the mechanic it claims ─────────────────────────────

def test_the_pause_card_actually_pauses():
    assert _by("pauses everything below")["halt"] is True


def test_the_prototype_card_carries_the_toggle_AND_the_forced_pause():
    """A design pass forces the pause on and locks it. A starter card
    showing one without the other teaches the wrong rule on day one."""
    row = _by("creates a prototype")
    assert row["requires_prototype"] is True
    assert row["halt"] is True


def test_the_question_card_has_an_UNANSWERED_question():
    prose = _prose(_by("asks you a question"))
    assert "## Questions" in prose
    after = prose[prose.index("### "):].split("\n", 1)[1]
    # A leading blockquote is the ASKER's context, not an answer.
    body = [l for l in after.split("\n")
            if l.strip() and not l.lstrip().startswith(">")]
    assert body == [], "the starter question arrives already answered"


def test_the_contradiction_card_is_in_ready_AND_owes_a_rung():
    """The warning needs both halves. One without the other is just an
    ordinary card."""
    row = _by("cannot be built")
    assert row["status"] == "ready"
    assert row["planning"] == "needs-brainstorm"


def test_the_abandon_card_is_somewhere_you_can_abandon_it_FROM():
    row = _by("not worth doing")
    assert row["status"] not in ("done", "abandoned")


def test_the_finished_card_has_an_outcome():
    assert "## Outcome" in _prose(_by("already done"))


# ── the example config ──────────────────────────────────────────────

def _example():
    with open(os.path.join(STARTER, "amik.toml.example"), "rb") as f:
        return tomllib.load(f)


def test_the_example_arms_the_board():
    """A fresh install cannot run anything anyway — verify and the
    agent command both refuse without a declaration — so a false here
    is a step that looks like the obstacle and is not."""
    assert _example()["armed"] is True


def test_armed_is_TOP_LEVEL_and_in_no_table():
    """A TOML table header captures every key below it, so `armed`
    written under a table becomes `<table>.armed` — absent, which means
    false, which silently turns the board off with nothing failing.

    This bit three separate times while the example was being written,
    which is why the file puts every plain key above every table and
    says so at the top.
    """
    cfg = _example()
    assert cfg.get("armed") is True
    for name, value in cfg.items():
        if isinstance(value, dict):
            assert "armed" not in value, name


def test_VERIFY_is_the_one_key_that_ships_empty():
    """The only thing a fresh install still has to declare, and the only
    one that genuinely cannot be guessed: what "green" means here.
    Guessing a test command is how a loop reports success on nothing."""
    assert _example()["verify"] == ""


def test_the_agent_command_ships_WORKING_rather_than_empty():
    """Amik names no vendor was the principle, and it lost to what it
    cost -- a fresh install that could not work a card until somebody
    found the blanks. The flags are not decoration: leave Glob or Grep
    off and an unattended agent asks permission mid-card and waits
    forever, which looks exactly like a board with nothing to do."""
    command = _example()["agent"]["command"]
    assert command.startswith("claude -p")
    for flag in ("--setting-sources project", "--output-format stream-json"):
        assert flag in command, flag
    for tool in ("Read", "Write", "Edit", "Glob", "Grep", "Bash"):
        assert tool in command.split("--allowedTools", 1)[1], tool


def test_the_board_and_its_cards_ship_as_SHARED_state():
    """Unprotected, a card's own close is committed onto that card's
    branch and vanishes when the tree returns to the trunk -- so the
    loop picks up the card it just finished. Harmless where the board is
    ignored; load-bearing where it is tracked, which is what this tool
    recommends."""
    shared = _example()["state"]["shared"]
    assert "amik/board.jsonl" in shared
    assert "amik/cards" in shared


def test_the_laws_key_points_at_something_by_default():
    """A project reaching for this usually has a CLAUDE.md, and a file
    that is not there costs nothing: the brief carries Amik's own laws
    and no others."""
    assert _example()["laws"] == "CLAUDE.md"


def test_every_key_the_reader_supports_appears_in_the_example():
    """A key the config reader honours and the example never names is a
    feature nobody will find. `notify_on` was exactly that: thirteen
    tests, read on every tick, and absent from the file people actually
    open.

    Mentioned in a comment counts — several keys are deliberately left
    undeclared so their absence means something, and showing them
    commented is how the example says both things at once.
    """
    import re
    from conftest import PACKAGE
    reader = open(os.path.join(PACKAGE, "core", "board.py"),
                  encoding="utf-8").read()
    supported = set()
    for pattern in (r'cfg\.get\("([a-z_]+)"', r'\)\.get\(\s*"([a-z_]+)"',
                    r'_text\("([a-z_]+)"\)'):
        supported |= set(re.findall(pattern, reader))
    # Structures and card fields the same call shapes also pull out.
    supported -= {"data", "status", "id", "rank", "title", "body", "type",
                  "slug", "loop", "state", "agent", "prototypes",
                  "planning", "group", "cards"}
    text = open(os.path.join(PACKAGE, "starter", "amik.toml.example"),
                encoding="utf-8").read()
    shown = (set(re.findall(r"^([a-z_]+)\s*=", text, re.M))
             | set(re.findall(r"^#\s+([a-z_]+)\s*=", text, re.M)))
    missing = sorted(supported - shown)
    assert not missing, f"supported but undocumented: {missing}"
