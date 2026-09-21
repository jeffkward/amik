"""Surgical edits to amik/board.jsonl — the same prime directive as
config_edit.py, applied to the board.

The file is hand-authored and git-tracked, so a drag rewrites ONLY the
lines whose rank or status actually changed; every other line, blank line
and non-JSON line comes through byte-for-byte. That works because every
line round-trips exactly through json.dumps(obj, ensure_ascii=False) and
Python dicts keep their key order — so a rewritten line comes back in the
author's key order with its non-ASCII characters intact.

Two layers, as in config_edit:
  - move_item(text, ...) is PURE — takes the file text, returns new text,
    raises ValueError when the target cannot be found.
  - move(root, ...) reads, applies, writes, and answers in the reader
    shape {ok, data|reason}, never raising.
"""
import datetime
import json
import os
import re

from . import log

from . import markdown as amik_markdown


def _stamp():
    """A full ISO timestamp, not a date. The modal shows "Updated 3m", and
    minutes cannot be recovered from a day. Rows written before this carry
    bare dates, which the age filter still parses -- they just read coarser."""
    return datetime.datetime.now().isoformat(timespec="seconds")


def _parse(lines):
    """line index -> object, for the lines that are JSON objects. A line
    that is blank or unparseable is simply absent, which is how it
    survives untouched."""
    out = {}
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out[i] = obj
    return out


def _sort_key(parsed, i):
    """Same ordering the page shows: rank first, unranked rows after the
    ranked ones in file order."""
    rank = parsed[i].get("rank")
    if isinstance(rank, bool) or not isinstance(rank, (int, float)):
        return (1, 0, i)
    return (0, rank, i)


def _column(parsed, status):
    """The rows the BOARD shows in that column, in the order it shows them.
    Every row is work, so the column is simply its status -- the browser
    computes a drop index over the cards it can see, and there is no longer
    a class of row it never rendered."""
    return sorted((i for i, o in parsed.items() if o.get("status") == status),
                  key=lambda i: _sort_key(parsed, i))


def move_item(text, item_id, to_status, to_index):
    """Move one row to `to_index` (0-based) of `to_status`, renumbering
    the columns it left and joined so both stay 1..n contiguous."""
    if not to_status:
        raise ValueError("no target status")
    _check_status(to_status)
    lines = text.split("\n")
    parsed = _parse(lines)

    src = next((i for i, o in parsed.items() if o.get("id") == item_id), None)
    if src is None:
        raise ValueError(f"no amik item with id {item_id!r}")
    row = parsed[src]
    from_status = row.get("status")

    source = _column(parsed, from_status)
    source.remove(src)
    dest = source if to_status == from_status else _column(parsed, to_status)
    dest.insert(max(0, min(to_index, len(dest))), src)

    changed = {src}
    if to_status != from_status:
        row["status"] = to_status
        # updated_at follows a COLUMN change only: reordering inside a
        # column is triage, not a change to the item, and stamping it
        # would make every re-prioritising pass look like work on every
        # card it slid past.
        row["updated_at"] = _stamp()

    columns = [dest] if dest is source else [source, dest]
    for column in columns:
        for position, i in enumerate(column, start=1):
            if parsed[i].get("rank") != position:
                parsed[i]["rank"] = position
                changed.add(i)

    for i in changed:
        lines[i] = json.dumps(parsed[i], ensure_ascii=False)
    return "\n".join(lines)


def move(root, item_id, to_status, to_index, fingerprint=None, by=None):
    """File-level wrapper. Refuses when the file has changed since the
    page was rendered, so a drag can never discard a hand edit made in
    the meantime."""
    from . import board                               # circular at import
    # A COLUMN THAT EXISTS. The pure `move_item` takes any string on
    # purpose -- a hand-edited board may carry a status this version has
    # never heard of, and the reader gives it a column of its own rather
    # than dropping the row. A WRITE is the other case: a typo here
    # invents a column nobody can see from the page, and strands the
    # card in it.
    #
    # Checked here rather than in `move_item` because that function is
    # the one with the hand-edited board's contract, and here rather
    # than only in the HTTP route because an agent reaches this through
    # the command line and deserves the same refusal the page gives.
    known = [c[0] for c in board.AMIK_COLUMNS]
    if to_status not in known:
        return {"ok": False,
                "reason": "unknown status {!r} — the columns are {}".format(
                    to_status, ", ".join(known))}
    path = os.path.join(root, "amik", "board.jsonl")
    if fingerprint is not None:
        if board.amik_fingerprint(root) != fingerprint:
            return {"ok": False, "reason": "stale"}
    try:
        with open(path) as f:
            text = f.read()
    except OSError as exc:
        return {"ok": False, "reason": f"unreadable: {exc.strerror}"}
    except ValueError as exc:                  # UnicodeDecodeError is one
        return {"ok": False, "reason": f"unreadable: {type(exc).__name__}"}
    # Where it came FROM, read out of the text already in hand rather
    # than by a second parse: the board file is the only place a card's
    # current column lives, and after the write below it is gone.
    was = _status_in(text, item_id)
    try:
        new = move_item(text, item_id, to_status, to_index)
    except ValueError as exc:
        return {"ok": False, "reason": str(exc)}
    try:
        # In place, never a rename: the instance root is somebody's
        # working directory, often open in an editor, and replacing the
        # inode under an open file is how that editor ends up writing
        # back what it read minutes ago.
        with open(path, "w") as f:
            f.write(new)
    except OSError as exc:
        return {"ok": False, "reason": f"unwritable: {exc.strerror}"}
    log.note(root, item_id, "move", by, **{"from": was, "to": to_status})
    return {"ok": True, "data": {"fingerprint":
                                 board.amik_fingerprint(root)}}


