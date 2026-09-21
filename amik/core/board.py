"""Amik's reader — the board, the queue, and everything derived from them.

`amik/board.jsonl` is the board: one JSON object per line. `amik/cards/
<id>.md` holds each card's prose. Nothing here writes; `edit` is the only
writer, and it is the only way in.

Stdlib only, and everything takes `root` — the instance directory holding
`amik/`. That is what lets this run inside a host application, inside a
test's temporary directory, or on its own.
"""
import json
import os
import re
import subprocess
import tomllib

from . import markdown as amik_markdown


def _ok(data):
    return {"ok": True, "data": data}


def _no(reason):
    return {"ok": False, "reason": reason}



# ── the board ────────────────────────────────────────────────────────
# amik/board.jsonl is the board: one JSON object per line. Nothing here
# reads outside the instance's amik/ folder, which is what lets Amik sit
# inside a project it knows nothing about.
#
# An instance without the file gets {ok: False} rather than an exception,
# and that is also the hiding mechanism: a project with no board 404s
# every route instead of rendering an empty one.

# The PM vocabulary, left to right, with whether the column arrives
# collapsed. Done, Someday and Won't Do are most of the file and none of
# them is work in flight, so they open on request rather than by default.
# A status not on this list still gets a column, appended after these — that
# is what kept the page rendering while a data migration ran ahead of it.
#
# `blocked` sits after `doing` by convention rather than by logic: a stall
# is not a stage. It is where a card waits on an answer, with its work
# stopped and the queue's not. `review` is built and green and waiting on
# the owner alone.
# Named so the finalise queue and the column table cannot drift apart --
# a status renamed in one but not the other would make the queue return
# [] forever, with nothing to say why.
AMIK_DONE = "done"

# Renamed from `wont_do` 2026-09-17. One word for one meaning: the card
# was dropped. `closed_as` went with the rename -- it carried
# `abandoned`, which this now says, and `retired`, whose evidence lives
# in the card's prose where every other ruling does.
AMIK_ABANDONED = "abandoned"

AMIK_COLUMNS = [
    ("inbox", "Inbox", False),
    ("todo", "To-Do", False),
    ("ready", "Ready", False),
    ("doing", "Doing", False),
    ("blocked", "Blocked", False),
    ("review", "Review", False),
    (AMIK_DONE, "Done", True),
    ("someday", "Someday", True),
    (AMIK_ABANDONED, "Abandoned", True),
]

# `ready` is a PULL, not a classification: the owner drags into it. Nothing
# here may fill it, or the column would only restate what To-Do says.

# The planning ladder, in order. It names what a row still needs before it
# can be built. An absent value is N/A — nothing owed. A rung is declared
# here even when no row wears one: the ladder is the vocabulary, not the
# current census.
AMIK_PLANNING = ["needs-brainstorm", "has-plan"]

# Rungs that contradict a claim of pullability. A row in `ready` still
# needing a brainstorm is a contradiction in the owner's own terms —
# surfaced on the card, never corrected.
AMIK_BLOCKING = ("needs-brainstorm",)

# A closed row needs no planning by definition, so a stale rung on one
# would print "not ready" against something that already shipped.
AMIK_CLOSED = (AMIK_DONE, AMIK_ABANDONED)

# The rungs that mean something is still OWED, and so hold a card back
# even from Ready. Everything else is takeable: dragging a card into
# Ready is the declaration, and `rank` is the priority. A confirming rung
# on top of the column would be two declarations for one intent.
#
# The same set as AMIK_BLOCKING, which the card's own contradiction chip
# already uses for these rungs — named separately for the queue's own
# vocabulary, but bound to the one tuple so the two cannot drift apart.
AMIK_BLOCKS_READY = AMIK_BLOCKING


def has_amik(root):
    """Whether this instance has a board at all — the one predicate that
    decides both the /amik route and whether the global quick-add
    exists. Existence, not a parse: it runs on EVERY page render, and it
    matches the reader's own failure mode, which is an OSError on open.

    A dev-tree file. Every ported instance answers False, and that is how
    the board stays out of the product rather than by remembering to."""
    return os.path.exists(os.path.join(root, "amik", "board.jsonl"))


# A card's `id` is hand-authored, so it is untrusted input to a path
# join. Anything but this shape reads nothing rather than reaching
# outside amik/cards/ — the same charset the board's own slugs use.
_CARD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _card_prose(root, item_id):
    """`amik/cards/<id>.md`, or "" when it is absent or unreadable.

    Prose lives in its own file so answering a question shows as three
    lines in `git diff` rather than as a replaced kilobyte of escaped
    JSON. Readers never raise: a bad byte costs one card its prose, not
    the whole page.
    """
    if not isinstance(item_id, str) or not _CARD_ID.match(item_id):
        return ""
    path = os.path.join(root, "amik", "cards", item_id + ".md")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""
    except ValueError:            # UnicodeDecodeError is one
        return ""


