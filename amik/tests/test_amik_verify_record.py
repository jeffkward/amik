"""The last verify Amik ran, remembered beside the board.

The pill on the bar reports a fact rather than a count. Counting tests
would mean recognising pytest from jest from cargo, which is the
framework knowledge this tool has refused to carry ever since `verify`
was given no default -- and it would read 0 on any project whose verify
is a compound command.

What Amik honestly knows is what its OWN verify run said. It runs one
when a card lands, so this is written there and nowhere else.

**It is machine-local and disposable**, like the lock and the seen
cursor: a result from another machine means nothing, and losing it costs
one pill reading "not run yet" until the next card lands.
"""

import json
import os

from amik import loop


def _path(root):
    return os.path.join(root, "amik", ".verify")


def test_a_verify_run_leaves_a_record(empty_board):
    ok, _ = loop._verify(empty_board, "true")
    assert ok
    rec = json.load(open(_path(empty_board)))
    assert rec["ok"] is True
    assert rec["command"] == "true"
    assert rec["at"]


def test_a_FAILED_verify_is_recorded_as_failed(empty_board):
    ok, _ = loop._verify(empty_board, "false")
    assert not ok
    rec = json.load(open(_path(empty_board)))
    assert rec["ok"] is False


def test_the_second_run_REPLACES_the_first(empty_board):
    """A cursor, not a log. An outcome appends because a card worked
    twice has two outcomes; this answers "how is the tree right now",
    which has one answer."""
    loop._verify(empty_board, "false")
    loop._verify(empty_board, "true")
    assert json.load(open(_path(empty_board)))["ok"] is True


def test_recording_never_fails_the_verify(empty_board):
    """Verify's answer is the thing that gates a merge. A bookkeeping
    write that could not happen must not turn a green tree red.

    The write is made to fail for real rather than by replacing the
    writer with a bomb: a directory sitting where the file goes is the
    shape a stale checkout or a stray `mkdir` actually leaves behind,
    and patching the function would only prove a wrapper exists."""
    os.makedirs(_path(empty_board))
    ok, _ = loop._verify(empty_board, "true")
    assert ok is True
    assert os.path.isdir(_path(empty_board)), "it removed what was there"


def test_the_reader_gives_back_what_was_written(empty_board):
    from amik.core import board
    loop._verify(empty_board, "true")
    rec = board.amik_verify(empty_board)
    assert rec["ok"] is True
    assert rec["command"] == "true"


def test_no_record_reads_as_NOT_RUN_rather_than_as_a_failure(empty_board):
    """A board that has never landed a card has never run verify here.
    That is not a red tree and must not render as one."""
    from amik.core import board
    rec = board.amik_verify(empty_board)
    assert rec["ok"] is None
    assert rec["at"] == ""


def test_a_CORRUPT_record_reads_as_not_run_and_does_not_raise(empty_board):
    """It is a file on disk that nothing validates. A page that 500s
    because a cursor got truncated is a board lost to a cache file."""
    from amik.core import board
    os.makedirs(os.path.join(empty_board, "amik"), exist_ok=True)
    with open(_path(empty_board), "w") as f:
        f.write("{not json")
    assert board.amik_verify(empty_board)["ok"] is None