def _status_in(text, item_id):
    """One row's column, out of raw board text. "" when it is not there.

    A malformed line is skipped rather than fatal, the same way every
    other reader here treats one.
    """
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("id") == item_id:
            return row.get("status") or ""
    return ""


# Every field update_item may rewrite. Everything else is either
# provenance the system writes (rank, created_at) or the drag's business
# (status, rank) — two writers for one field is how a board and its file
# drift.
EDITABLE = ("title", "body", "planning", "group", "requires_prototype",
            "halt", "docs")

# How a closed card closed, closed on purpose the way the ladder is.
# `abandoned` means dropped; `retired` means measured and disproven.
# Retired 2026-09-17 with the column rename. Hard refusals, never
# aliases: an old spelling quietly accepted is a row that reads fine and
# sorts into a column that no longer exists.
RETIRED_STATUS = {"wont_do": "abandoned"}


def _check_status(value):
    """Refuse a renamed status by name, so the error reads as the change
    it is rather than as a typo."""
    if value in RETIRED_STATUS:
        raise ValueError(
            f"{value!r} was renamed to {RETIRED_STATUS[value]!r}")

# The planning ladder, closed on purpose: a typo'd rung would print as a
# state of the ladder that does not exist. It answers ONE question — does
# this card still owe thinking — and nothing about how the work is done,
# which is what the handling toggles are for.
RUNGS = ("needs-brainstorm", "has-plan")

# The Planning and Area selects' own "clear this" option. A form posts no
# field at all for a box nobody touched, but an empty string IS what a
# closed select posts for its blank option — indistinguishable from that
# absence once the form layer collapses it, so a deliberate clear needs a
# value of its own to survive the trip.
CLEARED = "none"


def _slug(title):
    out = re.sub(r"[^a-z0-9]+", "-", str(title).lower()).strip("-")
    return out[:60] or "item"


# A card's `id` is hand-authored, so it is untrusted input to a path
# join. The writer REFUSES a bad one rather than reading nothing, because
# unlike the reader it would be creating a file.
_CARD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def card_path(root, item_id):
    """Where one card's prose lives."""
    if not isinstance(item_id, str) or not _CARD_ID.match(item_id):
        raise ValueError(f"{item_id!r} is not a usable card id")
    return os.path.join(root, "amik", "cards", item_id + ".md")


def write_prose(root, item_id, text):
    """Write a card's prose, or REMOVE the file when the text is empty.

    A card with no prose has no file: the reader treats absence as an
    empty body, so an empty file would be a second way to say the same
    thing. In place, never a rename — the repo root may be open in an
    editor or a notes app
    and replacing the inode under an open file is how an editor writes
    back what it read minutes ago.
    """
    path = card_path(root, item_id)
    if not text:
        try:
            os.unlink(path)
        except OSError:
            pass
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


_QUESTIONS_HEADING = "## Questions"


def replace_section_body(prose, heading, text):
    """Replace the body beneath one `### <heading>` under `## Questions`.

    Surgical, the way a line of the board file is: everything outside the
    target section comes back byte-for-byte, so answering a question
    shows as the sentences that changed rather than as a rewritten card.
    The alternative — rebuilding the document from parsed structure —
    would make the parser an author of prose it only meant to read.

    Pure, and over a string rather than a file, so the same function
    serves an editor and a route without knowing which called it. Raises
    ValueError when the heading is not there: unlike a reader, this is
    about to change something, and a silent no-op looks like a save that
    worked.
    """
    lines = str(prose).split("\n")
    wanted = str(heading).strip()
    inside, start, end = False, None, None
    for i, stripped, fenced in amik_markdown.walk(prose):
        if not fenced and stripped == _QUESTIONS_HEADING:
            # A repeated section heading closes the question being
            # replaced, but does not end the scan: the reader collects
            # questions from every such section, so the writer has to be
            # able to target them too. Closing here is what keeps this
            # line itself out of the replaced range -- the result is
            # spliced positionally, so a line inside that range is a
            # line deleted.
            if start is not None and end is None:
                end = i
                break
            inside = True
            continue
        if inside and not fenced and stripped.startswith("## "):
            if start is not None:
                end = i
            break
        if not inside:
            continue
        is_heading = not fenced and stripped.startswith("### ")
        if is_heading and start is None:
            if amik_markdown.heading_text(stripped, "### ") == wanted:
                start = i + 1
        elif start is not None and is_heading:
            end = i
            break
    if start is None:
        raise ValueError(f"no question heading {heading!r}")
    if end is None:
        end = len(lines)
    # The asker's context stays. It sits between the heading and the
    # answer, and a splice that began at the heading would overwrite the
    # very text that justified the question — the reader shows it, so the
    # writer has to keep it, through the same rule.
    start += amik_markdown.context_span(lines[start:end])
    body = ["", str(text).strip(), ""] if str(text).strip() else [""]
    return "\n".join(lines[:start] + body + lines[end:])


