#!/usr/bin/env bash
set -euo pipefail

# amik installer — give a repository a board an agent can work.
#
# Two ways in:
#   curl -fsSL https://raw.githubusercontent.com/jeffkward/amik/main/install.sh | bash
#     (nothing to answer; installs the command and tells you where to run it)
#   bash install.sh                           # from a local clone, installs that clone
#
# Everything it touches, in order (idempotent — re-running upgrades in
# place rather than stacking a second copy):
#   1. checks python3 >= 3.11 by IMPORTING tomllib rather than parsing a
#      version string — that import is the thing which actually has to
#      work, and it is the first thing the config reader does
#   2. builds a private virtualenv at ~/.amik/venv. Private on purpose:
#      amik has a dependency, and putting it in somebody's system python
#      is how a tool gets blamed for a conflict in an unrelated project
#   3. installs amik into it — from this clone if you are standing in
#      one, from GitHub if you were piped here
#   4. symlinks ~/.local/bin/amik at that venv's console script, so the
#      whole machine can run `amik` without knowing where the venv lives
#   5. adds ~/.local/bin to PATH in ~/.zshrc, if it is not there already
#
# It does NOT create a board, and that is deliberate. A board belongs to
# a project, and the only directory an installer could seed is whichever
# one you happened to be standing in when you ran it. `amik serve` in a
# project with no board writes one from the starter, which is the same
# gesture in the place that knows what it means.
#
# It installs no daemon either. Serving and working a board are one
# process now; there is nothing to keep running in the background and
# nothing to keep in step.
#
# Env overrides (mostly for testing and packaging):
#   AMIK_HOME       where the virtualenv goes            (~/.amik)
#   AMIK_REPO_URL   what it installs when piped          (this repo)
#   AMIK_LOCAL_BIN  where the amik command goes          (~/.local/bin)

die() { echo "amik install: $*" >&2; exit 1; }
note() { echo "• $*"; }

# Piped from curl, stdin IS this script: bash reads it as it runs. Two
# consequences shape everything below, and both were learned the
# expensive way on a sibling project.
#
# The whole body is a FUNCTION called on the last line, so bash has
# parsed the entire file before any command runs. Without that, a child
# process that reads stdin swallows the rest of the script and the
# install stops halfway with no error.
#
# And nothing here may prompt. `GIT_TERMINAL_PROMPT=0` turns a private
# or mistyped repository into a failure with a message instead of a
# process waiting forever on a password nobody can see it asking for;
# every child gets `</dev/null` for the same reason.
export GIT_TERMINAL_PROMPT=0
export PIP_DISABLE_PIP_VERSION_CHECK=1

main() {

AMIK_HOME="${AMIK_HOME:-$HOME/.amik}"
LOCAL_BIN="${AMIK_LOCAL_BIN:-$HOME/.local/bin}"
REPO_URL="${AMIK_REPO_URL:-https://github.com/jeffkward/amik.git}"
VENV="$AMIK_HOME/venv"

# WHERE THIS SCRIPT IS, or nothing at all when it is being piped.
#
# `${BASH_SOURCE[0]}` is unset under `curl | bash`, and the obvious
# fallback to `$0` is a trap: `$0` is then "bash", whose dirname is
# ".", which is WHOEVER'S DIRECTORY THEY HAPPENED TO BE STANDING IN.
# The check below asks whether a pyproject.toml sits beside this
# script, so that fallback made it ask about the user's own project --
# and a Python developer running the one-liner from their own
# repository installed THAT, into a virtualenv named for us, behind a
# symlink to a command that does not exist.
SELF="${BASH_SOURCE[0]:-}"
if [ -n "$SELF" ] && [ -f "$SELF" ]; then
  SRC="$(cd "$(dirname "$SELF")" && pwd)"
else
  SRC=""                       # piped: there is no clone beside us
fi

# Guard before anything creates or removes: a stray AMIK_HOME must not
# be able to name $HOME or /.
case "$AMIK_HOME" in
  ""|"/"|"$HOME"|"$HOME/") die "refusing to install into '$AMIK_HOME'" ;;
esac

# ── 1. python ───────────────────────────────────────────────────────────────

PYTHON3="$(command -v python3)" || die "python3 not found"
"$PYTHON3" -c 'import tomllib' 2>/dev/null \
  || die "python3 >= 3.11 required (tomllib missing in $PYTHON3)"