# The heading a card's questions live under. Matched exactly: `##
# questions` in lowercase is an ordinary prose heading, and matching it
# loosely would make one start blocking a card.
_QUESTIONS_HEADING = "## Questions"


def _card_questions(prose):
    """The `###` questions under `## Questions`, in document order.

    Each is {heading, answer, answered}. The answer is the prose beneath
    the heading, and an EMPTY section is an unanswered question — that
    one rule is the whole machine, so the work here is mostly about where
    it stops: a later `##` closes the section, and a `###` outside it is
    just a heading.

    Never raises. A card file is hand-edited markdown and the reader has
    to survive whatever is in it -- including a fenced code block that
    quotes a heading line, which is content, not structure.
    """
    if not isinstance(prose, str) or _QUESTIONS_HEADING not in prose:
        return []
    lines = prose.split("\n")
    inside, questions = False, []
    for i, stripped, fenced in amik_markdown.walk(prose):
        if not fenced and stripped == _QUESTIONS_HEADING:
            inside = True
            continue
        if inside and not fenced and stripped.startswith("## "):
            break                      # a sibling heading closes it
        if not inside:
            continue
        if not fenced and stripped.startswith("### "):
            questions.append({"heading": amik_markdown.heading_text(stripped, "### "),
                              "answer": []})
        elif questions:
            questions[-1]["answer"].append(lines[i])
    out = []
    for q in questions:
        # A leading blockquote is the ASKER's context, not the owner's
        # answer. Splitting here rather than at collection keeps `walk`
        # doing one job, and `answered` reads the remainder alone — the
        # whole reason the split exists is that context used to mark a
        # question answered.
        span = amik_markdown.context_span(q["answer"])
        context = "\n".join(q["answer"][:span]).strip()
        answer = "\n".join(q["answer"][span:]).strip()
        out.append({"heading": q["heading"], "context": context,
                    "answer": answer, "answered": bool(answer)})
    return out


_OUTCOME_HEADING = "## Outcome"


def _card_outcome(prose):
    """The prose under a card's `## Outcome`, or "".

    What the card PRODUCED, written as it leaves `doing`. A card can close
    with no commit at all — already built, or a design pass and no code —
    and for those the git log has nothing to say, so this is the only
    place the work is recorded.

    Same boundaries as `_card_questions`: a later `##` closes it, and a
    fenced block that quotes a heading line is content rather than
    structure. Never raises; a card file is hand-edited markdown.
    """
    if not isinstance(prose, str) or _OUTCOME_HEADING not in prose:
        return ""
    lines = prose.split("\n")
    inside, body = False, []
    for i, stripped, fenced in amik_markdown.walk(prose):
        if not fenced and stripped == _OUTCOME_HEADING:
            inside = True
            continue
        if inside and not fenced and stripped.startswith("## "):
            break
        if inside:
            body.append(lines[i])
    return "\n".join(body).strip()


_NOTIFY_ON = ("review", "blocked")


def _notify_on(value):
    """Which statuses a worked card must land in before anyone is told.

    Absent means `review` and `blocked` — the two columns that mean the
    loop stopped and is waiting on a person, where every other landing is
    a card that finished and can be read whenever. An explicit `[]` is
    silence, and it is how someone goes quiet without deleting the
    command they will want back.

    A value that is not a list of strings is a typo, and a typo falls back
    to the DEFAULT rather than to silence: the cheap direction of a
    mistake here is hearing about a card you did not need to hear about,
    and the expensive one is a board waiting on you in a column nothing
    announced. Statuses are lowercased, because the column names are and
    `["Review"]` is a reasonable thing to write.
    """
    if not isinstance(value, list):
        return list(_NOTIFY_ON)
    return [s.strip().lower() for s in value
            if isinstance(s, str) and s.strip()]


def _git(root, *args):
    """One read-only git command, or None.

    None means "could not answer" and covers every way that happens —
    not a checkout, git missing, the command refusing. Callers here are
    deciding what to DEFAULT to, and all three failures default the
    same way, so distinguishing them would be a distinction nothing
    reads.

    `stdin=DEVNULL` because a subprocess inheriting this process's stdin
    is how a CLI ends up waiting on a pipe that will never close.
    """
    import subprocess
    try:
        out = subprocess.run(["git", "--no-pager", "-C", str(root), *args],
                             capture_output=True, text=True, timeout=5,
                             stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def _detect_trunk(root):
    """`origin/HEAD`, then a local `main`, then a local `master`, then "".

    Ordered by how much each one KNOWS. `origin/HEAD` is the remote
    stating its own default and is worth more than a name that merely
    exists locally. `main` before `master`, because a repository
    carrying both has almost certainly renamed and left the old one
    behind.
    """
    out = _git(root, "symbolic-ref", "refs/remotes/origin/HEAD")
    if out and "/" in out:
        return out.rsplit("/", 1)[-1].strip()
    for name in ("main", "master"):
        if _git(root, "rev-parse", "--verify", "--quiet", name) is not None:
            return name
    return ""


def _shared(value):
    """A typo falls back to NOTHING shared rather than to a guess."""
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value
            if isinstance(v, str) and v.strip()]