def replace_overview(prose, text):
    """A card's prose with its BODY replaced and its promoted sections
    carried through verbatim.

    The modal edits the body alone — Questions and Outcome each have a
    tab of their own, and a second editable view of one slice of the
    prose would be a second writer for the same text — so a save carries
    only that much, and this is what puts it back.

    The boundary is `amik_markdown.split_promoted`, the same rule the
    reader renders by. Reader and writer must agree on it or a save
    splices over the sections the page was showing beside it.
    """
    promoted = amik_markdown.split_promoted(prose)[1]
    body = str(text).rstrip()
    if not promoted:
        return body
    return body + "\n\n" + promoted if body else promoted


def upsert_section(prose, heading, text):
    """Replace the body of a top-level `## <heading>`, creating it if it
    is not there.

    The asymmetry with `replace_section_body` is deliberate and is the
    reason this is a second function rather than a flag on the first.
    Answering a question that does not exist is a mistake, so that writer
    refuses. Writing a card's FIRST verdict is the normal case, so this
    one appends. One function cannot hold both contracts honestly.

    Surgical the same way: every line outside the target section comes
    back byte-for-byte. An empty `text` leaves the heading standing with
    an empty body — reviewed and cleared is not the same claim as never
    reviewed.
    """
    lines = str(prose).split("\n")
    wanted = str(heading).strip()
    target = "## " + wanted             # the line to append when absent
    start = end = None
    for i, stripped, fenced in amik_markdown.walk(prose):
        if start is None:
            if not fenced and amik_markdown.heading_text(stripped, "## ") == wanted:
                start = i + 1
            continue
        if not fenced and stripped.startswith("## "):
            end = i
            break
    body = ["", str(text).strip(), ""] if str(text).strip() else [""]
    if start is None:
        # Appended, not inserted: a card's sections are the owner's
        # order, and a writer that chose a position would be rearranging
        # prose it was only asked to add to.
        head = lines[:]
        while head and not head[-1].strip():
            head.pop()
        tail = [target] + body
        return "\n".join((head + [""] + tail) if head else tail)
    if end is None:
        end = len(lines)
    return "\n".join(lines[:start] + body + lines[end:])


def append_section(prose, heading, text):
    """Add to a top-level `## <heading>`, creating it when absent.

    Appends where `upsert_section` replaces, and the difference IS the
    contract rather than a flag: a card worked twice has two outcomes and
    the second does not supersede the first, the same law a ruling
    carries. A writer that could do either would eventually do the wrong
    one silently.

    A rule separates a new entry from what is already there, so two
    outcomes read as two rather than blurring into one paragraph.
    Surgical the same way: every line outside the section comes back
    byte-for-byte.
    """
    add = str(text).strip()
    if not add:
        return str(prose)
    lines = str(prose).split("\n")
    wanted = str(heading).strip()
    start = end = None
    for i, stripped, fenced in amik_markdown.walk(prose):
        if start is None:
            if not fenced and amik_markdown.heading_text(stripped, "## ") == wanted:
                start = i + 1
            continue
        if not fenced and stripped.startswith("## "):
            end = i
            break
    if start is None:
        head = lines[:]
        while head and not head[-1].strip():
            head.pop()
        tail = ["## " + wanted, "", add, ""]
        return "\n".join((head + [""] + tail) if head else tail)
    if end is None:
        end = len(lines)
    existing = lines[start:end]
    while existing and not existing[-1].strip():
        existing.pop()
    body = existing + (["", "---", ""] if any(l.strip() for l in existing)
                       else [""])
    return "\n".join(lines[:start] + body + [add, ""] + lines[end:])


def as_context(text):
    """`text` as the blockquote lines a question carries above its answer.

    Every line is quoted, blank ones included as a bare `>`, so the block
    is contiguous — `context_span` stops at the first line that is
    neither blank nor quoted, and an unquoted blank in the middle would
    hand the rest of the asker's own words to the answer.
    """
    lines = str(text).strip().split("\n")
    return [("> " + ln.rstrip()) if ln.strip() else ">" for ln in lines]


def _append_question(prose, heading, context=None):
    """`prose` with `### <heading>` appended, empty, to its `## Questions`
    section -- creating the section first when the card has none.

    Appended rather than inserted, the same reasoning as `upsert_section`:
    a card's existing questions are in the order they were asked, and a
    writer that chose a different position would be rearranging prose it
    was only asked to add to.
    """
    lines = str(prose).split("\n")
    start = end = None
    for i, stripped, fenced in amik_markdown.walk(prose):
        if start is None:
            if not fenced and stripped == _QUESTIONS_HEADING:
                start = i + 1
            continue
        if not fenced and stripped.startswith("## "):
            end = i
            break
    question = ["### " + heading, ""]
    if str(context or "").strip():
        question += as_context(context) + [""]
    if start is None:
        head = lines[:]
        while head and not head[-1].strip():
            head.pop()
        tail = [_QUESTIONS_HEADING, ""] + question
        return "\n".join((head + [""] + tail) if head else tail)
    if end is None:
        end = len(lines)
    section = lines[start:end]
    while section and not section[-1].strip():
        section.pop()
    gap = [""] if section else []
    return "\n".join(lines[:start] + section + gap + question + lines[end:])


