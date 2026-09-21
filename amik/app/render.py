"""Amik's rendering: one Jinja environment, and the filters it needs.

**`StrictUndefined` is not a preference.** Jinja's default `Undefined`
compares False and renders empty, which is how a component contract gets
violated silently — a missing value looks like a deliberate blank. The
whole argument for using a template engine here rests on turning that
off, so a test asserts it.

`autoescape` is on for the same family of reasons: card prose is
arbitrary text, and the one place it is rendered as markup goes through
an explicit filter that says so.
"""
import datetime
import os

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

from . import markdown_render as md

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "templates")
STATIC = os.path.join(HERE, "static")


def _mtime(name):
    """Cache-busting from the file's own mtime. No hashing: the question
    is only "has this changed since the browser last looked", and a
    rebuild that changes nothing should not invalidate anything."""
    try:
        return str(int(os.path.getmtime(os.path.join(STATIC, name))))
    except OSError:
        return "0"


def _inline_md(text):
    """A card title: emphasis and code, never block structure. A title
    that grew a heading would break the row it sits in."""
    return Markup(md.inline_markdown(str(text or "")))


def _block_md(text):
    """Card prose — the Outcome pane and a question's context."""
    return Markup(md.markdown(str(text or "")))


def _parse(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def time_ago(value, now=None):
    """`1m` / `14h` / `15d` / `3mo` / `2y`. Empty for anything
    unparseable, because a board carries hand-edited dates and a crash is
    a worse answer than a blank."""
    when = _parse(value)
    if when is None:
        return ""
    now = now or datetime.datetime.now()
    secs = max(0, int((now - when).total_seconds()))
    if secs < 60:
        return "now"
    for unit, size in (("m", 60), ("h", 3600), ("d", 86400),
                       ("mo", 2592000), ("y", 31536000)):
        nxt = {"m": 3600, "h": 86400, "d": 2592000,
               "mo": 31536000, "y": None}[unit]
        if nxt is None or secs < nxt:
            return f"{secs // size}{unit}"
    return ""


def human_dt(value):
    when = _parse(value)
    return when.strftime("%Y-%m-%d %-I:%M%p").lower() if when else ""


def environment(base=""):
    """The environment, bound to a mount prefix.

    `base` is where Amik is mounted — "" standalone, "/amik" embedded —
    and every URL the templates build goes through `url` or `static` so
    one setting moves all of them.
    """
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        undefined=StrictUndefined,
        autoescape=True,
        trim_blocks=False,
        keep_trailing_newline=True,
    )
    prefix = base.rstrip("/")
    # The mount prefix itself, for the one attribute the script reads.
    env.globals["base"] = prefix
    env.globals["url"] = lambda path="": prefix + (path or "/")
    env.globals["static"] = (
        lambda name: f"{prefix}/static/{name}?v={_mtime(name)}")
    env.filters["inline_md"] = _inline_md
    env.filters["chat_md"] = _block_md
    env.filters["time_ago"] = time_ago
    env.filters["human_dt"] = human_dt
    return env


def board_page(data, base="", **ctx):
    return environment(base).get_template("board.html").render(
        board=data, **ctx)


def chips(card, base=""):
    """One card's chip row, rendered alone — what a save hands back so
    the tile's derived chips repaint without a reload."""
    return environment(base).get_template("_chips.html").render(
        c=card).strip()


def card_view(card, base=""):
    """What the modal shows while a card is being READ: its chip strip
    and its body as prose.

    Handed back by a save for the same reason the chips are — a reopened
    card has to show what the file now says, not what it said when the
    page loaded — and rendered here because a script cannot call the
    markdown filter.
    """
    return environment(base).get_template("_cardview.html").render(
        c=card).strip()


def card_data(card, base=""):
    """One card's hidden data block — the data attributes, the editor's
    source, its questions, its outcome and its dates.

    What `GET /cards/{id}` serves and what the modal fills itself from.
    Rendered here rather than assembled in a script because the dates
    need the `timestamp` macro and the prose needs the markdown filter,
    neither of which a script can call.
    """
    return environment(base).get_template("_carddata.html").render(
        c=card).strip()