def _tick(value):
    """Seconds between looks. Absent, or nonsense, is one.

    Floored at a quarter of a second rather than trusted: a zero or a
    negative here is a busy-wait pinning a core, and the cheap direction
    of that mistake is looking slightly less often than someone meant.
    """
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return 1.0
    return max(0.25, seconds)


def _declared(root):
    """The config file and the first gate, WITHOUT touching git.

    Split out of `amik_project` because capability does not need a
    trunk. `amik_project` detects one when it is undeclared, which is up
    to three git subprocesses, and the board reader now asks whether an
    agent could work this board on every render. Paying for a branch
    lookup to answer a question about a test command would put git on a
    path that polls.
    """
    path = os.path.join(root, "amik", "amik.toml")
    try:
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
    except OSError:
        return _no("no amik/amik.toml in this instance")
    except ValueError as exc:        # TOMLDecodeError is one
        return _no(f"unreadable: {type(exc).__name__}")
    verify = cfg.get("verify")
    if not isinstance(verify, str) or not verify.strip():
        return _no("amik.toml declares no verify command, so this project "
                   "cannot be agent-worked")
    return _ok(cfg)


def amik_project(root):
    """`amik/amik.toml` → what this project declares about being worked.

    `verify` has no default on purpose: a project that has not said what
    green means here cannot be agent-worked, and refusing is the honest
    failure. Guessing a test command is how a loop reports green on
    nothing.
    """
    declared = _declared(root)
    if not declared["ok"]:
        return declared
    cfg = declared["data"]
    verify = cfg["verify"]

    def _text(key):
        value = cfg.get(key)
        return value.strip() if isinstance(value, str) else ""

    return _ok({"verify": verify.strip(),
                # What the HOST project is called, for the one place a
                # board says whose it is. Optional, and empty when
                # undeclared: Amik will not invent a name from a
                # directory, because a guessed name in the top bar reads
                # exactly like a configured one.
                "name": _text("name"),
                "laws": _text("laws"),
                "branch": _text("branch"),
                # `is True`, not truthiness: a gate that a string can open
                # is not a gate, and this one decides whether an agent may
                # work the board unattended.
                "armed": cfg.get("armed") is True,
                # Stylesheets injected into a prototype's <head>, not
                # written into the file — which stylesheet a prototype
                # wears is a property of the project, not of the file.
                # Root-relative only: this list is injected verbatim as
                # an href, so a `javascript:` or absolute `http://` entry
                # is dropped here rather than trusted by every caller.
                "assets": [a for a in (cfg.get("prototypes") or {}).get(
                    "assets", []) if isinstance(a, str)
                    and a.startswith("/")],
                # The command that works a card. Amik names no vendor: it
                # writes the prompt to this command's STDIN, which every
                # CLI has and no two spell the same way in argv. A
                # project that wants a different agent changes one line.
                "agent": ((cfg.get("agent") or {}).get("command") or "").strip(),
                # What a card branches FROM and returns TO. Declared,
                # because it cannot be guessed: most repositories call
                # it `main`, some `master`, and an instance with no
                # remote has nothing to ask. EMPTY IS A REFUSAL at the
                # call site, never a default — branching from the wrong
                # base is silent and merges the wrong thing.
                "trunk": ((cfg.get("trunk") or "").strip()
                          or _detect_trunk(root)),
                # Paths a card's branch must not own. Amik does not know
                # what these are; it knows only that a branch may not
                # take them hostage. Absent means nothing is shared,
                # which is right for almost every repository — and that
                # inertness is what makes this portable.
                "shared": _shared((cfg.get("state") or {}).get("shared")),
                # Of those, the ones that change on their OWN. Watchers
                # and Amik write these on a schedule that has nothing to
                # do with any card, so a card is never blamed for them.
                #
                # A subset of `shared`, not a separate idea: both are
                # protected from a branch; only these are exempt from
                # the report. Absent means every shared path is a card's
                # doing, which is right for a project whose shared paths
                # are all content.
                "churn": _shared((cfg.get("state") or {}).get("churn")),
                # Run after a card is worked, with a one-line summary on
                # argv. Absent means silent — a tool that insists on
                # telling you things has to be told how.
                "notify": ((cfg.get("loop") or {}).get("notify") or "").strip(),
                # Which landings are worth being told about.
                "notify_on": _notify_on(
                    (cfg.get("loop") or {}).get("notify_on")),
                # A card's transcript is every file the agent read. Off
                # unless asked for, because a default that records that
                # is a default nobody inspected.
                "transcript": (cfg.get("loop") or {}).get(
                    "transcript") is True,
                # How many cards one run may work. 0 means no limit —
                # drain Ready. That is less reckless than it sounds: the
                # batch already stops on the first card that does not
                # close cleanly, so an unlimited run cannot spin on
                # errors, it can only keep working cards that are
                # succeeding. What it spends is tokens, and how many is
                # exactly how many cards were put in Ready.
                "ceiling": (cfg.get("loop") or {}).get("ceiling", 3),
                # Seconds between looks when a server is working the
                # board. One, matching the live feed's poll.
                #
                # Measured rather than reasoned about: a stat is 0.9
                # microseconds, so a second's interval is forty
                # millionths of one core and about seventy milliseconds
                # of CPU a day. There is nothing here to save, and a
                # card starting a second sooner is a card starting a
                # second sooner.
                #
                # Declarable anyway, because the right number differs by
                # machine — a poll is nothing on a box that is always on
                # and is one more thing keeping a laptop awake.
                "tick": _tick((cfg.get("loop") or {}).get("tick"))})