def ask(root, item_id, heading, context=None,
        fingerprint=None, by=None):
    """Raise a question through the door, the way an agent that needs a
    decision does.

    Creates the card's `## Questions` section when it has none and
    appends `### <heading>` with an empty body -- an empty body under a
    question heading already means unanswered, so a freshly asked
    question needs no separate flag.

    `context` is what the ASKER knows and the owner needs in order to
    decide: options, measurements, what was already tried. It is written
    as a blockquote directly under the heading, which is the one place
    the reader will not mistake for an answer. Written any other way it
    lands in the box the owner types into and marks the question
    answered -- the queue then stops holding the card, and the page shows
    a question that reads as already decided.

    Refuses a heading the card already carries. The section writers
    refuse an unknown heading because a silent no-op reads as a save
    that worked; a silently duplicated question is that failure one
    level up -- the first occurrence would win, so an answer meant for
    the second writes into the first and the card looks like the save
    failed.

    Refuses, too, when the appended prose does not itself read the
    question back: an unclosed fence swallows everything after it, so a
    section landing inside one would report success on a write nothing
    can read -- the same failure arriving through a third door, since a
    card the reader cannot see a question on is a card the queue is
    free to take. Checked before anything is written, and never
    repaired: a fence is the owner's prose, not this verb's to rewrite.

    Stamps `updated_at` like every other writer here, and unlike every
    other writer, this one has to: an unanswered question is what HOLDS
    a card, so leaving its row looking untouched would be the one event
    that stops a card moving going missing from whatever reads recency.

    The line write goes through `_write` first and is stamped before the
    prose is written -- not because the reverse order would lose the
    question (prose first would leave it present and holding the card
    even if the line write then failed), but because this is the same
    half-applied shape `update` already accepts for a `body` field: a
    prose-write failure after a successful line write leaves the row
    claiming an update the card's text does not yet show.
    """
    from . import board                               # circular at import
    wanted = str(heading).strip()
    new_prose = []

    def apply(text):
        lines = text.split("\n")
        parsed = _parse(lines)
        src = next((i for i, o in parsed.items() if o.get("id") == item_id),
                    None)
        if src is None:
            raise ValueError(f"no amik item with id {item_id!r}")
        card_path(root, item_id)          # raises for an id write_prose
                                           # could never use as a filename
        prose = board._card_prose(root, item_id)
        if any(q["heading"] == wanted for q in board._card_questions(prose)):
            raise ValueError(f"already asked {wanted!r}")
        appended = _append_question(prose, wanted, context)
        if not any(q["heading"] == wanted
                   for q in board._card_questions(appended)):
            raise ValueError("unreadable after the change -- an unclosed "
                             "fence swallows the section")
        new_prose.append(appended)
        row = parsed[src]
        row["updated_at"] = _stamp()
        lines[src] = json.dumps(row, ensure_ascii=False)
        return "\n".join(lines), item_id

    res = _write(root, fingerprint, apply)
    if res["ok"]:
        try:
            write_prose(root, item_id, new_prose[0])
        except OSError as exc:
            return {"ok": False, "reason": f"unwritable: {exc.strerror}"}
        log.note(root, item_id, "ask", by, count=1, heading=heading)
    return res


def attribution(model=None, by=None):
    """The one line that says who wrote an outcome.

    Two halves, and they differ in how much they can be trusted. The
    HARNESS comes from the environment, so it cannot be misreported. The
    MODEL is knowable only to the agent itself — no environment variable
    carries it — so it is passed in and self-reported, exactly like the
    outcome it sits under. This attributes; it does not prove.

    Written even when the model was not supplied, and saying so. An
    omitted line cannot be told apart from an entry made before
    attribution existed, and a gap you cannot see is a gap nobody closes.
    """
    # `by` is for a note AMIK wrote rather than an agent. "Worked by
    # model unrecorded" is what the loop's own shared-state report said
    # before this, which reads as an agent that forgot to sign — the
    # opposite of the truth, since no agent wrote it at all.
    if by:
        return f"*Noted by {by}*"
    parts = [str(model).strip() if str(model or "").strip()
             else "model unrecorded"]
    harness = _harness()
    if harness:
        parts.append(harness)
    return "*Worked by " + " · ".join(parts) + "*"


# `claude-code_2-1-267_agent` is the shape one harness announces itself
# in. Tidied when it matches and passed through verbatim when it does
# not: a prettier line is worth having, and a vendor changing its format
# must cost legibility rather than correctness.
_HARNESS = re.compile(r"^([a-z][a-z0-9-]*)_(\d+(?:-\d+)*)_agent$", re.I)


def _harness():
    raw = (os.environ.get("AI_AGENT") or "").strip()
    if not raw:
        return ""
    m = _HARNESS.match(raw)
    return f"{m.group(1)} {m.group(2).replace('-', '.')}" if m else raw


