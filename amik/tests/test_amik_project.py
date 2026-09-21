"""What a project declares about being agent-worked.

A project that has not said how it is verified cannot be worked by an
agent, and the honest answer is a refusal rather than a guessed test
command — guessing one is how a loop reports green on nothing.
"""
import os

from amik.core import board as readers


def _toml(root, text):
    path = os.path.join(str(root), "amik", "amik.toml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


FULL = '''verify = "pytest -q"
laws = "CLAUDE.md"
branch = "card/"
armed = false
'''


def test_it_reads_what_the_project_declares(instance):
    _toml(instance, FULL)
    res = readers.amik_project(str(instance))
    assert res["ok"] is True
    assert res["data"]["verify"] == "pytest -q"
    assert res["data"]["laws"] == "CLAUDE.md"
    assert res["data"]["branch"] == "card/"


def test_a_project_with_no_file_is_refused(instance):
    res = readers.amik_project(str(instance))
    assert res["ok"] is False
    assert "amik.toml" in res["reason"]


def test_a_project_that_declares_no_verify_is_refused(instance):
    """The one declaration with no default. A project that has not said
    what green means here cannot be agent-worked, and saying so is the
    honest failure."""
    _toml(instance, 'laws = "CLAUDE.md"\n')
    res = readers.amik_project(str(instance))
    assert res["ok"] is False
    assert "verify" in res["reason"]


def test_an_empty_verify_is_the_same_as_none(instance):
    _toml(instance, 'verify = "   "\n')
    assert readers.amik_project(str(instance))["ok"] is False


def test_unparseable_toml_is_a_refusal_not_a_raise(instance):
    """Readers contract never to raise, and this file is hand-written."""
    _toml(instance, "verify = = =\n")
    res = readers.amik_project(str(instance))
    assert res["ok"] is False
    assert "unreadable" in res["reason"]


def test_armed_is_false_when_absent(instance):
    """A gate that opens by omission is not a gate."""
    _toml(instance, 'verify = "pytest -q"\n')
    assert readers.amik_project(str(instance))["data"]["armed"] is False


def test_only_a_real_boolean_arms_it(instance):
    """A config typo is exactly how a gate like this gets opened by
    accident, so a truthy string is not consent."""
    for value in ('"true"', '"yes"', '1', '["true"]'):
        _toml(instance, 'verify = "pytest -q"\narmed = ' + value + "\n")
        res = readers.amik_project(str(instance))
        assert res["data"]["armed"] is False, value


def test_a_real_boolean_true_does_arm_it(instance):
    _toml(instance, 'verify = "pytest -q"\narmed = true\n')
    assert readers.amik_project(str(instance))["data"]["armed"] is True


def test_assets_default_to_empty_when_undeclared(instance):
    _toml(instance, 'verify = "pytest -q"\n')
    assert readers.amik_project(str(instance))["data"]["assets"] == []


def test_declared_assets_are_read(instance):
    _toml(instance, 'verify = "pytest -q"\n\n[prototypes]\n'
                    'assets = ["/static/themes.css", "/static/app.css"]\n')
    res = readers.amik_project(str(instance))
    assert res["data"]["assets"] == ["/static/themes.css",
                                     "/static/app.css"]


def test_an_asset_that_is_not_root_relative_is_dropped(instance):
    """This list is injected verbatim as an href, so anything that is not
    a root-relative path is dropped here rather than trusted by every
    caller — a second consumer of this reader must not have to
    re-invent the same filter."""
    _toml(instance, 'verify = "pytest -q"\n\n[prototypes]\nassets = ['
                    '"javascript:alert(1)", "http://evil.example/x.css", '
                    '"/static/app.css", 7]\n')
    res = readers.amik_project(str(instance))
    assert res["data"]["assets"] == ["/static/app.css"]


def test_the_live_project_declares_itself_explicitly():
    """This repo's own declaration, read through the same door.

    It asserts the declaration is EXPLICIT, not what it says. Absent and
    false are the same value to the reader and a different thing to a
    person: an absent `armed` line is a gate nobody knows exists, so the
    file must actually carry one. Checking the reader's output alone
    would pass either way and miss the omission.

    It deliberately does NOT pin the value. Arming is the owner's edit
    and a test that failed when they made it would be a test arguing
    with the person it serves — and the one thing it must never do is
    make disarming feel like fighting the suite.

    The same goes for the agent: a project that has armed itself must
    """
    from conftest import INSTANCE, PACKAGE
    import re

    path = os.path.join(PACKAGE, "amik.toml")
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    assert re.search(r"(?m)^\s*armed\s*=", raw), \
        "amik.toml has no armed declaration — the gate exists but is undocumented"

    res = readers.amik_project(INSTANCE)
    assert res["ok"] is True, res
    assert "pytest" in res["data"]["verify"]
    assert res["data"]["laws"], "amik.toml names no laws file"
    assert os.path.isfile(os.path.join(INSTANCE,
                                       res["data"]["laws"])), \
        "laws names a file that is not there — the prompt would\n         carry no rules and say nothing about it"
    assert isinstance(res["data"]["armed"], bool)
    # Armed with NO agent is not a contradiction and is the shipped
    # default. `verify` and the agent command both refuse until they are
    # declared, so nothing can run before someone has said what works
    # their cards -- which makes `armed` the kill switch rather than the
    # gate, and a false there a step that looks like the obstacle and is
    # not. This used to assert the pair and would now fail every fresh
    # install.
