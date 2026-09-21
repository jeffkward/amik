"""The change feed.

No writer notifies anything. The server watches mtimes, which is what
catches the loop, a second tab, a hand edit, `git checkout` and a restore
from backup with one mechanism -- and makes a writer that forgets to
announce itself impossible.
"""

import json
import os

from amik.app import watch

READY = "rename-the-export-button"


def _write_prose(root, card_id, text):
    """Straight to the file, deliberately not through the door: an agent
    working this board holds Edit, and this is the write the feed has to
    notice anyway."""
    path = os.path.join(root, "amik", "cards", card_id + ".md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def test_a_snapshot_names_every_card(scenario):
    snap = watch.snapshot(scenario("ready_plain"))
    assert READY in snap["cards"]
    assert snap["fingerprint"]


def test_nothing_changed_is_an_empty_list(scenario):
    root = scenario("ready_plain")
    assert watch.changed(watch.snapshot(root), watch.snapshot(root)) == []


def test_a_moved_card_is_named(scenario):
    root = scenario("ready_plain")
    before = watch.snapshot(root)
    from amik.core import edit
    edit.move(root, READY, "doing", 0)
    assert watch.changed(before, watch.snapshot(root)) == [READY]


def test_a_deleted_card_is_named(scenario):
    root = scenario("ready_plain")
    before = watch.snapshot(root)
    from amik.core import edit
    edit.delete(root, READY)
    assert watch.changed(before, watch.snapshot(root)) == [READY]


def test_a_PROSE_only_change_is_named(scenario):
    """The fingerprint covers board.jsonl alone -- correct for a stale
    check, wrong for a change feed. A card's prose is its own file, and
    the agents that work this board hold Edit: one that writes
    amik/cards/<id>.md directly moves nothing board.jsonl can see.

    Without this the board would claim to be live and not see an answered
    question, which is worse than not claiming it."""
    root = scenario("ready_plain")
    before = watch.snapshot(root)
    _write_prose(root, READY, "A body written straight to the file.\n")
    assert watch.changed(before, watch.snapshot(root)) == [READY]


def test_a_field_no_page_renders_wakes_nobody(scenario):
    """The digest covers what a tile or a modal can SHOW. A row growing a
    key nothing draws must not wake every open page."""
    root = scenario("ready_plain")
    before = watch.snapshot(root)
    path = os.path.join(root, "amik", "board.jsonl")
    rows = [json.loads(line) for line in open(path) if line.strip()]
    rows[0]["raised_by"] = "agent"
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    assert watch.changed(before, watch.snapshot(root)) == []


def test_the_poll_is_cheap_when_nothing_moved(scenario):
    """`snapshot` reads every card file. Once is fine; once a second per
    connected client is not, so the poll compares three stat calls first
    and only digests when one of them moved."""
    root = scenario("ready_plain")
    assert watch.mtimes(root) == watch.mtimes(root)


def test_the_cheap_check_notices_a_prose_edit(scenario):
    """If it did not, the expensive check would never run and the feed
    would be silent about the very case it was widened to catch."""
    root = scenario("ready_plain")
    before = watch.mtimes(root)
    _write_prose(root, READY, "Edited straight on disk.\n")
    assert watch.mtimes(root) != before


def test_the_cheap_check_notices_a_new_card(scenario):
    """The cards/ directory's own mtime, which is what catches a file
    arriving rather than an existing one changing."""
    root = scenario("ready_plain")
    before = watch.mtimes(root)
    _write_prose(root, "a-brand-new-card", "Arrived.\n")
    assert watch.mtimes(root) != before


def test_a_frame_is_one_sse_data_line():
    frame = watch.frame({"fingerprint": "x", "changed": ["a"]})
    assert frame.startswith(b"data: ")
    assert frame.endswith(b"\n\n")
    assert json.loads(frame[len(b"data: "):].decode())["changed"] == ["a"]


def test_the_stream_opens_with_the_current_state(scenario):
    """A client that has just connected knows nothing, so the first frame
    is the state rather than a diff against one it never held."""
    root = scenario("ready_plain")
    frames = list(watch.stream(root, sleep=0, limit=1))
    first = json.loads(frames[0][len(b"data: "):].decode())
    assert first["fingerprint"]
    assert first["changed"] == []


def test_a_quiet_board_still_says_something(scenario):
    """Comment frames, not silence: without traffic a half-open socket
    looks exactly like a board nobody is touching."""
    root = scenario("ready_plain")
    frames = list(watch.stream(root, sleep=0, limit=3))
    assert frames[1:] == [b": tick\n\n"] * 3


def test_a_write_reaches_the_stream(scenario):
    """The whole point, end to end: something moved and the feed says
    which card."""
    root = scenario("ready_plain")
    feed = watch.stream(root, sleep=0)
    next(feed)                                   # the opening state
    from amik.core import edit
    edit.move(root, READY, "doing", 0)
    payload = json.loads(next(feed)[len(b"data: "):].decode())
    assert payload["changed"] == [READY]
    assert payload["fingerprint"]


def test_the_route_streams(scenario):
    from amik.app.handle import handle, ROUTES
    assert ("GET", "/events") in ROUTES
    status, headers, body = handle("GET", "/events", None, b"",
                                   root=scenario("ready_plain"), base="")
    assert status == 200
    assert headers["Content-Type"].startswith("text/event-stream")
    assert not isinstance(body, (bytes, bytearray)), "must be a stream"
    body.close()


def test_it_404s_on_an_instance_with_no_board(instance):
    from amik.app.handle import handle
    assert handle("GET", "/events", None, b"", root=instance, base="")[0] == 404
