"""`handle()` — Amik's entire public surface.

    handle(method, path, query, body, root, base="") -> (status, headers, body)

No framework, no globals, no I/O outside the instance's `amik/` folder.
That is what makes embedding a ten-line adapter in any stack rather than
a port: a host hands over four strings and gets three back.

Routes are resource-named. The resource is a card:

    GET    /                       the board
    GET    /events                 the change feed, as Server-Sent Events
    PATCH  /project                arm or disarm the loop
    POST   /cards                  create
    GET    /cards/{id}             one card's details, for the modal
    PATCH  /cards/{id}             update fields, body, answers
    DELETE /cards/{id}             destroy
    PATCH  /cards/{id}/position    move — status and rank
    DELETE /cards/{id}/work        discard the build, keep the card
    GET    /cards/{id}/prototype   a card's design pass
    GET    /static/{file}          Amik's own assets

**Position is a nested resource, not a field on the card.** `move` and
`update` are separate writers on purpose — status and rank belong to the
drag and nothing else — so folding position into the card's PATCH would
merge two doors the design keeps apart.
"""
import json
import mimetypes
import os
import posixpath
import re
import urllib.parse

from ..core import board, config, edit
from . import render, watch

JSON = {"Content-Type": "application/json; charset=utf-8"}
HTML = {"Content-Type": "text/html; charset=utf-8"}

_CARD = re.compile(r"^/cards/([A-Za-z0-9][A-Za-z0-9._-]*)(/[a-z]+)?$")

# Every route, in one place. The dispatcher below is a chain of ifs
# because it is short and reads better that way — but the SURFACE has to
# be enumerable, or a test cannot walk it and a gate can go unchecked on
# one route while the others are covered. Two tests bind this list to the
# dispatcher: every entry must answer on a real board, and every entry
# must 404 on an instance that has none.
ROUTES = (
    ("GET", "/"),
    ("GET", "/events"),
    ("PATCH", "/project"),
    ("POST", "/cards"),
    ("GET", "/cards/{id}"),
    ("PATCH", "/cards/{id}"),
    ("DELETE", "/cards/{id}"),
    ("PATCH", "/cards/{id}/position"),
    ("DELETE", "/cards/{id}/work"),
    ("GET", "/cards/{id}/prototype"),
    ("GET", "/static/{file}"),
)


def _json(status, payload):
    return status, dict(JSON), json.dumps(payload).encode("utf-8")


def _err(status, reason):
    return _json(status, {"detail": reason})


def _result(res):
    """A door's answer, as HTTP. Stale is not an error in the machinery —
    the file simply moved on, and the page has to catch up before writing
    again — so it is a 409 and says so."""
    if res["ok"]:
        return _json(200, res["data"])
    return _err(409 if res["reason"] == "stale" else 400, res["reason"])


def _form(body):
    raw = body.decode("utf-8") if isinstance(body, bytes) else (body or "")
    out = {}
    for key, vals in urllib.parse.parse_qs(raw, keep_blank_values=True).items():
        out[key] = vals[-1]
    return out


def _static(name, base):
    """Amik's assets. The path is rebuilt from its own basename rather
    than trusted, so nothing outside this folder is reachable however the
    request was spelled."""
    safe = posixpath.normpath("/" + name).lstrip("/")
    if "/" in safe or not safe:
        return _err(404, "not found")
    path = os.path.join(render.STATIC, safe)
    try:
        with open(path, "rb") as f:
            blob = f.read()
    except OSError:
        return _err(404, "not found")
    kind = mimetypes.guess_type(safe)[0] or "application/octet-stream"
    return 200, {"Content-Type": kind, "Cache-Control": "max-age=60"}, blob


def _prototype(root, card_id, base):
    project = board.amik_project(root)
    if not project["ok"]:
        return _err(404, "not found")
    path = os.path.join(root, "amik", "prototypes", card_id, "index.html")
    try:
        with open(path, encoding="utf-8") as f:
            markup = f.read()
    except (OSError, ValueError):
        return _err(404, "not found")
    # The reader already dropped anything that is not a root-relative
    # path, so every entry here is trusted to become an href. Embedded
    # these resolve against the HOST, which is the point: a prototype
    # should look like the application it is prototyping.
    links = "".join(
        '<link rel="stylesheet" href="{}">'.format(a)
        for a in (project["data"].get("assets") or []))
    if links and "</head>" in markup:
        markup = markup.replace("</head>", links + "</head>", 1)
    elif links:
        markup = links + markup
    return 200, dict(HTML), markup.encode("utf-8")


def _answers(raw, body_text):
    """Answers arrive as a JSON list and are spliced into the card's
    prose. They need a body to splice INTO — a save that carried answers
    and no body would be writing into prose it never read."""
    try:
        items = json.loads(raw)
    except ValueError:
        raise ValueError("answers must be JSON")
    if not isinstance(items, list):
        raise ValueError("answers must be a list")
    if body_text is None:
        raise ValueError("answers need a body")
    out = body_text
    for item in items:
        if not isinstance(item, dict) or "heading" not in item \
                or "text" not in item:
            raise ValueError("each answer needs a heading and text")
        out = edit.replace_section_body(out, item["heading"], item["text"])
    return out