def record_outcome(root, item_id, text, model=None, fingerprint=None,
                   by=None):
    """Write what a card produced, into its `## Outcome` section.

    Appends, never overwrites — the same law a ruling carries. A card
    worked twice has two outcomes and the second does not supersede the
    first: this board's own first tabbed-modal card produced a prototype,
    then a build after the owner picked from it, and either half alone
    misreports what happened.

    Refuses empty. An outcome is what gates an agent closing the card, so
    a verb that accepted "" would let the gate be satisfied by a write
    that said nothing.

    Refuses, too, a write the reader cannot read back — an unclosed fence
    in the owner's prose swallows everything after it, so an appended
    section can land inside the swallowed region and report success on a
    write nothing can see. Checked before anything is written and never
    repaired: a fence is the owner's prose, not this verb's to rewrite.

    Every entry carries an attribution line naming the model and harness
    that wrote it — see `attribution`. A board worked by more than one
    model, or by one whose quality moved, is unreadable without it: the
    difference shows up as "the board got worse" with nothing to point
    at.
    """
    from . import board                               # circular at import
    body = str(text or "").strip()
    if body:
        body = body + "\n\n" + attribution(model, by=by)
    new_prose = []

    def apply(line_text):
        lines = line_text.split("\n")
        parsed = _parse(lines)
        src = next((i for i, o in parsed.items() if o.get("id") == item_id),
                   None)
        if src is None:
            raise ValueError(f"no amik item with id {item_id!r}")
        if not body:
            raise ValueError("an outcome cannot be empty")
        card_path(root, item_id)           # raises for an unusable id
        prose = board._card_prose(root, item_id)
        appended = append_section(prose, "Outcome", body)
        if not board._card_outcome(appended).strip():
            raise ValueError("unreadable after the change -- an unclosed "
                             "fence swallows the section")
        new_prose.append(appended)
        row = parsed[src]
        row["updated_at"] = _stamp()
        lines[src] = json.dumps(row, ensure_ascii=False)
        return "\n".join(lines), item_id

    res = _write(root, fingerprint, apply)
    if res["ok"]:
        try:
            write_prose(root, item_id, new_prose[0])
        except OSError as exc:
            return {"ok": False, "reason": f"unwritable: {exc.strerror}"}
        # The MODEL rides the line. A board worked by more than one
        # model over its life has to say which wrote what, and the row
        # carries no room for it.
        log.note(root, item_id, "outcome", by, model=model)
    return res


def create_item(text, title, status="inbox", at_top=True, raised_by=None):
    """Append a new row to its column, renumbering the rest.

    `at_top` is WHO is adding. The owner through the UI lands at the top —
    their own newest thought is not jumping their own queue. An AGENT lands at
    the bottom, because nothing an agent adds may jump the owner's queue;
    that law was written down before any verb could honour it, and this
    parameter is the verb honouring it.

    `raised_by` records the adder when it is not the owner. Absent means
    the owner, which is the common case and needs no field.

    Returns (new_text, new_id).
    """
    if not title or not str(title).strip():
        raise ValueError("a new item needs a title")
    title = str(title).strip()
    lines = text.split("\n")
    parsed = _parse(lines)

    taken = {o.get("id") for o in parsed.values()}
    base = _slug(title)
    new_id, n = base, 2
    while new_id in taken:                  # ids are the door's handle on
        new_id, n = f"{base}-{n}", n + 1    # a row — never reuse one

    now = _stamp()
    # No `body`: prose lives in amik/cards/<id>.md and a card with none
    # has no file. A "body": "" here would be a second way to say empty.
    row = {"id": new_id, "title": title, "status": status, "planning": None,
           "rank": 1, "created_at": now, "updated_at": now}
    if raised_by:
        row["raised_by"] = str(raised_by)

    # Insert the line first so the renumber below sees it in its column.
    at = len(lines)
    while at and not lines[at - 1].strip():
        at -= 1                             # keep the trailing newline last
    lines.insert(at, json.dumps(row, ensure_ascii=False))
    parsed = _parse(lines)
    src = next(i for i, o in parsed.items() if o.get("id") == new_id)

    column = _column(parsed, status)
    column.remove(src)
    column.insert(0 if at_top else len(column), src)
    changed = set()
    for position, i in enumerate(column, start=1):
        if parsed[i].get("rank") != position:
            parsed[i]["rank"] = position
            changed.add(i)
    for i in changed:
        lines[i] = json.dumps(parsed[i], ensure_ascii=False)
    return "\n".join(lines), new_id


