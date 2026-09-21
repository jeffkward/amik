"""The top bar: the mark, the host's name, and the gate on the loop.

Three things, and only one of them writes. `armed` is the one key a UI
may set in `amik.toml`, and setting it is a SURGICAL line edit to a
hand-written, comment-heavy file — so most of what is here is about the
bytes that must not move.

The name is the opposite: read-only, optional, and empty when undeclared.
Amik will not invent one from a directory, because a guessed name in the
top bar reads exactly like a name someone chose.
"""
import os

from amik.app.handle import handle
from amik.core import board as readers
from amik.core import config

LIVE = '''# a comment that must survive
name = "Ledger"
verify = "pytest -q"
armed = false

[loop]
ceiling = 3
'''


def _toml(root, text):
    path = os.path.join(str(root), "amik", "amik.toml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _read(root):
    with open(os.path.join(str(root), "amik", "amik.toml"),
              encoding="utf-8") as f:
        return f.read()


def _page(root):
    status, _, body = handle("GET", "/", root=str(root))
    assert status == 200
    return body.decode()


# ── the host's name ─────────────────────────────────────────────────────

def test_the_project_name_is_read(instance):
    _toml(instance, LIVE)
    assert readers.amik_project(str(instance))["data"]["name"] == "Ledger"


def test_an_undeclared_name_is_empty_not_guessed(instance):
    """The fallback is NO name, never the directory's. A guessed name in
    the top bar is indistinguishable from a configured one."""
    _toml(instance, 'verify = "pytest -q"\n')
    assert readers.amik_project(str(instance))["data"]["name"] == ""


def test_a_name_that_is_not_a_string_is_empty(instance):
    _toml(instance, 'verify = "pytest -q"\nname = 7\n')
    assert readers.amik_project(str(instance))["data"]["name"] == ""


# ── the pure edit ───────────────────────────────────────────────────────

def test_arming_changes_one_line_and_nothing_else(instance):
    after = config.arm(LIVE, True)
    assert after == LIVE.replace("armed = false", "armed = true")


def test_disarming_is_the_same_edit_the_other_way(instance):
    assert config.arm(config.arm(LIVE, True), False) == LIVE


def test_a_trailing_comment_on_the_line_survives(instance):
    """The comment beside this key is the paragraph explaining what the
    gate does. A writer that ate it would be teaching the next reader
    nothing about the line they are looking at."""
    text = 'verify = "x"\narmed = false  # only a deliberate edit\n'
    assert config.arm(text, True) == (
        'verify = "x"\narmed = true  # only a deliberate edit\n')


def test_a_typo_value_is_replaced_by_a_real_boolean(instance):
    """`armed = "true"` is a config typo the reader refuses to honour.
    The writer replaces it outright rather than leaving two spellings of
    one gate in the file."""
    assert 'armed = false\n' in config.arm('verify = "x"\narmed = "true"\n',
                                           False)


def test_an_absent_key_lands_above_the_first_table(instance):
    """The trap this whole function exists for: a key appended to the END
    of the file sits below a `[table]` header and belongs to that table.
    `[loop].armed` reads exactly like consent and the reader never looks
    at it."""
    text = 'verify = "x"\n\n[loop]\nceiling = 3\n'
    after = config.arm(text, True)
    assert after.index("armed = true") < after.index("[loop]")


def test_an_absent_key_on_a_file_with_no_tables_still_lands(instance):
    after = config.arm('verify = "x"\n', True)
    assert "armed = true" in after


def test_a_key_inside_a_table_is_not_the_one_that_gets_written(instance):
    """Only the TOP-LEVEL `armed` is the gate. A key of that name under a
    table is a different key, and writing to it would move nothing."""
    text = 'verify = "x"\n\n[loop]\narmed = false\n'
    after = config.arm(text, True)
    assert after.index("armed = true") < after.index("[loop]")
    assert "armed = false" in after.split("[loop]", 1)[1]


# ── the write, end to end ───────────────────────────────────────────────

def test_a_write_lands_and_reads_back(instance):
    _toml(instance, LIVE)
    assert config.set_armed(str(instance), True)["ok"] is True
    assert readers.amik_project(str(instance))["data"]["armed"] is True
    assert config.set_armed(str(instance), False)["ok"] is True
    assert readers.amik_project(str(instance))["data"]["armed"] is False


def test_an_instance_with_no_declaration_is_refused(instance):
    res = config.set_armed(str(instance), True)
    assert res["ok"] is False
    assert "amik.toml" in res["reason"]


def test_a_write_that_does_not_read_back_is_rolled_back(instance):
    """A line-matching editor can be fooled: `armed = true` written inside
    a multi-line string looks like the key and is not. The read-back is
    what catches it — and the file goes back the way it was, because this
    is the file carrying `verify` and a board whose declaration stopped
    meaning what it said is a board no agent can work.
    """
    text = 'verify = """\narmed = true\n"""\n'
    _toml(instance, text)
    res = config.set_armed(str(instance), False)
    assert res["ok"] is False
    assert "read back" in res["reason"]
    assert _read(instance) == text


# ── the route ───────────────────────────────────────────────────────────

def test_the_route_arms_the_project(client, instance):
    from conftest import write_board
    write_board(str(instance), [])
    _toml(instance, LIVE)
    res = client.patch("/amik/project", {"armed": "true"})
    assert res.status_code == 200
    assert res.json()["armed"] is True
    assert readers.amik_project(str(instance))["data"]["armed"] is True


def test_the_route_refuses_anything_that_is_not_a_boolean(client, instance):
    """A gate a typo can open is not a gate, and the door is where a typo
    arrives. Nothing is written."""
    from conftest import write_board
    write_board(str(instance), [])
    _toml(instance, LIVE)
    for value in ("yes", "1", "", "True"):
        assert client.patch("/amik/project",
                            {"armed": value}).status_code == 400
    assert _read(instance) == LIVE


def test_the_route_404s_where_there_is_no_project(client, instance):
    """Gated on the PROJECT, not the board: `armed` lives in amik.toml,
    and an instance that declares nothing has no gate to move."""
    from conftest import write_board
    write_board(str(instance), [])
    assert client.patch("/amik/project",
                        {"armed": "true"}).status_code == 404


def test_a_pause_reports_the_work_already_under_way(client, scenario):
    """What the owner has to be told: a card the loop has started runs to
    the end. The count comes from a fresh read of `doing`, so a card that
    entered it since the page loaded is still counted."""
    root = scenario("doing_plain")
    _toml(root, LIVE)
    res = client.patch("/amik/project", {"armed": "false"})
    assert res.status_code == 200
    assert res.json() == {"armed": False, "working": 1}


def test_a_pause_on_an_idle_board_reports_nothing_running(client, scenario):
    root = scenario("ready_plain")
    _toml(root, LIVE)
    assert client.patch("/amik/project",
                        {"armed": "false"}).json()["working"] == 0


def test_the_host_name_shows_when_it_is_declared(scenario):
    root = scenario("ready_plain")
    _toml(root, LIVE)
    assert "Ledger" in _page(root)


def test_the_bar_names_nothing_when_the_project_does_not(scenario):
    root = scenario("ready_plain")
    _toml(root, 'verify = "pytest -q"\n')
    page = _page(root)
    assert 'class="akhost"' in page
    assert ">Ledger<" not in page


def test_the_toggle_carries_the_state_it_found(scenario):
    root = scenario("ready_plain")
    _toml(root, LIVE)
    assert 'data-armed="false"' in _page(root)
    config.set_armed(root, True)
    assert 'data-armed="true"' in _page(root)


def test_the_toggle_is_labelled_before_any_script_runs(scenario):
    """Both wordings ride as data attributes and the CURRENT one is
    rendered — so the button is correctly named with JavaScript off, and
    the script has no second copy of the sentences to drift from."""
    root = scenario("ready_plain")
    _toml(root, LIVE)
    page = _page(root)
    assert 'aria-label="Arm the queue"' in page
    assert "data-armed-tip=" in page and "data-paused-tip=" in page
    config.set_armed(root, True)
    assert 'aria-label="Pause the queue"' in _page(root)


def test_there_is_no_toggle_where_there_is_no_gate(scenario):
    """An instance that declares no project has nothing to arm, so the
    control is absent rather than present and inert. The name's cell
    stays — it is a grid column, and an empty one holds the mark and the
    gate where they were rather than letting them slide."""
    page = _page(scenario("ready_plain"))
    assert "akarmbtn" not in page
    assert '<span class="akhost"></span>' in page