def amik_queue(root):
    """The Ready card an agent would take next, why not the blocked ones,
    and the priority queue behind the take.

    Read-only, and deliberately answerable by eye: the queue and the
    board must never disagree, so this derives everything from the same
    reader the page renders.

    Ready is the declaration — dragging a card there already said go, so
    every card is takeable except one still carrying a rung that says
    something is owed, or one holding an unanswered question — the chip
    that says the owner is blocking the card, and a queue that took it
    anyway would make that chip a lie. Those are `skipped` and named.
    Every other Ready card lands in exactly one of `take` (the first by
    rank) or `queued` (the rest, in rank order) — never both, and never
    neither, EXCEPT while a `halt` is in force (below), when eligible
    Ready cards are held back and land in neither.

    A `halt` is a gate that must survive the very act of clearing it: the
    owner drags a card to Review to have it looked at, and until they move
    it back out, that card's work may still be sitting unmerged on a
    branch — a foundation later cards cannot be built on. So the gate is
    driven by Review, not by Ready: a `halt` on a card SITTING IN REVIEW
    pauses the whole queue (`take` None, `queued` empty) for as long as
    it stays there, and lifts the moment the owner moves it anywhere
    else — not a verb the queue exposes, a fact it reads. `skipped` is
    still computed as normal while paused, so the owner can still see
    which Ready cards are separately held by their own rung or a
    question.

    A `halt` on a Ready card gates the cards behind it the same way, and
    it does so REGARDLESS of whether its own card is workable — a card
    can be both blocked by its rung and a barrier to what is ranked below
    it, and it is reported as both: present in `skipped` for its own
    reason, and named as `halted` because nothing behind it is queued.
    """
    board = amik(root)
    if not board["ok"]:
        return board
    columns = board["data"]["columns"]
    ready = next((c["cards"] for c in columns if c["status"] == "ready"), [])
    review = next((c["cards"] for c in columns if c["status"] == "review"), [])

    # A halted card already in Review gates the queue before Ready is
    # even walked: the owner sent it there, so its unmerged work still
    # stands between master and anything ranked below it. `review`'s
    # cards are already in the column's own rank order.
    stalled = next((c for c in review if c.get("halt")), None)
    halted = ({"id": stalled.get("id"), "title": stalled.get("title")}
              if stalled else None)
    paused = halted is not None

    take, queued, skipped = None, [], []
    for card in ready:                      # already ordered by rank
        rung = card.get("planning")
        eligible = True
        if rung in AMIK_BLOCKS_READY:
            skipped.append({"id": card.get("id"), "title": card.get("title"),
                            "reason": _amik_skip_reason(rung)})
            eligible = False
        else:
            # A rung is the owner's deliberate lever; an open question is
            # incidental to it, so a card owing both reports the rung —
            # the one the owner set on purpose.
            unanswered = card.get("unanswered") or 0
            if unanswered:
                skipped.append({"id": card.get("id"),
                                "title": card.get("title"),
                                "reason": _amik_question_skip_reason(
                                    unanswered)})
                eligible = False
        if eligible and not paused:
            if take is None:
                take = card
            else:
                queued.append({"id": card.get("id"),
                               "title": card.get("title")})
        # A halt gates what comes after it whether or not its OWN card
        # is workable — a rung-blocked card can still be the barrier the
        # owner meant it to be. Once set, later cards stop entering
        # `take`/`queued` even if they are themselves eligible.
        if halted is None and card.get("halt"):
            halted = {"id": card.get("id"), "title": card.get("title")}
            paused = True
    return _ok({"take": take, "queued": queued, "skipped": skipped,
                "halted": halted})


