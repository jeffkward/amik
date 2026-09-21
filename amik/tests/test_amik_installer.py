"""The one-line installer, and the README that publishes it.

A curl-to-bash line is the one piece of documentation that cannot be
slightly wrong. Nobody reads it -- they paste it -- so a README naming a
path the repository does not serve is an error discovered by a stranger,
on their first contact with the tool, with nothing to compare against.

These tests are about the CONTRACT between the two files rather than
about running the script: what it promises to touch, what it refuses to
touch, and that both copies of the command say the same thing.
"""

import os
import re
import stat

from conftest import REPO

INSTALLER = os.path.join(REPO, "install.sh")
README = os.path.join(REPO, "README.md")


def _text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _curl_lines(text):
    return re.findall(r"curl -fsSL (\S+) \| bash", text)


# ── it is there and it runs ─────────────────────────────────────────

def test_the_installer_exists_and_is_executable():
    """`bash install.sh` is the documented manual path, but a file
    without its bit set is one somebody has to be told to work around."""
    assert os.path.isfile(INSTALLER)
    assert os.stat(INSTALLER).st_mode & stat.S_IXUSR


def test_it_is_a_bash_script_that_stops_on_the_first_failure():
    src = _text(INSTALLER)
    assert src.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in src


# ── the two copies of the command agree ─────────────────────────────

def test_the_readme_and_the_script_publish_the_SAME_url():
    """The script's own header documents the way in, and so does the
    README. Two copies of one string is a drift waiting to happen, and
    this is the cheapest place to catch it."""
    from_readme = set(_curl_lines(_text(README)))
    from_script = set(_curl_lines(_text(INSTALLER)))
    assert from_readme, "the README publishes no curl line"
    assert from_script, "the script's header documents no curl line"
    assert from_readme == from_script


def test_the_url_names_this_repository_and_a_raw_file():
    (url,) = set(_curl_lines(_text(README)))
    assert url.startswith("https://raw.githubusercontent.com/")
    assert url.endswith("/install.sh")
    assert "amik" in url


# ── what it promises not to do ──────────────────────────────────────

def test_it_creates_no_board():
    """A board belongs to a project, and the only directory an installer
    could guess is whichever one somebody happened to be standing in.
    `amik serve` writes one where that means something."""
    assert "board.jsonl" not in _text(INSTALLER)


def test_it_refuses_a_prefix_that_would_take_the_home_directory():
    """`rm -rf` is not in this script, but the prefix it is handed ends
    up in paths that get created and linked, and a stray environment
    variable naming `/` or `$HOME` is the one that cannot be undone."""
    src = _text(INSTALLER)
    assert 'case "$AMIK_HOME" in' in src
    assert '"$HOME"' in src
    assert "refusing to install into" in src


def test_it_never_clobbers_a_real_file_where_the_command_goes():
    """Only our own symlink, or a stale one, is replaced. A real
    `amik` somebody else put on their PATH is left alone and named."""
    src = _text(INSTALLER)
    assert "! -L" in src
    assert "leaving it alone" in src


# ── what it promises to do ──────────────────────────────────────────

def test_it_proves_the_python_by_importing_what_the_reader_needs():
    """A capability check, not a version string. `tomllib` is what the
    config reader imports, and it is the thing that actually has to
    work -- which is why `requires-python` says 3.11 at all."""
    assert "import tomllib" in _text(INSTALLER)


def test_it_links_the_console_script_the_packaging_declares():
    """`[project.scripts]` is what puts `amik` in the virtualenv's bin,
    and the symlink is what puts it on a PATH. If the name in either
    file changed alone, the installer would link something absent."""
    assert 'amik = "amik.__main__:main"' in _text(
        os.path.join(REPO, "pyproject.toml"))
    assert "/bin/amik" in _text(INSTALLER)


def test_every_env_override_it_documents_is_one_it_reads():
    """A header that lists a variable nothing consumes is worse than no
    header: it is a documented way to configure something that silently
    will not configure."""
    src = _text(INSTALLER)
    header = src.split("die()")[0]
    documented = set(re.findall(r"^#   (AMIK_[A-Z_]+)", header, re.M))
    assert documented, "the header documents no overrides"
    for name in documented:
        assert "${" + name + ":-" in src, f"{name} is documented, never read"


# ── the piped path, which is the one nobody tests ───────────────────

def test_it_does_not_resolve_its_own_path_through_DOLLAR_ZERO():
    """The trap that shipped, and the reason this file grew a section.

    Under `curl | bash`, `BASH_SOURCE[0]` is unset and `$0` is "bash",
    whose dirname is "." -- whichever directory the user happened to be
    standing in. The installer asks whether a `pyproject.toml` sits
    beside it to decide between a local clone and a fetch, so that
    fallback made it ask about the USER'S project: running the
    one-liner from inside any Python repository installed that
    repository, into a virtualenv named for us, behind a symlink to a
    command that did not exist.
    """
    src = _text(INSTALLER)
    assert "${BASH_SOURCE[0]:-$0}" not in src, "it is back to guessing from $0"
    assert 'SELF="${BASH_SOURCE[0]:-}"' in src
    # And the clone path must be gated on having found a real file.
    assert '[ -n "$SRC" ] && [ -f "$SRC/pyproject.toml" ]' in src


def test_the_body_is_a_function_called_on_the_LAST_line():
    """Piped, stdin IS the script and bash reads it as it runs. With the
    body inline, a child process that reads stdin swallows the rest and
    the install stops halfway with no error. As a function, bash has
    parsed the whole file before anything executes."""
    src = _text(INSTALLER).rstrip()
    assert "\nmain() {" in src
    assert src.endswith('main "$@"')


def test_nothing_in_it_can_sit_waiting_for_a_password():
    """A private or mistyped repository should fail with a message, not
    hang forever on a prompt the user cannot see being asked."""
    src = _text(INSTALLER)
    assert "GIT_TERMINAL_PROMPT=0" in src
    assert src.count("</dev/null") >= 2, "a child can still read stdin"


def test_a_RE_RUN_actually_refetches_rather_than_reporting_success():
    """`--upgrade` compares version numbers, and a project installed
    from a branch keeps the same one between releases -- so pip skips
    the fetch and says "already satisfied", and the script reports a
    successful install having done nothing.

    Measured, not reasoned about: a venv re-installed several times over
    a day still recorded the first commit it ever saw."""
    src = _text(INSTALLER)
    assert "--force-reinstall" in src
    assert "--upgrade" in src
