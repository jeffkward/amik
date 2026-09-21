"""The board's change feed.

Nothing notifies this module. It compares snapshots, which is what lets
one mechanism catch the loop, a second tab, a hand edit, `git checkout`
and a restore from backup alike -- and makes a writer that forgets to
announce itself impossible to write.

Stdlib only, like everything under `amik/core`. This renders nothing;
the client fetches what it needs once it has been told something moved.
"""
import hashlib
import json
import os
import time

from ..core import board


# The card fields a tile or a modal can show. A change to any of them is
# a change the page has to hear about; a change to anything else is not,
# and including it would wake every open page for a field nobody renders.
_WATCHED = ("title", "status", "rank", "planning", "group", "halt",
            "branch_requested", "requires_prototype", "branch",
            "updated_at")


def _digest(card, prose):
    parts = [str(card.get(key) or "") for key in _WATCHED]
    parts.append(prose)
    return hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest()


def mtimes(root):
    """A cheap fingerprint of the whole instance: `board.jsonl`, the
    `cards/` directory, and the newest file in it.

    This is what the poll actually compares. `snapshot` reads every card
    file, which is fine once but not once a second per connected client;
    this is three `stat` calls and it moves whenever anything under
    `amik/` that matters does. The directory's own mtime catches an added
    or deleted card; the newest child catches an edited one.
    """
    base = os.path.join(root, "amik")
    cards = os.path.join(base, "cards")
    out = []
    for path in (os.path.join(base, "board.jsonl"), cards):
        try:
            out.append(str(os.stat(path).st_mtime_ns))
        except OSError:
            out.append("")
    try:
        newest = max((os.stat(os.path.join(cards, name)).st_mtime_ns
                      for name in os.listdir(cards)), default=0)
    except OSError:
        newest = 0
    out.append(str(newest))
    return "/".join(out)


def snapshot(root):
    """What the board looks like right now: its fingerprint, and a digest
    per card covering the rendered fields AND the card's prose.

    The prose is in the digest because `amik_fingerprint` deliberately is
    not: it identifies `board.jsonl` alone, which is right for a stale
    check and wrong here.
    """
    out = {"fingerprint": board.amik_fingerprint(root), "cards": {}}
    data = board.amik(root)
    if not data["ok"]:
        return out
    for column in data["data"]["columns"]:
        for card in column["cards"]:
            card_id = card.get("id")
            if not card_id:
                continue
            out["cards"][card_id] = _digest(card, card.get("body") or "")
    return out


def changed(before, after):
    """Ids added, removed or altered between two snapshots, sorted.

    Sorted because a set's order is not stable across runs and a test
    that compares one is a test that fails on a Tuesday.
    """
    old, new = before["cards"], after["cards"]
    moved = {i for i in old if old[i] != new.get(i)}
    moved |= {i for i in new if i not in old}
    return sorted(moved)


def frame(payload):
    """One SSE frame. The blank line is the terminator, not decoration --
    without it the client holds the event forever waiting for more."""
    return b"data: " + json.dumps(payload).encode("utf-8") + b"\n\n"


def stream(root, sleep=1.0, limit=None):
    """The feed.

    The FIRST frame carries the current fingerprint and an empty change
    list: a client that has just connected -- or reconnected after a
    laptop woke up, which EventSource does silently and on its own --
    knows nothing, so it is handed the state rather than a diff against
    one it may never have held.

    `limit` bounds the number of polls so a test can drain it. Left None
    it runs until the client goes away, which arrives as a write error on
    the socket and ends the generator.
    """
    state = snapshot(root)
    seen = mtimes(root)
    yield frame({"fingerprint": state["fingerprint"], "changed": []})
    polls = 0
    while limit is None or polls < limit:
        polls += 1
        if sleep:
            time.sleep(sleep)
        # The cheap check first. A quiet board costs three stat calls a
        # second, not a read of every card file a second per connected
        # client.
        fresh_mtimes = mtimes(root)
        if fresh_mtimes == seen:
            yield b": tick\n\n"
            continue
        seen = fresh_mtimes
        fresh = snapshot(root)
        moved = changed(state, fresh)
        if moved or fresh["fingerprint"] != state["fingerprint"]:
            state = fresh
            yield frame({"fingerprint": state["fingerprint"],
                         "changed": moved})
        else:
            # The files moved but nothing a page renders did -- a
            # `git checkout` that restored identical bytes, say. A
            # comment frame, which is also how a dead connection is
            # discovered: without traffic, a half-open socket looks
            # exactly like a quiet board.
            yield b": tick\n\n"
