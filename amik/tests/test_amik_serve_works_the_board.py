"""Serving and working are one process now.

The banner is the only thing that will say whether a board is being
worked. There is no `launchctl list` to ask any more, so a server that
is silently not going to work anything has to say so at the moment it
starts -- not when somebody wonders why nothing happened.
"""

import inspect
import os
import socket

from amik.app import server


def _write(root, text):
    with open(os.path.join(root, "amik", "amik.toml"), "w") as f:
        f.write(text)


# ── the thread ──────────────────────────────────────────────────────

def test_serve_starts_the_ticker_on_a_DAEMON_thread():
    """A card's verify runs for minutes. On a request thread that is a
    board which stops answering; on a non-daemon thread it is a server
    that will not exit."""
    src = inspect.getsource(server.serve)
    assert "tick_forever" in src
    assert "daemon=True" in src


# ── two boards ──────────────────────────────────────────────────────

def test_a_bound_port_refuses_with_the_flag_that_fixes_it(project, capsys):
    """Two boards is the normal case now, and the second one meets this
    immediately. A traceback here teaches nothing."""
    _write(project, 'verify = "true"\n')
    held = socket.socket()
    held.bind(("127.0.0.1", 0))
    held.listen(1)
    port = held.getsockname()[1]
    try:
        ok = server.serve(project, port=port, loop=False, forever=False)
        assert ok is False
        # ONE read: capsys drains, so a second call returns empty
        # and an assertion on it passes or fails for the wrong reason.
        captured = capsys.readouterr()
        said = captured.out + captured.err
        assert "--port" in said, said
    finally:
        held.close()


def test_a_free_port_binds_and_reports_it(project, capsys):
    _write(project, 'verify = "true"\n')
    assert server.serve(project, port=0, loop=False, forever=False) is not False


def test_the_banner_is_FLUSHED():
    """stdout is block-buffered when it is not a terminal, and a server
    that runs forever never fills the buffer -- so the banner never
    appears in a log. Which is the case it exists for: a board started
    as a daemon, where the log is the only way to know whether it will
    work cards.

    Measured before it was fixed: two seconds into a redirected run the
    log was empty, and it was still empty after the process was killed.
    """
    src = inspect.getsource(server.serve)
    assert "flush=True" in src
