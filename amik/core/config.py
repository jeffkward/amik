"""Surgical edits to amik/amik.toml — the project's own declaration.

One key is writable from the UI and it is `armed`, the gate that decides
whether the loop may take a card unattended. Everything else in the file
is hand-written on purpose and stays that way.

The same prime directive as the board's door: the file is hand-authored,
comment-heavy and git-tracked, so a write rewrites ONE line and every
other byte comes through untouched. A wholesale rewrite would take the
comments with it, and those comments are why anyone can read the file.

Two layers, as in `edit`:
  - `arm(text, armed)` is PURE — takes the file text, returns new text.
  - `set_armed(root, armed)` reads, applies, writes, reads back, and
    answers in the reader shape {ok, data|reason}, never raising.
"""
import os
import re
import tomllib

# The value is matched as one non-space token and whatever follows is
# carried through, so a trailing comment on the line survives the write.
_ARMED = re.compile(r"^(\s*armed\s*=\s*)(\S+)(.*)$")
_TABLE = re.compile(r"^\s*\[")


def _ok(data):
    return {"ok": True, "data": data}


def _no(reason):
    return {"ok": False, "reason": reason}


def path(root):
    return os.path.join(root, "amik", "amik.toml")


def arm(text, armed):
    """The file's text with `armed` set to a real boolean.

    Only the TOP-LEVEL `armed` is touched, and a new one is inserted
    above the first `[table]` header rather than appended to the file. A
    key written below a header belongs to that table, so an appended
    `armed = true` would be `[loop].armed` — a line that reads exactly
    like consent and that the reader never looks at.
    """
    value = "true" if armed else "false"
    lines = text.split("\n")
    end = len(lines)
    for i, line in enumerate(lines):
        if _TABLE.match(line):
            end = i
            break
        found = _ARMED.match(line)
        if found:
            lines[i] = found.group(1) + value + found.group(3)
            return "\n".join(lines)

    block = ["armed = " + value]
    if end and lines[end - 1].strip():
        block.insert(0, "")
    if end < len(lines) and lines[end].strip():
        block.append("")
    lines[end:end] = block
    return "\n".join(lines)


def set_armed(root, armed):
    """Arm or disarm this project, and prove it by reading it back.

    The read-back is not ceremony: this file carries `verify`, and a
    board whose declaration stopped parsing is a board no agent can work
    at all. If the rewrite did not land as a real boolean the original
    text goes back and the write is refused — the same law the board's
    door carries, applied to the more expensive file.
    """
    target = bool(armed)
    where = path(root)
    try:
        with open(where, encoding="utf-8") as f:
            before = f.read()
    except OSError:
        return _no("no amik/amik.toml in this instance")

    # An in-place truncate-write, never an atomic rename: this is a file
    # someone may have open in an editor.
    def _put(text):
        with open(where, "w", encoding="utf-8") as f:
            f.write(text)

    try:
        _put(arm(before, target))
    except OSError as exc:
        return _no("could not write amik.toml: {}".format(
            exc.strerror or exc))

    try:
        with open(where, "rb") as f:
            cfg = tomllib.load(f)
    except (OSError, ValueError):
        cfg = None
    if cfg is None or cfg.get("armed") is not target:
        try:
            _put(before)
        except OSError:
            pass
        return _no("the file did not read back armed = {} — nothing was "
                   "changed".format(str(target).lower()))
    return _ok({"armed": target})