def amik_agent_may_close(card):
    """Whether an agent may move this card to Done itself.

    Done used to mean "I approve this merge", which is why it was the
    owner's alone. Where nothing is waiting to be merged it means only
    "this is finished" — not a decision, and not theirs to make twice.

    A halted card is the exception and the whole point of the halt: the
    owner asked to see it. A prototype forces a halt, and this checks it
    directly rather than trusting the UI to have done so — a predicate
    that depends on a form is a predicate a script can walk around.

    `ready` is untouched by any of this. It stays a pull.
    """
    if not isinstance(card, dict):
        return False
    # An outcome is required, and only non-empty is required of it: a
    # card closing with no commit — already built, or a design pass and
    # no code — has the git log saying nothing about it, and the terminal
    # where the agent said what happened dies with the session. One line
    # is a pass. The check is presence, never length or quality, because
    # a gate that judges prose is a gate that argues.
    if not str(card.get("outcome") or "").strip():
        return False
    return not (card.get("halt") or card.get("requires_prototype"))


def amik_finalise(root):
    """Done cards that still carry a branch — the work an agent owes.

    Done is the owner's signal, not an action: nothing here merges,
    deletes or checks anything. The branch FIELD is the record, and
    whether that branch still exists is the agent's to reconcile, because
    the tree this reads is not necessarily the tree the agent works in.

    Stays done-only on purpose, unlike `amik_prototypes` below, which
    also walks an abandoned card's column: a branch is kept regardless
    of how a card closed, so an agent is never handed "delete an
    unmerged branch" — a destructive verb on work nobody reviewed.
    """
    board = amik(root)
    if not board["ok"]:
        return board
    done = next((c["cards"] for c in board["data"]["columns"]
                 if c["status"] == AMIK_DONE), [])
    return _ok([{"id": c.get("id"), "title": c.get("title"),
                 "branch": _amik_branch(c.get("branch"))}
                for c in done if _amik_branch(c.get("branch"))])


def amik_prototypes(root):
    """Closed cards — done OR abandoned — that still have a prototype
    directory.

    A prototype's lifetime is its card's, and the ritual's last step has
    always been deleting it — the thing nobody remembers. Naming it here
    is what makes it rememberable; performing it is an agent's, for the
    same reason the face does not merge a branch.

    This walks BOTH closed columns, unlike `amik_finalise` below, which
    stays done-only. A design pass is finished the moment a card leaves
    play, ship or not, so its directory is owed a deletion either way —
    but an abandoned card's BRANCH is kept on purpose, so no agent is
    ever handed "delete an unmerged branch". Do not widen the two
    together; the asymmetry is the point.
    """
    board = amik(root)
    if not board["ok"]:
        return board
    closed = [c for col in board["data"]["columns"]
              if col["status"] in AMIK_CLOSED for c in col["cards"]]
    return _ok([{"id": c.get("id"), "title": c.get("title"),
                 "path": os.path.join("amik", "prototypes", c["id"])}
                for c in closed if c.get("has_prototype")])


def _amik_skip_reason(rung):
    """Why a Ready card is held by its planning rung. An unanswered
    question is a separate reason, named by `_amik_question_skip_reason`
    — this one only ever explains what the rung says is still owed, in
    the owner's own vocabulary. A rung reads "needs-<thing>", so the
    sentence wants the segment after the hyphen, not the verb."""
    return f"still needs a {rung.split('-', 1)[1]}"


def _amik_question_skip_reason(unanswered):
    """Why a Ready card with an open question is not takeable. The chip
    on the card already says the owner is blocking it by asking — a
    queue that took it anyway would make that chip a lie."""
    plural = "" if unanswered == 1 else "s"
    return f"still has {unanswered} open question{plural}"


# What a card MAY carry. Absent on the row means absent from the file;
# present-and-falsy is what a reader hands on, so the shape of a card is
# the same whatever that particular card happens to hold.
OPTIONAL = ("group", "docs", "commits", "raised_by", "branch",
            "requires_prototype", "halt", "planning",
            "created_at", "updated_at", "rank")


def amik_agent_capable(root):
    """COULD an agent ever work a card here? Not whether it will.

    Two gates, and both are declarations the project makes: a verify
    command, so there is something "green" means, and an agent command,
    so something has been told what works a card. Neither has a default,
    for the same reason -- guessing either is how a loop reports success
    on nothing.

    `armed` is deliberately NOT part of this. Pausing stops the loop
    taking anything new; a card already in Doing runs to the end, and
    the page promises exactly that when you pause it. So a paused board
    is still a capable one, and a card on it is still being worked.

    The reason is returned rather than a bare false, because "no" on its
    own sends somebody to the source to find out which gate is shut.
    """
    declared = _declared(root)
    if not declared["ok"]:
        return declared
    agent = (declared["data"].get("agent") or {}).get("command") or ""
    if not agent.strip():
        return _no("[agent] command is not declared, so nothing has "
                   "been told what works your cards")
    return _ok({})