def handle(method, path, query=None, body=b"", root=".", base=""):
    method = (method or "GET").upper()
    prefix = (base or "").rstrip("/")
    if prefix and path.startswith(prefix):
        path = path[len(prefix):] or "/"
    path = path or "/"

    if method == "GET" and path == "/":
        data = board.amik(root)
        if not data["ok"]:
            return _err(404, data["reason"])
        page = render.board_page(
            data["data"], base=prefix, rungs=edit.RUNGS,
            columns=board.AMIK_COLUMNS, git=board.git_status(root),
            project=board.amik_project(root),
            # Why nothing will work these cards, if nothing will. The
            # same sentence the serve banner prints, from the same
            # reader -- a log nobody has open was the only place this
            # was said, and the page is where somebody is dragging.
            capable=board.amik_agent_capable(root),
            verified=board.amik_verify(root))
        return 200, dict(HTML), page.encode("utf-8")

    if method == "GET" and path == "/events":
        if not board.has_amik(root):
            return _err(404, "not found")
        # A generator body. Both hosts stream it rather than buffering,
        # and neither sends a Content-Length for it.
        return 200, {"Content-Type": "text/event-stream; charset=utf-8",
                     "Cache-Control": "no-cache",
                     # Named for the one proxy that buffers SSE by
                     # default and turns a live feed into a long silence.
                     "X-Accel-Buffering": "no"}, watch.stream(root)

    if method == "PATCH" and path == "/project":
        # Gated on the PROJECT, not the board: `armed` lives in amik.toml
        # and an instance that declares nothing has no gate to move.
        project = board.amik_project(root)
        if not project["ok"]:
            return _err(404, project["reason"])
        want = _form(body).get("armed")
        if want not in ("true", "false"):
            return _err(400, "armed must be true or false")
        res = config.set_armed(root, want == "true")
        if not res["ok"]:
            return _err(400, res["reason"])
        # The count comes back from a FRESH read rather than from the
        # page, because it is what the answer promises will finish: a
        # card that entered Doing since the page loaded is still a card
        # the loop is going to carry to the end.
        return _json(200, {"armed": res["data"]["armed"],
                           "working": _working(root)})

    if method == "GET" and path.startswith("/static/"):
        return _static(path[len("/static/"):], prefix)

    if method == "POST" and path == "/cards":
        if not board.has_amik(root):
            return _err(404, "not found")
        form = _form(body)
        title = (form.get("title") or "").strip()
        if not title:
            return _err(400, "a card needs a title")
        # An empty fingerprint means "do not check" — the quick-add is
        # reachable from pages that never rendered the board and so have
        # nothing to quote back.
        # `by="user"` on every write from here. The server and the loop
        # share a process, so an environment variable would race the
        # ticker and attribute a drag to Amik. The two callers that
        # cannot be confused say who they are outright.
        return _result(edit.create(root, title,
                                   form.get("fingerprint") or None,
                                   by="user"))

    m = _CARD.match(path)
    if m:
        card_id, tail = m.group(1), m.group(2)
        # A prototype gates on the PROJECT declaring itself, not on the
        # board: `prototypes/` and `board.jsonl` are separate files and a
        # design pass can be looked at without one.
        if method == "GET" and tail == "/prototype":
            return _prototype(root, card_id, prefix)
        # A WRITE with no board is not a bad request — it is an instance
        # that has no board, which is every instance but the ones being
        # worked. 404 like the page does, rather than letting a door
        # answer "no such card" and imply there was a board to look in.
        if not board.has_amik(root):
            return _err(404, "not found")
        # The card as a RESOURCE. The page ships tiles and fetches this
        # when a modal opens, and the live refresh reads the same route —
        # one path for both, rather than two that can drift.
        if method == "GET" and not tail:
            data = board.amik(root)
            if not data["ok"]:
                return _err(404, data["reason"])
            card = _find(data["data"], card_id)
            if card is None:
                return _err(404, "no such card")
            return 200, dict(HTML), render.card_data(
                card, base=prefix).encode("utf-8")
        if method == "PATCH" and tail == "/position":
            form = _form(body)
            try:
                index = int(form.get("to_index", ""))
            except ValueError:
                return _err(400, "a position needs an index")
            status = form.get("to_status", "")
            if status not in [c[0] for c in board.AMIK_COLUMNS]:
                return _err(400, "unknown status")
            # Every close deletes the branch, and a card reaches
            # `abandoned` by being DRAGGED there far more often than by
            # any button. The cleanup belongs to the destination rather
            # than to one route into it, or a dropped card keeps its ref
            # whenever the owner used the gesture instead of the verb.
            if status == board.AMIK_ABANDONED:
                project = board.amik_project(root)
                trunk = project["data"]["trunk"] if project["ok"] else ""
                return _result(edit.abandon(root, card_id, trunk,
                                            by="user"))
            return _result(edit.move(root, card_id, status, index,
                                     form.get("fingerprint") or None,
                                     by="user"))
        # Discarding the WORK, not the card: the build is wrong and the
        # idea is not, so the branch and the prototype go and the card
        # returns to Ready. DELETE on the work, because that is what is
        # being removed — the card survives.
        if method == "DELETE" and tail == "/work":
            project = board.amik_project(root)
            trunk = project["data"]["trunk"] if project["ok"] else ""
            return _result(edit.discard(root, card_id, trunk,
                                        feedback=_form(body).get(
                                            "feedback", ""), by="user"))
        if tail:
            return _err(404, "not found")
        if method == "DELETE":
            form = _form(body)
            return _result(edit.delete(root, card_id,
                                       form.get("fingerprint") or None,
                                       by="user"))
        if method == "PATCH":
            form = _form(body)
            fields = {k: form[k] for k in edit.EDITABLE if k in form}
            # The modal edits a card's BODY, not its whole file: the
            # sections with tabs of their own are not editable there. The
            # door puts the body back into the prose it came out of, so
            # the page never carries its own copy of where that boundary
            # is.
            if "overview" in form:
                fields["body"] = edit.replace_overview(
                    board._card_prose(root, card_id), form["overview"])
            if "answers" in form:
                try:
                    fields["body"] = _answers(form["answers"],
                                              fields.get("body"))
                except ValueError as exc:
                    return _err(400, str(exc))
            res = edit.update(root, card_id, fields,
                              form.get("fingerprint") or None, by="user")
            if not res["ok"]:
                return _result(res)
            out = dict(res["data"])
            if "answers" in form:
                out["fingerprint"] = _unblock(root, card_id,
                                              out.get("fingerprint"))
            # After the move, never before: a card's question chip is read
            # against its COLUMN, so chips derived first would describe
            # the column it just left.
            out.update(_painted(root, card_id, prefix))
            return _json(200, out)

    return _err(404, "not found")


