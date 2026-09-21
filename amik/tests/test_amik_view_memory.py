"""The board remembers how you were looking at it.

Which columns are shut and how far across the board is scrolled are the
two things the owner re-did on every single visit. Both are VIEW, not
data: they belong to the person looking, so they live in that browser's
localStorage and never in `board.jsonl`, which travels through git to
every other reader.

What is pinned here is the part that is easy to get subtly wrong: only
your own click is written down. A snapshot of every column would freeze
today's defaults forever — a column added tomorrow would arrive in
whatever state the snapshot happened to record for it, or worse, in the
state of a column that no longer exists.
"""
import os

FACE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "app")
STATIC = os.path.join(FACE, "static")


def _js(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


def _block(src, marker, nxt):
    """One section of amik.js, cut at its banner comments."""
    start = src.index(marker)
    return src[start:src.index(nxt, start)]


def test_the_store_is_namespaced_by_where_amik_is_mounted():
    """The same origin serves a standalone board and one embedded under
    /amik. One reader's shut columns are not the other's."""
    src = _js("amik.js")
    assert "'amik:' + window.akBase() + ':' + name" in src


def test_both_ends_of_the_store_survive_a_browser_that_refuses_it():
    """localStorage THROWS on the READ — not returning null, throwing —
    in a browser with site data turned off. This runs at file scope, so
    an uncaught exception would take every listener below it with it."""
    view = _block(_js("amik.js"), "window.akView = (function () {",
                  "/* ── collapsing")
    assert view.count("try {") == 2
    assert view.count("catch (e)") == 2
    # the read has to answer the fallback, not undefined
    assert "return fallback;" in view


def test_a_toggle_is_written_down_under_its_column_status():
    collapsing = _block(_js("amik.js"), "/* ── collapsing",
                        "/* ── how far across you were")
    assert "col.dataset.status" in collapsing
    assert "shut[status] = now;" in collapsing
    assert "window.akView.write('columns', shut);" in collapsing


def test_a_column_never_clicked_keeps_the_server_default():
    """The stored map holds one entry per toggle, so the restore has to
    ask whether this column is IN it — not read a falsy value out of it.
    `if (shut[status])` would silently open every column the owner has
    never touched, which is how Done, Someday and Won't Do would arrive
    expanded on a browser that had stored anything at all."""
    collapsing = _block(_js("amik.js"), "/* ── collapsing",
                        "/* ── how far across you were")
    assert "hasOwnProperty.call(shut, status)" in collapsing
    assert "classList.toggle('akcollapsed', !!shut[status])" in collapsing


def test_a_stored_value_that_is_not_a_map_is_ignored():
    """Hand-edited or written by an older shape. `shut[status] = now` on
    a string would throw in strict mode and be silently lost otherwise."""
    collapsing = _block(_js("amik.js"), "/* ── collapsing",
                        "/* ── how far across you were")
    assert "typeof shut !== 'object'" in collapsing


def test_the_drag_opening_a_column_is_not_a_decision():
    """A shut column opens itself to accept a drop and shuts again on
    dragend. That is the drag's business and nothing the owner asked
    for, so no part of the drag may reach the store."""
    drag = _block(_js("amik.js"), "/* ── drag to reorder",
                  "/* ── the play/pause toggle")
    assert "akView" not in drag


def test_the_scroll_offset_is_restored_after_the_columns():
    """A shut column is 130px narrower than an open one, so restoring
    the offset before the collapse state lands it somewhere else."""
    src = _js("amik.js")
    assert src.index("/* ── collapsing") < src.index("/* ── how far across")


def test_the_scroll_write_is_coalesced():
    """A scroll fires once a frame. Serialising on each one would be a
    write per frame for the length of a flick."""
    scroll = _block(_js("amik.js"), "/* ── how far across you were",
                    "/* ── drag to reorder")
    assert "if (timer) return;" in scroll
    assert "setTimeout(" in scroll
    assert "window.akView.write('scroll'" in scroll


def test_the_scroll_offset_is_read_as_a_number():
    scroll = _block(_js("amik.js"), "/* ── how far across you were",
                    "/* ── drag to reorder")
    assert "window.akView.read('scroll', 0)" in scroll
    assert "typeof at === 'number'" in scroll
