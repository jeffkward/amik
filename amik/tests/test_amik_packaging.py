"""Amik is installable, and installing it puts `amik` on the PATH.

Without this there is no `pip install`, no one-line installer, and the
command exists only as `python3 -m amik` typed from the right directory
-- which is the parked "getting amik onto a PATH" problem, answered
here as a side effect of packaging rather than as a shell alias
somebody has to remember.
"""

import os
import tomllib

# The REPOSITORY, not the package: LICENSE and pyproject sit
# beside `amik/`, not inside it.
from conftest import PACKAGE, REPO as HERE


def _cfg():
    with open(os.path.join(HERE, "pyproject.toml"), "rb") as f:
        return tomllib.load(f)


def test_there_is_a_real_licence():
    """A stub is refused on purpose: an empty LICENSE is worse than
    none, because it looks answered."""
    path = os.path.join(HERE, "LICENSE")
    assert os.path.isfile(path)
    text = open(path).read()
    assert len(text) > 500
    assert "MIT" in text


def test_the_project_declares_itself():
    p = _cfg()["project"]
    assert p["name"] == "amik"
    assert p["version"]
    assert p["license"]
    assert p["authors"]


def test_it_requires_the_python_that_has_tomllib():
    """`tomllib` is stdlib from 3.11 and the reader imports it.
    Declaring less installs cleanly and fails on the first config
    read."""
    assert _cfg()["project"]["requires-python"] == ">=3.11"


def test_jinja_is_the_ONLY_dependency():
    """The engine is stdlib and another test pins that. This pins the
    other half -- nothing creeps into the install either."""
    deps = _cfg()["project"]["dependencies"]
    assert len(deps) == 1, deps
    assert deps[0].lower().startswith("jinja2")


def test_installing_it_gives_you_an_amik_command():
    assert _cfg()["project"]["scripts"]["amik"] == "amik.__main__:main"


def test_the_wheel_carries_the_templates_and_the_static_files():
    """They are DATA, not modules, so nothing includes them
    automatically. A wheel without them installs cleanly and fails at
    the first request with a TemplateNotFound."""
    data = _cfg()["tool"]["setuptools"]["package-data"]["amik"]
    joined = " ".join(data)
    assert "app/templates" in joined
    assert "app/static" in joined


def test_every_template_and_static_file_is_MATCHED_by_a_pattern():
    """The patterns are a list, and a list is a thing something falls
    off. An `.html` added under a new subdirectory, or a static file
    with an unlisted extension, ships missing and says nothing."""
    import fnmatch
    patterns = _cfg()["tool"]["setuptools"]["package-data"]["amik"]
    # Patterns come from the REPOSITORY's pyproject; the files they have
    # to match live in the PACKAGE. Reading both from one root is how a
    # test like this passes while shipping nothing.
    for sub in ("app/templates", "app/static"):
        base = os.path.join(PACKAGE, sub)
        for name in os.listdir(base):
            if name.startswith(".") or name == "__pycache__":
                continue
            rel = sub + "/" + name
            assert any(fnmatch.fnmatch(rel, p) for p in patterns), rel


def test_status_says_WHY_a_fresh_board_cannot_be_worked(tmp_path, capsys):
    """`armed: false` on a board whose config says true is the first
    thing a new user sees and the easiest thing to misread. The real
    cause is an undeclared verify command, and status now names it."""
    import json
    from amik.__main__ import main
    from amik.core import init
    init.init(str(tmp_path))
    assert main(["--root", str(tmp_path), "status"]) == 0
    said = json.loads(capsys.readouterr().out)
    assert said["ready_to_work"] is False
    assert "verify" in said["why_not"]


def test_every_skill_the_laws_POINT_AT_is_actually_there():
    """CLAUDE.md and the README name skills by path. A pointer to a file
    that is not there is worse than no pointer: an agent follows it,
    finds nothing, and carries on without the thing it was sent for."""
    import re
    from conftest import REPO
    named = set()
    for name in ("CLAUDE.md", "README.md"):
        text = open(os.path.join(REPO, name), encoding="utf-8").read()
        named |= set(re.findall(r"\.claude/skills/[a-z0-9-]+/SKILL\.md", text))
    assert named, "nothing names a skill any more"
    for rel in sorted(named):
        assert os.path.isfile(os.path.join(REPO, rel)), rel


def test_a_shipped_skill_declares_itself_properly():
    """Frontmatter with a name and a description, or the harness will
    not list it and nobody will ever see it."""
    import glob
    from conftest import REPO
    for path in glob.glob(os.path.join(REPO, ".claude", "skills", "*",
                                       "SKILL.md")):
        head = open(path, encoding="utf-8").read().split("---")[1]
        assert "name:" in head, path
        assert "description:" in head, path