def amik_will_work(root):
    """WILL the loop take the next Ready card? Capable, and armed.

    One ladder with `amik_agent_capable`, deliberately: the reason lived
    in the serve banner and again in `status`, worded almost the same,
    and a third copy on the page is how one board comes to give two
    accounts of itself.
    """
    capable = amik_agent_capable(root)
    if not capable["ok"]:
        return capable
    # `is True`, the same gate `amik_project` applies: a gate a string
    # can open is not a gate. Read here rather than through the full
    # project, for the reason `_declared` exists.
    if _declared(root)["data"].get("armed") is not True:
        return _no("armed is not true in amik.toml")
    # A TRUNK TO BRANCH FROM, when there is a repository at all.
    #
    # Detection reads the remote's own default, then a local `main`,
    # then `master`. A checkout sitting on some other branch with no
    # remote answers none of them, and every card then halts at
    # placement -- one at a time, each discovering it separately, after
    # the board had already said it would work them.
    #
    # Asked HERE rather than in `amik_agent_capable`, which is read on
    # every board render and must not shell out to git: detection is up
    # to three subprocesses. The banner asks this once, at boot, which
    # is the moment somebody is reading.
    #
    # A directory that is not a checkout is left alone. Amik works those
    # boards deliberately, losing branch placement rather than the
    # board, so there is nothing here to be wrong about.
    from . import git
    if git.is_repo(root) and not amik_project(root)["data"]["trunk"]:
        return _no("no trunk: no remote default, no `main`, no `master` — "
                   "set `trunk` in amik.toml")
    return _ok({})