def _find(data, card_id):
    """One card out of the rendered board, or None. The board is already
    grouped into columns, and the reader is the only thing that knows how
    to derive a card — so this walks its output rather than re-reading
    the file into a second shape."""
    for column in data["columns"]:
        for card in column["cards"]:
            if card.get("id") == card_id:
                return card
    return None


def _working(root):
    """How many cards are being worked right now.

    `doing` is the answer and not the loop's lock file: the column is
    what the board shows and what a person is looking at, and a card
    worked by hand holds no lock at all.
    """
    data = board.amik(root)
    if not data["ok"]:
        return 0
    return next((c["count"] for c in data["data"]["columns"]
                 if c["status"] == "doing"), 0)


def _unblock(root, card_id, fingerprint):
    """A `blocked` card whose last question just got an answer goes back
    to Ready. Returns the fingerprint to hand the page — the new one when
    the card moved, the one passed in when it did not.

    This is not the board inferring a pull on the owner's behalf, which
    nothing here may do. Answering is the owner's own gesture, made in
    the box the question put in front of them, and the drag back to
    Ready was the second half of it — a second half easily forgotten,
    leaving a card sitting in Blocked with nothing waiting on it, which
    is a contradiction the board then has to draw a chip for.

    Three conditions, and all three are about the answer having actually
    finished something: the card is IN `blocked`, it carries questions at
    all, and none is left unanswered. Answering one of two has unblocked
    nothing.

    Bottom of Ready, which is where the modal's own status dropdown lands
    a card. This is that move made for the owner rather than a new kind
    of move, and the top would re-prioritise a queue nobody asked it to
    touch.

    `move` does it, because status and rank have one writer.
    """
    data = board.amik(root)
    if not data["ok"]:
        return fingerprint
    card, ready = None, 0
    for column in data["data"]["columns"]:
        if column["status"] == "ready":
            ready = column["count"]
        if card is None:
            card = next((c for c in column["cards"]
                         if c.get("id") == card_id), None)
    if card is None or card.get("status") != "blocked":
        return fingerprint
    if not card.get("questions") or card.get("unanswered"):
        return fingerprint
    res = edit.move(root, card_id, "ready", ready, fingerprint)
    return res["data"]["fingerprint"] if res["ok"] else fingerprint


def _painted(root, card_id, base):
    """What the page repaints after a save: the tile's chips, and the
    modal's own view of the card.

    All of it is derived state the page cannot recompute — the waiting
    count, the conflict, the body minus its promoted sections — so it
    comes back rendered, from the same reader that drew it the first
    time. One lookup for both, because two would be two reads of the
    board answering about one card.
    """
    data = board.amik(root)
    card = _find(data["data"], card_id) if data["ok"] else None
    if card is None:
        return {"chips": "", "view": ""}
    return {"chips": render.chips(card, base=base),
            "view": render.card_view(card, base=base)}