def update_item(text, item_id, fields):
    """Rewrite one row's owner-editable STATE, and return its prose for
    the caller to write to the card file.

    Returns (new_text, prose) where prose is None when `body` was not
    among the fields. Prose is deliberately not written here: this
    function is pure, and the file write belongs to `update`.
    """
    unknown = [k for k in fields if k not in EDITABLE]
    if unknown:
        raise ValueError(f"not editable: {', '.join(sorted(unknown))}")
    lines = text.split("\n")
    parsed = _parse(lines)
    src = next((i for i, o in parsed.items() if o.get("id") == item_id), None)
    if src is None:
        raise ValueError(f"no amik item with id {item_id!r}")
    row = parsed[src]

    prose = None
    for key, value in fields.items():
        value = "" if value is None else str(value)
        if key in ("planning", "group"):
            value = value.strip()
            # The select's own "clear this" option, not a blank string: a
            # form field posts no value at all when nobody touched it, so
            # an actual empty string never reaches here — only the
            # sentinel does, standing for a deliberate clear.
            if value == CLEARED:
                value = ""
            if key == "planning" and value and value not in RUNGS:
                raise ValueError(f"{value!r} is not a rung of the ladder")
            # An empty box means "nothing here", not a blank string on the
            # row — the readers test emptiness, not presence.
            row[key] = value or None
        elif key == "title":
            if not value.strip():
                raise ValueError("an item needs a title")
            row[key] = value.strip()
        elif key == "body":
            prose = value
        elif key in ("requires_prototype", "halt"):
            # A form sends "on"; the toggle's own JS sends "off" rather
            # than an empty value, because an empty form field arrives at
            # the route as no field at all and this branch would never run.
            # A caller off the door -- an agent script clearing a halt it
            # set itself -- passes a real Python bool or int rather than a
            # form string, and `str(False)`/`str(0)` stringify to "False"/
            # "0": non-empty, and not "off", so without this the obvious
            # way to clear the field ARMS it instead. Stored as a real
            # boolean, and REMOVED when false: absent means no, and a
            # false on every row is noise in a file read by eye.
            if value.strip() and value.strip().lower() not in ("off", "false", "0"):
                row[key] = True
            else:
                row.pop(key, None)
        elif key == "docs":
            # Repo-relative paths a build can open. The `has-plan` rung
            # claims a plan exists and THIS is where it is named -- the
            # conflict chip reads emptiness here, so a rung with nothing
            # in this field prints "plan not named" on the card.
            #
            # It was on rows for months with no writer, which made that
            # chip a gate on a field only a hand edit could satisfy.
            #
            # A list from a Python caller; newline- or comma-separated
            # text from anything posting a form. Removed when empty,
            # because the readers test emptiness and a `[]` on a row read
            # by eye says less than no key at all.
            raw = fields[key]
            if isinstance(raw, (list, tuple)):
                items = list(raw)
            else:
                items = re.split(r"[\n,]", str(raw or ""))
            paths = [str(p).strip() for p in items if str(p).strip()]
            if paths:
                row[key] = paths
            else:
                row.pop(key, None)
        else:
            row[key] = value

    # A legacy inline body is dropped the first time a row is written.
    row.pop("body", None)
    row["updated_at"] = _stamp()
    lines[src] = json.dumps(row, ensure_ascii=False)
    return "\n".join(lines), prose


def delete_item(text, item_id):
    """Remove one row, renumbering the column it left so ranks stay
    1..n contiguous.

    There is no referential guard because there are no references left to
    dangle: `parent` and `related` were both retired, and nothing on a row
    names another row's `id` any more. A connection between two cards is
    prose in their bodies now, which no delete can break.
    """
    lines = text.split("\n")
    parsed = _parse(lines)

    src = next((i for i, o in parsed.items() if o.get("id") == item_id), None)
    if src is None:
        raise ValueError(f"no amik item with id {item_id!r}")

    status = parsed[src].get("status")
    del lines[src]
    parsed = _parse(lines)

    changed = set()
    for position, i in enumerate(_column(parsed, status), start=1):
        if parsed[i].get("rank") != position:
            parsed[i]["rank"] = position
            changed.add(i)
    for i in changed:
        lines[i] = json.dumps(parsed[i], ensure_ascii=False)
    return "\n".join(lines)


def create(root, title, fingerprint=None, at_top=True,
           raised_by=None, by=None):
    """File-level wrapper for create_item, reader-shaped."""
    res = _write(root, fingerprint,
                 lambda text: create_item(text, title, at_top=at_top,
                                          raised_by=raised_by))
    if res["ok"]:
        # A new idea always lands in `inbox`, so the column is stated
        # rather than read back: naming it here is what makes the line
        # answer "where did this start" without a second lookup.
        log.note(root, res["data"]["id"], "create", by,
                 to="inbox", title=title)
    return res


def update(root, item_id, fields, fingerprint=None, by=None):
    """File-level wrapper for update_item, reader-shaped.

    Two targets, routed by field: state to the line, prose to the card
    file. No field has two writers. A hand-authored id that cannot name
    a card file is refused up front when `body` is among the fields —
    before the line is touched, so a refusal can never follow a write
    that already happened. A state-only update never reaches the card
    file at all, so such an id is no obstacle to it.
    """
    if "body" in fields:
        try:
            card_path(root, item_id)
        except ValueError as exc:
            return {"ok": False, "reason": str(exc)}

    # What the card was, read BEFORE the write: a toggle is only an
    # event when it changed, and an answer is only an answer against
    # the count it started from.
    before = _row_before(root, item_id, "body" in fields)
    prose = []

    def apply(text):
        new, text_prose = update_item(text, item_id, fields)
        prose.append(text_prose)
        return new, item_id

    res = _write(root, fingerprint, apply)
    # Only after the line write succeeded — a refused or stale write must
    # not leave prose on disk for a state change that did not happen.
    if res["ok"] and prose and prose[0] is not None:
        try:
            write_prose(root, item_id, prose[0])
        except OSError as exc:
            return {"ok": False, "reason": f"unwritable: {exc.strerror}"}
    if res["ok"]:
        _log_update(root, item_id, fields, before, by)
    return res