"$PYTHON3" -c 'import venv' 2>/dev/null \
  || die "python3 venv module missing in $PYTHON3 (on Debian: apt install python3-venv)"

# ── 2. where it is coming from ──────────────────────────────────────────────

# Piped from the web there is no repository on disk — no pyproject.toml
# beside us — so pip fetches it instead. Asking the filesystem is more
# honest than a flag somebody has to remember to pass.
if [ -n "$SRC" ] && [ -f "$SRC/pyproject.toml" ]; then
  TARGET="$SRC"
  note "installing from this clone at $SRC"
else
  command -v git >/dev/null || die "git not found, and it is needed to fetch amik"
  TARGET="amik @ git+$REPO_URL@main"
  note "installing from $REPO_URL"
fi

# ── 3. the virtualenv ───────────────────────────────────────────────────────

mkdir -p "$AMIK_HOME"
if [ ! -x "$VENV/bin/python" ]; then
  "$PYTHON3" -m venv "$VENV" || die "could not create a virtualenv at $VENV"
  note "created $VENV"
fi
# --force-reinstall, and it is not belt-and-braces. `--upgrade` alone
# compares VERSION NUMBERS, and a project installed straight from a
# branch keeps the same one between releases -- so pip reads "amik
# 0.1.0 already satisfies amik @ git+...@main", skips the fetch, and
# reports success. Re-running this script then did nothing at all, for
# days, while saying "installed amik 0.1.0" every time. Measured: the
# venv still recorded the first commit it ever saw.
#
# The cost is reinstalling one dependency that has not changed, which
# takes a second in a script somebody runs by hand.
"$VENV/bin/pip" install --quiet --upgrade pip </dev/null >/dev/null 2>&1 || true
"$VENV/bin/pip" install --quiet --upgrade --force-reinstall "$TARGET" </dev/null \
  || die "pip could not install amik from $TARGET"
VERSION="$("$VENV/bin/python" -c 'from importlib.metadata import version
print(version("amik"))' 2>/dev/null || echo "?")"
note "installed amik $VERSION"

# ── 4. the `amik` command ───────────────────────────────────────────────────

# One symlink so the whole machine can run `amik` without knowing where
# the virtualenv is. Never clobber a real file of that name — only our
# own, or a stale, symlink gets replaced.
LINK="$LOCAL_BIN/amik"
mkdir -p "$LOCAL_BIN"
if [ -e "$LINK" ] && [ ! -L "$LINK" ]; then
  echo "WARNING: $LINK exists and isn't a symlink — leaving it alone." >&2
  echo "         Run amik as $VENV/bin/amik" >&2
  LINK="$VENV/bin/amik"
else
  ln -sfn "$VENV/bin/amik" "$LINK"
  note "linked $LINK → $VENV/bin/amik"
fi

# ── 5. PATH ─────────────────────────────────────────────────────────────────

# Guard on the rc FILE's contents rather than the live $PATH, so running
# this twice in one shell does not append the line twice.
_pathline='export PATH="$HOME/.local/bin:$PATH"'
if ! grep -qF "$_pathline" "$HOME/.zshrc" 2>/dev/null; then
  echo "$_pathline" >> "$HOME/.zshrc"
  note "added ~/.local/bin to PATH in ~/.zshrc (open a new terminal to pick it up)"
fi
case "${SHELL:-}" in
  *zsh) ;;
  *) echo "NOTE: your login shell isn't zsh. Add $LOCAL_BIN to its PATH" >&2
     echo "      so 'amik' is found in new terminals." >&2 ;;
esac
export PATH="$LOCAL_BIN:$PATH"

# ── 6. confirm ──────────────────────────────────────────────────────────────

"$LINK" --help >/dev/null 2>&1 || die "installed, but '$LINK --help' did not run"

echo
echo "amik is installed."
echo "  command: $LINK"
echo "  venv:    $VENV"
echo
echo "Give a project a board — it writes one on the first run:"
echo "  cd ~/your-project"
echo "  amik serve"
echo
echo "Then open http://127.0.0.1:4455, and tell amik how your project is"
echo "verified in amik/amik.toml before anything is allowed to work a card."
echo
echo "Also: amik status  ·  amik work --once  ·  amik land"
}

# LAST LINE, deliberately. See the note at the top: bash parses the
# whole file before this call, so a piped install cannot be cut in
# half by a child that reads stdin.
main "$@"
