"""The loop without a scheduler.

A timer that watches a file. The TICK is time-based; the WORK is
change-based -- so a quiet board costs one stat an interval and nothing
else: no spawn, no read, no agent.

This is the only thing that works a board now, which makes the failure
that matters "it stopped, and nothing said so".
"""

import os
import threading

import pytest

from amik import loop
from amik.core import board
from tests.test_loop import ROWS, _toml


@pytest.fixture()
def ticking(instance):
    from conftest import write_board
    write_board(instance, ROWS)
    with open(os.path.join(instance, "LAWS.md"), "w") as f:
        f.write("# Laws\n")
    _toml(instance, armed=True, agent="true")
    return instance


# ── when it looks ───────────────────────────────────────────────────

def test_the_FIRST_tick_looks_without_the_board_moving(ticking, monkeypatch):
    """A fresh process has nothing to compare against. A server started
    with a card already in Ready that sat there until somebody touched
    the file would look broken."""
    seen = []
    monkeypatch.setattr(loop, "work",
                        lambda root, **kw: seen.append(kw) or {"did": []})
    loop.tick_forever(ticking, sleep=0, rounds=1)
    assert seen, "the first tick did not look"
    assert seen[0].get("if_changed") is False


def test_LATER_ticks_only_work_when_the_board_moved(ticking, monkeypatch):
    seen = []
    monkeypatch.setattr(loop, "work",
                        lambda root, **kw: seen.append(kw) or {"did": []})
    loop.tick_forever(ticking, sleep=0, rounds=3)
    assert [s.get("if_changed") for s in seen] == [False, True, True]


# ── when it goes wrong ──────────────────────────────────────────────

def test_one_bad_tick_does_NOT_end_the_thread(ticking, monkeypatch):
    """A board that stopped working because one card threw would be
    silent: the server keeps answering and nothing is ever worked
    again. This is the one exception that must not be fatal."""
    calls = []

    def boom(root, **kw):
        calls.append(1)
        raise RuntimeError("the card exploded")

    monkeypatch.setattr(loop, "work", boom)
    loop.tick_forever(ticking, sleep=0, rounds=3)
    assert len(calls) == 3, "it stopped after the first failure"


def test_a_bad_tick_is_REPORTED_not_swallowed(ticking, monkeypatch, capsys):
    """Surviving is not the same as hiding. Something has to say so, or
    a board works nothing forever and looks healthy -- and there is no
    `launchctl list` to ask any more."""
    monkeypatch.setattr(loop, "work",
                        lambda root, **kw: (_ for _ in ()).throw(
                            RuntimeError("the card exploded")))
    loop.tick_forever(ticking, sleep=0, rounds=1)
    assert "exploded" in capsys.readouterr().err


# ── when it stops ───────────────────────────────────────────────────

def test_a_set_stop_returns_at_once(ticking, monkeypatch):
    monkeypatch.setattr(loop, "work", lambda root, **kw: {"did": []})
    stop = threading.Event()
    stop.set()
    seen = []
    monkeypatch.setattr(loop, "work",
                        lambda root, **kw: seen.append(kw) or {"did": []})
    loop.tick_forever(ticking, sleep=0, stop=stop)
    assert seen == [], "it worked a card after being told to stop"


def test_stopping_mid_sleep_does_not_wait_out_the_interval(ticking,
                                                           monkeypatch):
    """`stop.wait(seconds)` rather than `time.sleep` -- a server being
    shut down should not hang for the tick."""
    import inspect
    src = inspect.getsource(loop.tick_forever)
    assert "wait(" in src
    assert "time.sleep" not in src


# ── the gates are still the loop's ──────────────────────────────────

def test_an_unarmed_board_ticks_and_works_nothing(ticking):
    """The gate belongs to `work`, not the ticker: one place decides,
    and it is the same place the command line goes through."""
    _toml(ticking, agent="true")                    # armed absent
    loop.tick_forever(ticking, sleep=0, rounds=2)   # no agent spawns
    rows = open(os.path.join(ticking, "amik", "board.jsonl")).read()
    assert '"status": "ready"' in rows, "it worked a card on an unarmed board"


def test_it_takes_its_interval_from_the_project(ticking):
    """Declarable, because the right number differs by machine."""
    assert board.amik_project(ticking)["data"]["tick"] == 1.0