def _log_update(root, item_id, fields, before, by):
    """The parts of an update that are EVENTS.

    A title or a body edit is not one: they fire on every save, and a
    log recording them buries the lines somebody wanted under a
    keystroke history. `git diff` is already a better record of prose.

    The toggles are, because each changes what the queue does with the
    card — a pause holds everything ranked below it. Only an actual
    CHANGE: setting halt to what it already was is the modal being
    closed, not a decision being made.

    Answers are, because answering is the owner's own gesture and how
    much of it landed is the interesting part. Counted by what stopped
    being unanswered, which is the only honest measure — a save can
    answer one of three.
    """
    for field in ("halt", "requires_prototype"):
        if field in fields and bool(fields[field]) != bool(
                before.get(field)):
            log.note(root, item_id, "toggle", by,
                     field=field, value=bool(fields[field]))
    if "body" in fields:
        from . import board
        now = sum(1 for q in board._card_questions(fields["body"] or "")
                  if not q["answered"])
        was = before.get("unanswered")
        if was is not None and now < was:
            log.note(root, item_id, "answer", by, count=was - now)


def discard_prototype(root, item_id):
    """Remove a card's design pass.

    Idempotent: every close path calls it and most cards never had one,
    so a refusal would make the common case an error.

    This is the only thing that removes a prototype now. They left git
    on 2026-09-17 — a tracked prototype lives on one branch and is
    invisible from every other — and with them untracked, no checkout
    and no branch delete tidies one up incidentally any more.

    The id is hand-authored and reaches a path join, so it is checked
    against the same shape the reader uses. A verb that DELETES earns
    that check more than a reader does.
    """
    import shutil
    # This module's own `_CARD_ID`, not the reader's. The duplication is
    # deliberate and pinned by a test: the reader TOLERATES a bad id by
    # returning no prose, where a writer must refuse one. Same pattern,
    # different consequence.
    if not isinstance(item_id, str) or not _CARD_ID.match(item_id):
        return {"ok": False, "reason": f"unusable card id {item_id!r}"}
    path = os.path.join(root, "amik", "prototypes", item_id)
    if not os.path.isdir(path):
        return {"ok": True, "data": {"removed": False}}
    try:
        shutil.rmtree(path)
    except OSError as exc:
        return {"ok": False, "reason": f"could not remove: {exc.strerror}"}
    return {"ok": True, "data": {"removed": True}}


def set_branch(root, item_id, name, fingerprint=None, by=None):
    """Record the branch a card was built on, or remove the record.

    Not an owner-editable field: provenance is written by the system,
    never typed, and a hand-entered branch name is a claim about git that
    nothing checked. Removing it is how shipped work stops looking
    unfinished — absent rather than blank, because a blank string would
    be a second way to say the same thing.
    """
    def apply(text):
        lines = text.split("\n")
        parsed = _parse(lines)
        src = next((i for i, o in parsed.items()
                    if o.get("id") == item_id), None)
        if src is None:
            raise ValueError(f"no amik item with id {item_id!r}")
        row = parsed[src]
        value = str(name or "").strip()
        if value:
            row["branch"] = value
        else:
            row.pop("branch", None)
        row["updated_at"] = _stamp()
        lines[src] = json.dumps(row, ensure_ascii=False)
        return "\n".join(lines), item_id

    res = _write(root, fingerprint, apply)
    if res["ok"]:
        log.note(root, item_id, "branch", by,
                 branch=str(name or "").strip())
    return res


def _close_and_clean(root, item_id, trunk, to_status, by=None):
    """Drop the branch, sweep the prototype, move the card — in that
    order, and all or nothing.

    The branch goes FIRST because it is the step that can refuse: git
    will not delete the branch you are standing on. A card closed with
    its branch still alive is cleanup nobody comes back for, so a
    refusal here has to stop the whole verb rather than leave two of
    three done.
    """
    from . import board, git
    rows = board.amik(root)
    if not rows["ok"]:
        return {"ok": False, "reason": rows["reason"]}
    card = None
    for column in rows["data"]["columns"]:
        for row in column["cards"]:
            if row.get("id") == item_id:
                card = row
    if card is None:
        return {"ok": False, "reason": f"no amik item with id {item_id!r}"}

    name = card.get("branch") or f"card/{item_id}"
    if git.is_repo(root) and git.branch_exists(root, name):
        # Step off it first. git will not delete the branch you are
        # standing on, and a halted card leaves the tree exactly there
        # — so refusing would mean the owner has to know to check out
        # the trunk before using a button that closes the card.
        #
        # The checkout is still the gate: an uncommitted change that
        # would be overwritten stops it, and that refusal is reported
        # rather than forced.
        here = git.current_branch(root)
        if here["ok"] and here["data"] == name:
            if not trunk:
                return {"ok": False, "reason":
                        "the tree is on " + name + " and there is no "
                        "trunk to return it to: set `trunk` in amik.toml"}
            # Lift the protection before the tree moves. A parked card
            # keeps `skip-worktree` on the shared paths, and git reports
            # such a path as outside the sparse checkout — so the
            # checkout below either refuses or leaves the branch's copy
            # standing on the trunk. Cleared wholesale rather than from
            # the declared list, because a bit stranded on a path that
            # has since left `shared` would otherwise be unreachable.
            git.clear_all_protection(root)
            left = git.run(root, "checkout", trunk)
            if not left["ok"]:
                return left
        dropped = git.drop_branch(root, name)
        if not dropped["ok"]:
            return dropped
    discard_prototype(root, item_id)
    if card.get("branch"):
        set_branch(root, item_id, "")
    return move(root, item_id, to_status, 0, by=by)


def _next_round(prose):
    """Which round of feedback this is. Counted from the headings
    already on the card, so a third attempt writes `Round 3` and
    nothing ever overwrites anything."""
    return len(re.findall(r"^## User Feedback: Round \d+\s*$", prose or "",
                          re.M)) + 1


