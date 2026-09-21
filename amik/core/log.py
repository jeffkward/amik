"""What happened to this board, one JSON object per line.

`board.jsonl` is state and answers "where is everything now". This
answers "how did it get there", which the board cannot: a row carries
one `updated_at` and forgets every move before the last.

**Structural events only.** Moves, creations, questions, answers,
outcomes, toggles, branches, discards, deletions. NOT title and body
edits -- those fire on every save, and a log that records them buries
the four lines somebody actually wanted under a keystroke history. The
prose already has a better record of itself in `git diff`.

**It travels with the board.** A project that tracks its board tracks
its log, and a card's history then arrives in the same commits as the
code it describes. This repository ignores both, because its board is
whoever is working here rather than the project.

**Append-only, and it never raises.** A write that could not happen
must not fail the move it was describing -- the board is the record and
this is the account of it, and losing a line costs a gap in a story
rather than a card in the wrong column.
"""
import json
import os
import time

PATH = "amik/log.jsonl"


def actor(by=None):
    """Who did this: told, then the environment, then unknown.

    Explicit first because the SERVER and the loop share one process --
    a request handled while the ticker runs would race a process-wide
    variable and attribute a drag to the loop. The two callers that
    cannot be confused pass it outright.

    The environment is for the AGENT, which the loop spawns as its own
    process and can hand a variable no card can rewrite. That is the
    same reasoning the outcome's attribution uses: what the environment
    knows cannot be misreported, and what only the agent knows is
    passed.

    "unknown" is written rather than guessed. A gap you can see is a
    gap somebody closes.
    """
    if by and str(by).strip():
        return str(by).strip()
    return (os.environ.get("AMIK_ACTOR") or "").strip() or "unknown"


def program(command):
    """The agent's PROGRAM, out of its whole command line.

    `claude -p --output-format stream-json --verbose --setting-sources
    project --allowedTools Read,Write,Edit,Glob,Grep,Bash` on every card
    is a line nobody reads. The name is the part that answers "which
    agent took this", which is the question a board running more than
    one has to be able to ask of its own history.
    """
    import shlex
    try:
        parts = shlex.split(str(command or ""))
    except ValueError:
        parts = str(command or "").split()
    return os.path.basename(parts[0]) if parts else ""


def note(root, card, event, by=None, **facts):
    """Append one event. Returns nothing and raises nothing.

    `facts` are the event's own fields -- `from`/`to` for a move, the
    count for questions and answers, the model and agent for work. They
    are written in the order given, after the four every line carries,
    so a human scanning the file reads the same four columns first
    every time.

    A fact that is None is dropped rather than written null: a line
    says what is known, and "model": null on every hand-made move is
    noise in a file whose whole value is being readable.
    """
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "card": str(card or ""),
             "event": str(event),
             "by": actor(by)}
    for key, value in facts.items():
        if value is not None and value != "":
            entry[key] = value
    try:
        line = json.dumps(entry, ensure_ascii=False) + "\n"
    except (TypeError, ValueError):
        return
    path = os.path.join(root, PATH)
    # A HEALING append. A process killed mid-write leaves a line with no
    # newline on the end, and appending straight onto that glues the
    # next entry to the broken one -- which loses a second event to a
    # fault that only damaged the first. The torn line stays torn and
    # the reader skips it; nothing after it is taken down with it.
    try:
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                line = "\n" + line
    except OSError:
        pass                      # no file yet, or an empty one
    try:
        os.makedirs(os.path.join(root, "amik"), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def read(root, limit=None, card=None):
    """The log, oldest first, as a list of dicts.

    A malformed line is SKIPPED rather than fatal, the same way the
    board reader treats one: this file is appended to by a process that
    can be killed mid-write, and one torn line must not take the
    history with it.
    """
    entries = []
    try:
        with open(os.path.join(root, PATH), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if isinstance(entry, dict) and (
                        card is None or entry.get("card") == card):
                    entries.append(entry)
    except OSError:
        return []
    return entries[-limit:] if limit else entries


def line(entry):
    """One entry as a sentence, for a person reading a terminal."""
    who = entry.get("by") or "unknown"
    card = entry.get("card") or "(no card)"
    event = entry.get("event")
    if event == "move":
        what = "moved from {!r} to {!r}".format(
            entry.get("from") or "?", entry.get("to") or "?")
    elif event == "create":
        what = "created in {!r}".format(entry.get("to") or "?")
    elif event == "ask":
        what = "{} question(s) asked".format(entry.get("count", 1))
    elif event == "answer":
        what = "{} question(s) answered".format(entry.get("count", 1))
    elif event == "toggle":
        what = "{} turned {}".format(entry.get("field") or "?",
                                     "on" if entry.get("value") else "off")
    elif event == "branch":
        what = ("branch set to {!r}".format(entry["branch"])
                if entry.get("branch") else "branch cleared")
    elif event == "discard":
        what = "work discarded, sent back to be tried again"
    elif event == "work":
        what = "picked up to be worked"
    elif event == "outcome":
        what = "outcome recorded"
    elif event == "delete":
        what = "deleted"
    else:
        what = str(event)
    # The agent and the model ride in ONE parenthetical at the end,
    # never in the sentence. Spelling the agent inline produced "picked
    # up to be worked by claude by amik", which is two actors in a line
    # that has one.
    detail = [d for d in (entry.get("agent"), entry.get("model")) if d]
    tail = " ({})".format(", ".join(detail)) if detail else ""
    return "{}  {}  {} by {}{}".format(
        entry.get("at") or "", card, what, who, tail)