def amik_verify(root):
    """The last verify AMIK ran here -- not a count of tests.

    Counting would mean recognising pytest from jest from cargo, which
    is the framework knowledge this tool has refused to carry since
    `verify` was given no default, and it would read zero on any project
    whose verify is a compound command. What Amik honestly knows is what
    its own run said.

    `ok` is None for "never run", which is NOT a failure and must not
    render as one: a board that has never landed a card has never run
    verify here. A corrupt file reads the same way -- it is a disposable
    cursor, and a page that 500s because one got truncated is a board
    lost to a cache file.
    """
    blank = {"ok": None, "at": "", "command": "", "tail": ""}
    try:
        with open(os.path.join(root, "amik", ".verify"),
                  encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return blank
    if not isinstance(rec, dict):
        return blank
    return {"ok": rec.get("ok") if isinstance(rec.get("ok"), bool) else None,
            "at": str(rec.get("at") or ""),
            "command": str(rec.get("command") or ""),
            "tail": str(rec.get("tail") or "")}


def amik(root):
    """amik/board.jsonl → the work board.

    Every row is work: `kind` was retired with the reference panes, so
    there is one structure here and not two. A malformed line is counted in
    `skipped`, never fatal: the board is hand-edited, and one bad line must
    not take the whole page down.
    """
    # Once for the whole board rather than once per row: it is a file
    # read, and every row gets the same answer.
    capable = amik_agent_capable(root)["ok"]
    path = os.path.join(root, "amik", "board.jsonl")
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return _no("no amik/board.jsonl in this instance")
    except ValueError as exc:
        # UnicodeDecodeError is a ValueError, and `except OSError` misses
        # it — a single stray byte would otherwise propagate out of a
        # module that contracts never to raise.
        return _no(f"unreadable: {type(exc).__name__}")

    rows, skipped = [], 0
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        # `status` and `title` must be strings. status keys the columns and
        # the move route builds a set of them, where an unhashable value
        # would 500 the POST; title is rendered through html.escape, which
        # None has no method for. Both would take the whole page down, and
        # a skipped line is counted where the page can report it.
        if not isinstance(row, dict) or not isinstance(row.get("status"), str) \
                or not row["status"] or not isinstance(row.get("title"), str):
            skipped += 1
            continue
        # Prose comes from the card file and nowhere else. A line still
        # carrying `body` is a line the migration missed, and honouring
        # it would let a stale copy win somewhere.
        row["body"] = _card_prose(root, row.get("id"))
        # Derived from the prose, never stored: a question is a heading
        # the owner answers underneath, so the card file is the only
        # place either half can live.
        row["questions"] = _card_questions(row["body"])
        row["unanswered"] = sum(1 for q in row["questions"]
                                if not q["answered"])
        row["duplicate_question"] = _amik_duplicate_question(row["questions"])
        row["outcome"] = _card_outcome(row["body"])
        # The card's own prose, without the sections that have tabs of
        # their own. This is what the modal RENDERS while a card is being
        # read and what its editor holds while one is being written --
        # one boundary, shared with the writer that puts an edited body
        # back, so a save cannot splice over what the page displayed.
        row["overview"] = amik_markdown.split_promoted(row["body"])[0].strip()
        # `doing` is the agent's own column: the owner's pull is `ready`
        # and an agent moves a card here as it starts, so the column is
        # the signal. A second field saying the same thing would be one
        # more thing that can be left true after a crash.
        # AND the project has to be one an agent could work. A board
        # with nothing declared is a manual board -- the shipped config
        # promises that in as many words -- and a card dragged into
        # Doing there is held by a person. "An agent is working this
        # card", with a spinner, is then simply false.
        #
        # Capable rather than armed, and the difference is the point:
        # pausing stops the loop taking anything NEW, so a card already
        # running must keep saying so.
        row["working"] = (row.get("status") == "doing") and capable
        row["question_flag"], row["question_flag_label"] = \
            _amik_question_mismatch(row)
        # File order, kept as the last tiebreaker in `_amik_sort_key` so a
        # column of rows with no rank still comes out in a stable order.
        # It is not an address: a card is addressed by `id`, because `n`
        # shifts for every row after a delete.
        row["n"] = len(rows)
        row["created_at"] = _amik_when(row.get("created_at"))
        row["updated_at"] = _amik_when(row.get("updated_at"))
        row["planning_chip"] = _amik_planning_chip(row)
        row["blocking"] = row["planning_chip"] in AMIK_BLOCKING
        row["conflict"], row["conflict_label"] = _amik_conflict(row)
        row["branch"] = _amik_branch(row.get("branch"))
        # Derived from the directory existing, never stored, so the board
        # cannot disagree with the disk.
        row["has_prototype"] = bool(row.get("id")) and os.path.isdir(
            os.path.join(root, "amik", "prototypes", row["id"]))
        # Every optional key present, falsy when unset. A row carries only
        # what it actually holds, so without this a renderer has to GUESS
        # which keys exist — and a template engine that answers a missing
        # key with "falsy" makes a typo indistinguishable from an absent
        # field. Filled here, in the one reader, so nothing downstream
        # keeps its own idea of a card's shape.
        for key in OPTIONAL:
            row.setdefault(key, None)
        rows.append(row)

    known = [s for s, _, _ in AMIK_COLUMNS]
    extra = []
    for row in rows:
        s = row["status"]
        if s not in known and s not in extra:
            extra.append(s)
    order = AMIK_COLUMNS + [
        (s, str(s).replace("_", " ").title(), False) for s in extra]

    columns = []
    for status, label, collapsed in order:
        cards = sorted((r for r in rows if r["status"] == status),
                       key=_amik_sort_key)
        # The column's label, carried on the card. The modal shows a
        # status chip and the label it shows is the column's own — a
        # second table of them would be a second place to rename one.
        for card in cards:
            card["status_label"] = label
        columns.append({"status": status, "label": label,
                        "collapsed": collapsed and bool(cards),
                        "count": len(cards), "cards": cards})

    # Derived, never a hard-coded list: a new area shows up the moment a
    # row uses it, and a typo never becomes a permanent suggestion.
    groups = sorted({r["group"] for r in rows
                     if isinstance(r.get("group"), str) and r["group"]})

    return _ok({"columns": columns, "groups": groups,
                "total": len(rows), "skipped": skipped,
                "fingerprint": amik_fingerprint(root)})


def _amik_when(value):
    """A bare date renders as an EMPTY age — time_ago needs a time
    component, by design and with tests — so date-only values are
    normalised on read. Midday, not midnight: these dates are day-accurate
    only (created_at was inferred from git history), and midday is the
    reading that keeps the error under twelve hours either way.

    A host application may well need the same two lines for the same
    reason on its own timestamps. They stay separate because that is the
    higher-level module — readers.py must not import it — and a lazy
    import in both directions would be worse than two lines.
    """
    v = str(value or "").strip()
    return (v + "T12:00:00") if len(v) == 10 and "T" not in v else v


def _amik_planning_chip(row):
    """The rung to show on the card, or "" for none. Only a declared rung
    counts — a typo'd value would otherwise print as a state of the ladder
    that does not exist. A closed row shows nothing whatever it carries: a
    rung left on something that already shipped is stale by definition."""
    if row.get("status") in AMIK_CLOSED:
        return ""
    rung = row.get("planning")
    return rung if rung in AMIK_PLANNING else ""


def _amik_branch(value):
    """Whether a row's `branch` counts as one, and what it is when it
    does -- the one predicate the card's chip and the finalise queue both
    go through, so a whitespace-only string or a non-string value (a
    hand-edited `true`) cannot render a chip the queue would never list.
    Returns the stripped name, or "" for anything that does not qualify,
    which is falsy either way a caller uses it.
    """
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _amik_conflict(row):
    """(sentence, short label) for a claim the row's own fields contradict.
    Two strings because a pill cannot carry a sentence: the label is the
    chip, the sentence is its tooltip and the modal's callout. Surfaced,
    never corrected — the board is hand-edited and which half is wrong is
    the owner's call.

    A closed row is never asked: it owes nothing, and a rung left on
    something that already shipped is stale rather than contradictory.
    """
    status, rung = row.get("status"), row.get("planning")
    if status in AMIK_CLOSED:
        return ("", "")
    if status == "ready" and rung in AMIK_BLOCKING:
        # A rung reads "needs-<thing>" — the sentence wants the thing, not
        # the verb, so it takes the segment after the hyphen.
        return (f"Marked ready but still needs a {rung.split('-', 1)[1]}.",
                "ready but blocked")
    if rung == "has-plan" and not row.get("docs"):
        # The rung's whole value is that it names a document the build can
        # read. Without one it is a claim about a plan nobody can open.
        return ("Says a plan exists but names no document.",
                "plan not named")
    return ("", "")


def _amik_question_mismatch(row):
    """(sentence, short label) when a card's column and its prose
    disagree about whether it is waiting on an answer.

    A SEPARATE reporter rather than another branch of `_amik_conflict`:
    that one returns a single pair and its branches cannot co-occur, but
    a question mismatch can happen alongside either of them, and folding
    it in would let the older disagreement hide this one.

    It reports and stops. An owner can block a card for a reason that
    appears nowhere in its prose — a person, a vendor, an upstream
    dependency — so that card is correctly blocked with nothing
    unanswered, and the chip says only that the two do not agree.
    """
    status = row.get("status")
    if status in AMIK_CLOSED:
        return ("", "")
    unanswered = row.get("unanswered") or 0
    if unanswered and status != "blocked":
        return ("Has a question waiting on an answer.", "question waiting")
    if status == "blocked" and not unanswered:
        return ("In Blocked with no question waiting.", "blocked, no question")
    return ("", "")


def _amik_duplicate_question(questions):
    """Whether two `### ` questions under `## Questions` share a heading.

    Surfaced, never corrected: the writer targets a question by its
    heading, so two sharing one are ambiguous to every writer that
    touches them, and which was meant is the owner's call, not the
    machine's — the board is hand-edited and the door cannot catch what
    the owner types.
    """
    headings = [q["heading"] for q in questions]
    return len(set(headings)) != len(headings)


def _amik_sort_key(row):
    """`rank` orders a column, 1 at the top — the one sort rule for any
    view of this file. A row with no rank sorts after every ranked one, in
    file order: the board is hand-edited, so a row can arrive before its
    rank does."""
    rank = row.get("rank")
    if isinstance(rank, bool) or not isinstance(rank, (int, float)):
        return (1, 0, row["n"])
    return (0, rank, row["n"])


def amik_fingerprint(root):
    """Identifies the bytes of `board.jsonl` only — card STATE, not the
    prose files under `amik/cards/`. A write through this file is refused
    once the board has moved on since the page was rendered; a hand edit
    to a card's prose file moves nothing this checks, so a modal save
    from a page rendered before that edit overwrites it with no stale
    refusal. Not a hash: this file is written by hand between page loads,
    where mtime and size already disagree."""
    path = os.path.join(root, "amik", "board.jsonl")
    try:
        st = os.stat(path)
    except OSError:
        return ""
    return f"{st.st_mtime_ns}/{st.st_size}"


def git_status(root, n=7):
    """The tree's branch and its newest commit subjects.

    Two shell-outs, bounded and read-only. A directory that is not a
    checkout is a refusal, not an exception: a ported instance may not be
    one and the board still has to render.

    `--no-pager` and an explicit `-C` rather than a chdir: this runs under
    a web request, and a process-wide cwd change is not something a
    reader may do to its own server.
    """
    import subprocess

    def run(*args):
        return subprocess.run(["git", "--no-pager", "-C", str(root), *args],
                              capture_output=True, text=True, timeout=5,
                              stdin=subprocess.DEVNULL)
    try:
        head = run("rev-parse", "--abbrev-ref", "HEAD")
        if head.returncode != 0:
            return _no("not a git checkout")
        log = run("log", f"-{int(n)}", "--format=%h\t%s")
        if log.returncode != 0:
            return _no("no commits yet")
    except (OSError, subprocess.SubprocessError) as exc:
        return _no(f"git unavailable: {type(exc).__name__}")
    commits = []
    for line in log.stdout.splitlines():
        sha, _, subject = line.partition("\t")
        if sha:
            commits.append({"sha": sha, "subject": subject})
    return _ok({"branch": head.stdout.strip(), "commits": commits})