def discard(root, item_id, trunk, feedback="", by=None):
    """The build is wrong; the idea is not. Throw it away and go again.

    Back to READY, because the button says Try Again and a button that
    says that and then does not is lying. The owner can drag it to
    To-Do if they want to think first.

    **Nothing on the card is reset.** Questions and their answers are
    the OWNER's work, not the attempt's, and clearing them would make
    the next agent re-ask what they already decided. The outcome is not
    cleared either — it APPENDS a line saying the attempt was
    discarded, which is the law every ruling here keeps, and which is
    the one thing that stops the next agent doing what the last one
    did.

    `feedback` is what the owner typed in the confirm, and it lands on
    the BODY as its own round — the body is the brief, and guidance for
    the next attempt belongs with the brief rather than in a section
    nobody wired up. Optional: a retry you already understand should
    not need an explanation typed to be allowed.

    Deleting the branch is unnaming, not destruction.
    """
    prose = None
    if str(feedback or "").strip():
        from . import board
        prose = board._card_prose(root, item_id)
    res = _close_and_clean(root, item_id, trunk, "ready", by=by)
    if not res.get("ok"):
        return res
    # Its own event. Throwing a build away and going again is the one
    # verdict with no column to drag to, so without this a history
    # shows a card in Review and then in Ready with nothing between.
    #
    # WHETHER there was feedback, never the feedback itself -- that
    # lands on the card, where the next agent reads it, and a log that
    # copied it would be a second writer for one piece of prose.
    log.note(root, item_id, "discard", by,
             feedback=True if str(feedback or "").strip() else None)
    if prose is not None:
        body = (prose or "").rstrip()
        # Under the body and ABOVE nothing in particular: the reader
        # splits sections by heading, so where this sits in the file
        # does not change what anything reads. Appending keeps every
        # round in the order they were given.
        body += "\n\n## User Feedback: Round {}\n\n{}\n".format(
            _next_round(prose), str(feedback).strip())
        update(root, item_id, {"body": body})
    record_outcome(
        root, item_id,
        "**This attempt was discarded.** Its branch and any prototype "
        "are gone and the card went back to Ready. What is written "
        "above is what the DISCARDED attempt did — read it as what not "
        "to repeat, not as what the card produced.",
        by="Amik")
    return res


def abandon(root, item_id, trunk, by=None):
    """The card is dropped, and its branch goes with it.

    The owner ruled the other way on 2026-09-14 — "keep the branch
    around because it's cheap" — and revised it on 2026-09-17: "we
    abandoned it, don't need it. And like you say we have 90 days."
    What changed is scale. Cheap per branch was measured when branching
    was rare; with every card branching it is the standard repository
    mess, where nobody dares delete a ref because nobody remembers
    which ones matter.
    """
    return _close_and_clean(root, item_id, trunk, "abandoned", by=by)


def delete(root, item_id, fingerprint=None, by=None):
    """File-level wrapper for delete_item, reader-shaped. Unlinks the
    card's prose too: leaving it would make a deleted card's text
    reappear under a later card that reused the id. An id the guard
    rejects can never have had a card file — the writer refuses to
    create one under such an id — so there is nothing to unlink, and a
    malformed id must not block the one thing this call is for."""
    res = _write(root, fingerprint,
                 lambda text: (delete_item(text, item_id), item_id))
    if res["ok"]:
        try:
            write_prose(root, item_id, "")
        except ValueError:
            pass
        log.note(root, item_id, "delete", by)
    return res


def _row_before(root, item_id, with_questions):
    """The row's toggles, and its unanswered count when prose is being
    written. `{}` when the board will not read — a log that cannot say
    what changed says nothing rather than guessing."""
    from . import board
    data = board.amik(root)
    if not data["ok"]:
        return {}
    row = next((c for col in data["data"]["columns"]
                for c in col["cards"] if c.get("id") == item_id), None)
    if row is None:
        return {}
    out = {"halt": row.get("halt"),
           "requires_prototype": row.get("requires_prototype")}
    if with_questions:
        out["unanswered"] = row.get("unanswered")
    return out


def _write(root, fingerprint, apply):
    from . import board
    path = os.path.join(root, "amik", "board.jsonl")
    if fingerprint is not None:
        if board.amik_fingerprint(root) != fingerprint:
            return {"ok": False, "reason": "stale"}
    try:
        with open(path) as f:
            text = f.read()
    except OSError as exc:
        return {"ok": False, "reason": f"unreadable: {exc.strerror}"}
    except ValueError as exc:                  # UnicodeDecodeError is one
        return {"ok": False, "reason": f"unreadable: {type(exc).__name__}"}
    try:
        new, item_id = apply(text)
    except ValueError as exc:
        return {"ok": False, "reason": str(exc)}
    try:
        # In place, never a rename: the instance root is somebody's
        # working directory, often open in an editor, and replacing the
        # inode under an open file is how that editor ends up writing
        # back what it read minutes ago.
        with open(path, "w") as f:
            f.write(new)
    except OSError as exc:
        return {"ok": False, "reason": f"unwritable: {exc.strerror}"}
    return {"ok": True, "data": {"id": item_id,
                                 "fingerprint":
                                 board.amik_fingerprint(root)}}
