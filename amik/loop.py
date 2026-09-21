"""The loop that works the board.

Cheapest check first, and nothing paid runs until every free one has
passed. That ordering is the whole design: a timer that wakes a model to
learn there is no work costs real money for an answer a file's mtime
could have given. The rule is not "never a timer" — it is never wake a
PAID step on one.

    armed?  →  board changed?  →  is there a take?  →  spawn

Steps one to three are free. Only the fourth costs anything.
"""
import itertools
import json
import os
import shlex
import subprocess
import sys
import threading
import time

from .core import board, edit, git, log

LOCK = "amik/.lock"
SEEN = "amik/.seen"


def _path(root, rel):
    return os.path.join(root, rel)


# ── the gates ────────────────────────────────────────────────────────


def armed(root):
    """Re-read EVERY tick, never cached at start.

    Cached, disarming means finding and restarting a daemon at the moment
    someone already wants it stopped. Re-read, it is a one-line edit that
    takes effect on the next card. The agent command is read the same way
    and for the same reason: switching agents mid-week should not need a
    process managed.
    """
    project = board.amik_project(root)
    return bool(project["ok"] and project["data"]["armed"])


def changed(root):
    """Has the board moved since the last look? Free — one stat.

    The board file IS the doorbell. A card entering Ready is a write to
    it, so there is nothing to poll that the filesystem does not already
    know.
    """
    path = _path(root, "amik/board.jsonl")
    try:
        stamp = "{}/{}".format(os.stat(path).st_mtime_ns,
                               os.stat(path).st_size)
    except OSError:
        return False
    try:
        with open(_path(root, SEEN), encoding="utf-8") as f:
            was = f.read().strip()
    except OSError:
        was = ""
    return stamp != was


def remember(root):
    try:
        with open(_path(root, SEEN), "w", encoding="utf-8") as f:
            f.write("{}/{}".format(
                os.stat(_path(root, "amik/board.jsonl")).st_mtime_ns,
                os.stat(_path(root, "amik/board.jsonl")).st_size))
    except OSError:
        pass


# ── one card at a time ───────────────────────────────────────────────


class Busy(Exception):
    """Another worker holds the lock."""


class Lock:
    """One card at a time, enforced by a file.

    The tree is a shared working directory: two agents editing it at once
    is a half-applied merge waiting to happen, and this repository has
    already paid for one of those. A lock is the whole concurrency story.

    A dead holder's lock is reclaimed — a crashed run must not wedge the
    board forever — and liveness is checked by signalling the pid rather
    than by a timeout, because a card can legitimately take an hour.
    """

    def __init__(self, root, card_id):
        self.path = _path(root, LOCK)
        self.card_id = card_id

    def _holder(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    @staticmethod
    def _alive(pid):
        try:
            os.kill(int(pid), 0)
        except (OSError, TypeError, ValueError):
            return False
        return True

    def __enter__(self):
        held = self._holder()
        if held and self._alive(held.get("pid")):
            raise Busy("card {!r} is already being worked by pid {}".format(
                held.get("card"), held.get("pid")))
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "card": self.card_id,
                       "since": time.strftime("%Y-%m-%dT%H:%M:%S")}, f)
        return self

    def __exit__(self, *exc):
        try:
            os.unlink(self.path)
        except OSError:
            pass
        return False


# ── what the agent is told ───────────────────────────────────────────


def _own_laws():
    """Amik's own CLAUDE.md, read from beside the package.

    Absent is survivable and silent: a checkout that has lost it still
    works its cards, with the project's own rules and nothing else.
    Refusing would make a missing documentation file stop the board.
    """
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for candidate in (os.path.join(here, "CLAUDE.md"),
                      os.path.join(os.path.dirname(here), "CLAUDE.md")):
        try:
            with open(candidate, encoding="utf-8") as f:
                return f.read()
        except OSError:
            continue
    return ""


def _door(root):
    """The write door, named so the agent can actually run it.

    `sys.executable -m amik` rather than the bare `amik` command,
    because a loop started from a virtualenv hands its child a PATH that
    may not contain that console script at all -- and a command an agent
    cannot run is the same as no door, which is the state this whole
    thing was written to fix.

    `--root` is absolute for the same reason: an agent that changed
    directory mid-card would otherwise write to a board that is not the
    one it was given.
    """
    return "{} -m amik --root {}".format(
        sys.executable, shlex.quote(os.path.abspath(root)))


def prompt(root, card, project):
    """One card's brief. The card, the laws, the procedure — not the
    project.

    A persistent session accretes the whole repository and pays for it on
    every tick. A fresh invocation per card starts clean and reads only
    what that card needs, which is the difference between a loop that
    gets more expensive the longer it runs and one that does not.
    """
    # AMIK'S OWN laws come first, and no project has to ask for them.
    # They are about the BOARD -- what a column means, when a card may
    # close, how to ask a question -- and they ship with the package, so
    # making every project copy them into its own file would be Amik
    # asking to be told something it already knows. It would also mean
    # every copy drifting from the version the code enforces.
    #
    # `project["laws"]` is for the PROJECT's rules, which only the
    # project has. Both, in that order, and either may be missing.
    laws = _own_laws()
    if project["laws"]:
        try:
            with open(_path(root, project["laws"]), encoding="utf-8") as f:
                theirs = f.read()
            laws = (laws + "\n\n---\n\n" + theirs) if laws else theirs
        except OSError:
            pass
    return "\n".join([
        "You are working one card on a board. Do this card and stop.",
        "",
        "## The card",
        "",
        "Title: " + str(card.get("title") or ""),
        "Id: " + str(card.get("id") or ""),
        "",
        str(card.get("body") or "(no description)"),
        "",
        "## How this project is verified",
        "",
        project["verify"],
        "",
        "It must pass before you close the card. If it fails and you",
        "cannot fix it, halt the card and leave it in `review` naming",
        "what failed. Never merge red.",
        "",
        "## How to write to the board",
        "",
        "This exact command, which is the door. Do not edit",
        "`board.jsonl` or a card file by hand, and do not expect to",
        "import anything: this project may not be written in Python at",
        "all, and the module the laws name is not on your path.",
        "",
        "  " + _door(root) + " move <card-id> <column> [--index N]",
        "  " + _door(root) + " outcome <card-id> \"what happened\" "
        "--model \"<your model>\"",
        "  " + _door(root) + " ask <card-id> \"A question?\" "
        "--context \"what you already know\"",
        "  " + _door(root) + " halt <card-id> [--off]",
        "  " + _door(root) + " plan <card-id> --doc <path>   "
        "# or --needs-brainstorm",
        "  " + _door(root) + " status        # the queue, changing nothing",
        "  " + _door(root) + " log --card <card-id>",
        "",
        "Each one prints what it did, or refuses and says why. A refusal",
        "is an answer: read it and act on it rather than working around",
        "it.",
        "",
        "## The laws you are working under",
        "",
        laws or "(this project declares no laws file)",
    ])


def run_agent(root, card, project, model=None, transcript=None):
    """Spawn the agent on one card, prompt on STDIN.

    STDIN and not argv: every CLI has stdin, no two spell a prompt the
    same way in flags, and argv has quoting and length limits a card's
    prose will eventually meet.
    """
    if not project["agent"]:
        raise ValueError("amik.toml names no [agent] command")
    argv = shlex.split(project["agent"])
    if model:
        argv += ["--model", str(model)]
    try:
        # The agent is a FRESH PROCESS per card, so a variable works
        # here where it would race the server: the loop and the board
        # share one process and an environment set there would
        # attribute somebody's drag to whatever ran last. A card
        # cannot rewrite this one.
        env = dict(os.environ, AMIK_ACTOR="agent")
        out = subprocess.run(argv, cwd=root, env=env,
                             input=prompt(root, card, project),
                             text=True, capture_output=True)
    except OSError as exc:
        # launchd hands a job a minimal PATH, so "command not found" is
        # the FIRST thing an unattended run meets, not a rare one. Under
        # a trigger nobody reads stderr, and a traceback there looks
        # exactly like nothing having happened.
        raise ValueError("cannot run the agent command {!r}: {}".format(
            argv[0], exc.strerror or exc)) from None
    if transcript:
        _keep(transcript, out.stdout, out.stderr)
    return out


def _could_not_start(root, card, project, placed, reason):
    """The agent never ran. Not "failed" — a failed agent has an exit
    code, and the card goes back to Ready for that. This is the command
    itself not starting, and it will not start next tick either.

    `run_agent` already said why this is the FIRST thing an unattended
    run meets: launchd hands a job a four-directory PATH. What it did
    not have was a caller that treated the answer as one. `work_once`
    caught the ValueError as an ordinary refusal, indistinguishable from
    "not armed" — AFTER moving the card to `doing` and checking out its
    branch. Three starter cards sat in `doing` in twenty seconds, no
    agent ever run, nothing on any card and nothing in the log.

    So: the same halt a failed verify sets and an owner sets by hand,
    with the error ON THE CARD where the owner reads. `review` rather
    than `ready`, because Ready would be taken again next tick and fail
    the same way forever; and a halted card pauses the queue below it,
    which is what stops the second card meeting the same missing
    command. The tree comes home — the branch holds nothing worth
    parking on, and a checkout left on an empty card branch is the
    owner's trunk quietly not being the trunk. The branch itself stays:
    a resumed card checks it out rather than recreating it, and
    dropping one is the kind of tidying that only ever costs.
    """
    edit.record_outcome(
        root, card["id"],
        "**The agent could not be started, so this card was not worked.** "
        "No agent ran, and its branch holds nothing.\n\n```\n"
        + reason.strip() + "\n```", by="Amik")
    if not card.get("halt"):
        edit.update(root, card["id"], {"halt": True}, by="amik")
    edit.move(root, card["id"], "review", 0, by="amik")
    if placed["data"]["branch"]:
        git.finish(root, project["trunk"], project["shared"])
    return {"did": None, "fault": True,
            "why": "could not start the agent: " + reason}


def _keep(path, stdout, stderr):
    """The raw stream, beside the board rather than on the card.

    A transcript is every file the agent read, and it is long. On the
    card it would bury the prose and make every diff unreadable — the
    card is what a person reads, and this is the escape hatch for when
    reading it is not enough.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(stdout or "")
        if stderr:
            f.write("\n----- stderr -----\n" + stderr)


_ATTRIBUTION = "*Worked by "


def _newest_outcome(outcome):
    """The LAST entry under a card's `## Outcome`.

    Outcomes append, so a card worked twice carries both, and the one
    worth telling someone about is the one that just happened. Entries are
    separated by the attribution line every `record_outcome` writes; a
    trailing chunk carrying none is an entry too, from before that line
    existed.
    """
    entries, current = [], []
    for raw in str(outcome or "").split("\n"):
        line = raw.strip()
        if line.startswith(_ATTRIBUTION) and line.endswith("*"):
            if "\n".join(current).strip():
                entries.append("\n".join(current).strip())
            current = []
        else:
            current.append(raw)
    if "\n".join(current).strip():
        entries.append("\n".join(current).strip())
    return entries[-1] if entries else ""


def _first_sentence(text, cap=200):
    """One sentence of it, flattened, and never longer than a line.

    The ceiling matters more than the sentence boundary being perfect: a
    notify command's argv ends up in a chat message, and an outcome that
    opens with a paragraph must not arrive as one. A `.` is only an end
    when a space or the end of the text follows it, so `**Built.**` and
    `v1.2` do not cut a sentence in half.
    """
    flat = " ".join(str(text or "").split())
    cut = len(flat)
    for i, char in enumerate(flat):
        if char in ".!?" and (i + 1 == len(flat) or flat[i + 1] == " "):
            cut = i + 1
            break
    out = flat[:cut].strip()
    return out if len(out) <= cap else out[:cap].rstrip() + "…"


def landing_line(card_id, status, outcome=""):
    """What a person is told: the card, where it landed, and why.

    The why is the newest outcome's first sentence, which is what an
    outcome's first sentence is usually already for. A card that recorded
    nothing says only where it went — a reason read off the exit code
    would report the machinery rather than the work.
    """
    why = _first_sentence(_newest_outcome(outcome))
    return "amik worked {} → {}{}".format(
        card_id, status or "nowhere the board can see",
        " — " + why if why else "")


def notify(project, line, status=None):
    """Tell someone, when the card landed somewhere they asked about.

    The gate lives here rather than at the call site so that one place
    decides both whether to speak and how — a caller that filtered first
    would be a second place to teach about a new column.

    An UNKNOWN landing (`status` empty: the board would not read back, or
    the row is gone) always speaks. It is not a status anyone configured,
    and silence about a card that went somewhere unreadable is the one
    thing this filter must not buy.
    """
    if not project["notify"]:
        return
    if status and status not in project["notify_on"]:
        return
    # WHICH BOARD. Two boards are two servers, and nothing stops one
    # person pointing both at the same notifier rather than standing up
    # a second bot for the second project. A card id and a column say
    # nothing about which project they belong to, so without this the
    # two arrive indistinguishable.
    #
    # Only when the project declared a name. Amik invents one nowhere
    # else -- a guessed name reads exactly like a chosen one -- and an
    # empty one would be a separator with nothing in front of it.
    if project.get("name"):
        line = "{} · {}".format(project["name"], line)
    try:
        subprocess.run(shlex.split(project["notify"]) + [line],
                       capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass                       # telling someone must never fail a run


# ── the tick ─────────────────────────────────────────────────────────


def work(root, dry_run=False, if_changed=False):
    """A batch: cards from the top of Ready until something stops it.

    Stops on the FIRST card that does not close cleanly rather than
    carrying on down the list. A run that hit trouble and kept going
    would bury the card that went wrong under the ones after it, and a
    tree left mid-edit is not a tree the next card can be worked in.

    `ceiling` is the other stop and it is the one that matters when
    nobody is watching: a loop with no limit empties the board overnight.

    `if_changed` is what a TRIGGER uses. The board file is the doorbell,
    and a watch can fire more than once for one write — so a firing on an
    unmoved board costs a single stat and nothing else.
    """
    project = board.amik_project(root)
    ceiling = project["data"]["ceiling"] if project["ok"] else 1
    if if_changed and not changed(root):
        return {"did": [], "why": "the board has not moved since the last look"}
    # Remembered on every LOOK, not only after a worked card: a board
    # that was looked at and found empty must not look moved next tick.
    remember(root)
    done, last = [], None
    # 0 is no limit. `count()` rather than a large number, so "drain
    # Ready" is what the code says rather than what it approximates.
    rounds = itertools.count() if not ceiling else range(max(1, int(ceiling)))
    for _ in rounds:
        last = work_once(root, dry_run=dry_run)
        if not last.get("did"):
            break
        done.append(last["did"])
        if last.get("returncode"):
            last = dict(last, why=last["why"] + " — stopping the batch")
            break
    return {"did": done, "why": last["why"] if last else "nothing to do",
            "last": last}


def _landed(root, card_id):
    """The card's row as the board has it NOW — after the agent.

    `{}` when the board will not read or the row is gone, which is not the
    same as a card that stayed put: an unknown landing is the one a person
    most needs told about, and `landing_line` and `notify` both read the
    missing status that way.
    """
    after = board.amik(root)
    if not after["ok"]:
        return {}
    return next((dict(c) for col in after["data"]["columns"]
                 for c in col["cards"] if c.get("id") == card_id), {})


def _verify(root, command):
    """Run the project's verify command and say whether it passed.

    `shell=True` because `verify` is a shell command string — a real
    one looks like `cd ui && npm test` — and splitting it would be
    inventing a grammar the config never promised.

    `stdin=DEVNULL` for the reason every subprocess here has it: a child
    inheriting this process's stdin waits on a pipe nobody will close.
    """
    try:
        out = subprocess.run(command, shell=True, cwd=root,
                             capture_output=True, text=True,
                             stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        _remember_verify(root, command, False, f"verify could not run: {exc}")
        return False, f"verify could not run: {exc}"
    if out.returncode:
        tail = (out.stdout or out.stderr or "").strip().split("\n")[-3:]
        _remember_verify(root, command, False, "\n".join(tail))
        return False, "\n".join(tail)
    # The last line, because every runner worth the name puts its count
    # there and none of them agree on the format. Amik keeps the
    # sentence rather than parsing a number out of it -- reading "993
    # passed" is the project's own words, and inventing a count from
    # them is the framework knowledge this tool has refused to carry.
    tail = (out.stdout or out.stderr or "").strip().split("\n")[-1:]
    _remember_verify(root, command, True, "\n".join(tail))
    return True, ""


def _remember_verify(root, command, ok, tail):
    """What the last verify said, beside the board.

    The bar reports this, and a board that has never landed a card has
    never run one -- which reads as "not run yet" rather than as a
    failure, because those are different things.

    Machine-local and disposable, like the lock and the seen cursor: a
    result from another machine means nothing here.

    **Never raises.** Verify's answer is what gates a merge, and a
    bookkeeping write that could not happen must not turn a green tree
    red.
    """
    try:
        os.makedirs(_path(root, "amik"), exist_ok=True)
        with open(_path(root, "amik/.verify"), "w", encoding="utf-8") as f:
            json.dump({"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                       "ok": bool(ok), "command": command,
                       "tail": tail.strip()}, f)
    except OSError:
        pass


def land(root):
    """Merge every card that is owed one, in one gesture.

    Every closed card owes a merge now, so this cannot be a per-card
    ritual anybody performs by hand — a queue that grows faster than a
    person clears it is friction this change would have created rather
    than removed.

    Per card: merge, **re-run verify from the MERGED tree** because a
    merge can break what both sides passed, then drop the ref, sweep
    the prototype and clear the field. A red verify unwinds THAT merge
    and the batch carries on: one bad card must not strand the rest.
    """
    project = board.amik_project(root)
    if not project["ok"]:
        return {"ok": False, "reason": project["reason"]}
    project = project["data"]
    trunk = project["trunk"]
    if not trunk:
        return {"ok": False, "reason": "no trunk: set `trunk` in amik.toml"}
    if not git.is_repo(root):
        return {"ok": False, "reason": "not a git repository"}

    # OWED FIRST, then the tree. The order is the fix.
    #
    # A card landing in `review` parks the tree on its own branch on
    # purpose: the work worth looking at is there. But the owner moving
    # that card to Done is not an unusual act -- for a card carrying a
    # prototype flag it is the ONLY way it can close, since
    # `amik_agent_may_close` refuses one and the card's prose says so.
    # Nothing then un-parked the tree, and landing refused on every tick
    # while finished work piled up unmerged.
    #
    # So the parking is honoured while a card is still in `review`,
    # which is when it owes no merge and this returns before touching
    # anything. It stops being honoured the moment a branch is owed a
    # merge, because then the parked tree is the only thing preventing
    # one.
    owed = board.amik_finalise(root)
    if not owed["ok"]:
        return {"ok": False, "reason": owed["reason"]}
    if not owed["data"]:
        return {"ok": True,
                "data": {"landed": [], "refused": {}, "verified": []}}

    here = git.current_branch(root)
    if not here["ok"]:
        return {"ok": False, "reason": here["reason"]}
    if here["data"] != trunk:
        # `finish` rather than a bare checkout: it lifts the protection
        # the parking put on first, and a `skip-worktree` path with
        # local changes blocks a checkout outright.
        came = git.finish(root, trunk, project["shared"])
        if not came["ok"]:
            # Still a refusal, and still for the original reason: git
            # merges INTO the current branch, so merging a card into
            # another card's branch is worse than not merging. What
            # changed is that this is now the last resort rather than
            # the first answer.
            return {"ok": False, "reason":
                    "landing happens on the trunk, and this tree could "
                    "not leave " + here["data"] + ": " + came["reason"]}

    landed, refused, skipped_verify = [], {}, []
    for card in owed["data"]:
        cid = card["id"]
        # The lock is checked per card rather than held for the batch:
        # a long verify would otherwise block the loop for the whole
        # run, and a card that starts being worked mid-batch is one
        # this must not merge underneath.
        try:
            with Lock(root, cid):
                name = card.get("branch") or "card/" + cid
                if not git.branch_exists(root, name):
                    refused[cid] = "no such branch: " + name
                    continue
                # Did the trunk move since this branch was cut?
                #
                # If it did not, the merged tree is byte-identical to
                # the tree the card's own agent already verified, and
                # running the suite again cannot discover anything —
                # it is the same files answering the same question, at
                # three minutes a card.
                #
                # If it DID move, the second run earns its keep: two
                # cards can each be green alone and broken together,
                # one renaming what the other calls. That is the case
                # this check exists to keep paying for, and it becomes
                # the common one the day cards run in parallel.
                settled = git.run(root, "merge-base", "--is-ancestor",
                                  trunk, name)["ok"]
                merged = git.run(root, "merge", "--no-ff", "--no-edit",
                                 name)
                if not merged["ok"]:
                    # Never leave MERGE_HEAD in a shared checkout:
                    # anything else that commits adopts the staged merge
                    # under its own message.
                    git.run(root, "merge", "--abort")
                    refused[cid] = merged["reason"]
                    continue
                green, why = (True, "") if settled else _verify(
                    root, project["verify"])
                if not green:
                    git.run(root, "reset", "--hard", "HEAD~1")
                    refused[cid] = "verify failed after merging: " + why
                    continue
                git.drop_branch(root, name)
                edit.discard_prototype(root, cid)
                edit.set_branch(root, cid, "", by="amik")
                landed.append(cid)
                if settled:
                    skipped_verify.append(cid)
        except Busy as exc:
            return {"ok": False, "reason": str(exc)}
    # `verified` says which landings were actually re-checked, so a
    # fast batch is legible rather than suspicious.
    return {"ok": True, "data": {"landed": landed, "refused": refused,
                                 "verified": [c for c in landed
                                              if c not in skipped_verify]}}


def _fault_line(last):
    """What a tick must SAY, or "" for the ordinary refusals.

    Two kinds get said. A FAULT is the loop failing at its one job on a
    board that asked for work -- an agent command that would not start,
    a tree that could not be placed. A refused LANDING is finished work
    sitting unmerged, which is the one this was written for: it refused
    on every tick for an hour, and the only way to find out was to read
    the code.

    Everything else stays quiet. "Not armed" and "nothing in Ready" are
    answers, and a log that repeats them is a log nobody opens.
    """
    if last.get("fault"):
        return "amik: " + str(last.get("why") or "a tick failed")
    refused = (last.get("landed") or {}).get("refused")
    if isinstance(refused, str) and refused.strip():
        return "amik: nothing landed — " + refused.strip()
    if isinstance(refused, dict) and refused:
        return "amik: " + "; ".join(
            "{} did not land — {}".format(cid, why)
            for cid, why in sorted(refused.items()))
    return ""


def tick_forever(root, sleep=None, stop=None, rounds=None):
    """Work the board whenever it moves. The loop, without a scheduler.

    A timer that WATCHES A FILE. Every interval it stats `board.jsonl`
    and works the queue only when that has moved, so a quiet board costs
    one stat and nothing else — no spawn, no read, no agent. That is
    what keeps a timer honest here: the law is that a timer must never
    wake a PAID step, and between this one and any spend sit three free
    checks — the board moved, the project is armed, the queue has a
    take.

    **The first pass ignores whether the board moved.** A fresh process
    has nothing to compare against, and a server started with a card
    already in Ready that sat there until somebody touched the file
    would look broken. `if_changed` is the right question for a trigger
    firing repeatedly and the wrong one for a process that has just
    started.

    **An exception never ends this.** It is the only thing working a
    board now, so a tick that throws must not leave a server answering
    requests and working nothing for the rest of its life. It is
    reported on stderr — surviving quietly would be its own failure,
    since there is no scheduler left to ask — and the next tick runs.

    `rounds` bounds the iterations so a test can drain it; `stop` is a
    `threading.Event`, waited on rather than slept through so a shutdown
    is immediate rather than an interval away.
    """
    if sleep is None:
        project = board.amik_project(root)
        sleep = project["data"]["tick"] if project["ok"] else 1.0
    stop = stop or threading.Event()
    first = True
    said = None
    counter = itertools.count() if rounds is None else range(rounds)
    for _ in counter:
        if stop.is_set():
            return
        try:
            res = work(root, if_changed=not first)
            # A refusal is an answer and stays quiet: "not armed",
            # "nothing in Ready". A FAULT is the loop failing at its one
            # job on a board that asked for work, and a refused LANDING
            # is finished work not being merged — neither is boring, and
            # both were silent.
            #
            # Once, not every tick. A tick is a second long, and a merge
            # conflict printing on every one of them is the reason
            # nobody reads this log. Held in memory rather than on
            # disk: a restart reprinting it once is right, because a
            # restart is somebody looking.
            note = _fault_line(res.get("last") or {})
            if note and note != said:
                print(note, file=sys.stderr)
            said = note
        except Exception as exc:                  # noqa: BLE001
            print("amik: a tick failed and the next one will run anyway: "
                  "{}: {}".format(type(exc).__name__, exc), file=sys.stderr)
        first = False
        if stop.wait(sleep):
            return


def work_once(root, dry_run=False):
    """One pass. Returns a dict saying what happened and why.

    Never raises for an ordinary refusal — not armed, nothing to do,
    someone else is working — because those are answers, not faults.
    """
    project = board.amik_project(root)
    if not project["ok"]:
        return {"did": None, "why": project["reason"]}
    project = project["data"]

    # A DRY RUN reports rather than refuses. "Not armed" is the right
    # answer to "did you work a card"; it is a useless answer to "what
    # would you work" — and both checks are free, so there is no reason
    # to make someone arm the board to find out.
    if not project["armed"] and not dry_run:
        return {"did": None, "why": "not armed"}

    # Land what is owed, BEFORE looking for work.
    #
    # Moving a card to Done is the whole gesture — dropdown, drag or
    # button — and the finalisation belongs to the destination rather
    # than to whoever remembered to run a command afterwards. That
    # write rings the doorbell anyway, so the loop is already awake;
    # it would be a strange design that woke up, saw a merge owed, and
    # went looking for something else to do.
    #
    # Cheap when nothing is owed: one board read. Cheap when something
    # is, most of the time — the post-merge verify is skipped whenever
    # the trunk has not moved since the branch was cut.
    #
    # A refusal here does NOT stop the tick. Landing and working are
    # different jobs; a branch that will not merge is a thing to
    # report, not a reason to stop taking cards.
    landed = None
    if not dry_run:
        res = land(root)
        if res["ok"] and res["data"]["landed"]:
            landed = res["data"]
        elif not res["ok"]:
            landed = {"refused": res["reason"]}

    queue = board.amik_queue(root)
    if not queue["ok"]:
        return {"did": None, "why": queue["reason"]}
    take = queue["data"]["take"]
    if take is None:
        halted = queue["data"]["halted"]
        return {"did": None, "landed": landed, "why": (
            "the queue is paused at {!r}".format(halted["id"]) if halted
            else "nothing in Ready is workable")}

    if dry_run:
        return {"did": None, "would": take["id"],
                "armed": project["armed"],
                "why": ("would work {!r}".format(take["id"])
                        if project["armed"] else
                        "would work {!r}, but the project is not armed"
                        .format(take["id"]))}

    try:
        with Lock(root, take["id"]):
            # The tree goes where the card belongs BEFORE anything else
            # happens in here — before the move to `doing`, because that
            # move writes `board.jsonl` and would leave the tree dirty
            # by Amik's own hand.
            #
            # This is the whole fix. Placement is a property of the
            # transition BETWEEN cards, and the loop is the only thing
            # that sees two: an agent placing the tree correctly for its
            # own card and never putting it back is how 34 commits ended
            # up off the trunk.
            # A project WITHOUT git loses branch placement, not the
            # board. Amik does not require a repository, and refusing
            # to work a card because there is no git would make it a
            # tool for git repositories only — which is the opposite of
            # what `handle()` and every declared key are for.
            placed = ({"ok": True, "data": {"branch": "", "swept": ""}}
                      if not git.is_repo(root)
                      else git.start(root, take["id"], project["trunk"],
                                     project["shared"]))
            if not placed["ok"]:
                # The same halt an owner sets by hand and a failed
                # verify sets. One field, one gate — the queue does not
                # care who set it.
                #
                # git's words go ON THE CARD, not only into this
                # function's return value. They were in the return
                # before, where launchd's log is the only reader, so a
                # card halted at placement said nothing at all — and
                # the test asserting "it carries git's words" was
                # reading the return value too, and passed.
                edit.record_outcome(
                    root, take["id"],
                    "**The tree could not be placed, so this card was "
                    "not worked.** No agent ran and no branch was "
                    "made.\n\n```\n" + placed["reason"].strip()
                    + "\n```", by="Amik")
                edit.update(root, take["id"], {"halt": True}, by="amik")
                edit.move(root, take["id"], "review", 0, by="amik")
                return {"did": None, "fault": True,
                        "why": "could not place the tree: "
                               + placed["reason"]}
            # Record WHERE, on the card. `amik_finalise` reads this
            # field to find work owed a merge, so a card whose branch
            # was never written is one `land` cannot see — its commits
            # would sit on a ref nothing points at. Amik writes it now;
            # the agent's laws lost git entirely.
            if placed["data"]["branch"]:
                edit.set_branch(root, take["id"], placed["data"]["branch"],
                                by="amik")
            # Into `doing` BEFORE the agent starts. It costs one line
            # write, and it is the only thing that tells a person looking
            # at the board that work has begun — left to the agent it
            # happens whenever that agent gets round to reading its
            # instructions, which on a large card is minutes of the board
            # saying nothing is happening while something is.
            moved = edit.move(root, take["id"], "doing", 0, by="amik")["ok"]
            # WHO and WITH WHAT, as its own line rather than as extra
            # fields on the move. The door stays strict -- a verb that
            # accepted arbitrary keywords would swallow a misspelled
            # `fingerprint` in silence -- and the event says plainly
            # what the move only implies.
            #
            # The row has room for neither, and a board that runs more
            # than one agent has to be able to ask its own history
            # which one took a card and under which model. The program
            # name rather than the whole command: the flags are
            # identical on every card and the name is the answer.
            log.note(root, take["id"], "work", "amik",
                     model=take.get("model"),
                     agent=log.program(project["agent"]))
            transcript = (_path(root, "amik/runs/{}/{}.log".format(
                take["id"], time.strftime("%Y%m%dT%H%M%S")))
                if project["transcript"] else None)
            try:
                out = run_agent(root, take, project,
                                model=take.get("model"),
                                transcript=transcript)
            except ValueError as exc:
                return _could_not_start(root, take, project, placed,
                                        str(exc))
            # Where the card ended up, read once and used twice: it
            # decides both whether the loop must put it back and whether
            # anyone is told. A second read between those two would be a
            # second answer to one question.
            landed = _landed(root, take["id"])
            # A card the loop moved and the agent then failed on must go
            # BACK. `doing` is invisible to the queue, so a card stranded
            # there is one that silently stops being work — and this is
            # restoring what the loop changed, not the agent promoting
            # its own card into Ready.
            if moved and out.returncode and landed.get("status") == "doing":
                if edit.move(root, take["id"], "ready", 0, by="amik")["ok"]:
                    landed["status"] = "ready"
            line = "amik worked {} (exit {})".format(take["id"], out.returncode)
            notify(project,
                   landing_line(take["id"], landed.get("status"),
                                landed.get("outcome")),
                   landed.get("status"))
            # What this card changed that is LIVE. Shared paths are
            # protected while the card runs, so anything dirty here is
            # something the agent wrote and could not commit — which is
            # exactly the set worth reporting.
            #
            # The board is excluded. It is shared, and it changes on
            # every single card, because moving a card IS Amik's own
            # bookkeeping rather than anything the card did.
            # Lift the protection BEFORE looking. `skip-worktree` hides
            # a file from `git status` as well as from `git add -A` —
            # one mechanism, not two — so a card's live changes are
            # invisible until it comes off.
            if placed["data"]["branch"]:
                git.unprotect(root, project["shared"])
            # `churn` paths are exempt: declared as changing on their
            # OWN. Measured rather than guessed — the first live probe
            # was halted for two cursor writes its agent never made,
            # because the hourly watchers fired mid-card and git cannot
            # tell one writer from another. The board is in that list
            # for the same reason said differently: moving a card IS
            # Amik's own bookkeeping.
            # Two exemptions, and they come from different places on
            # purpose. Amik's OWN FOLDER is exempt without being
            # declared: the board, the cards, everything under `amik/`.
            # Writing a card is bookkeeping — every card that closes
            # writes its own outcome — and making a project remember
            # to declare that would be Amik asking to be told
            # something it knows. The report is about the PROJECT's
            # shared state; Amik reporting its own writes as a finding
            # would fire on every card and mean nothing.
            # `churn` is the project's own: paths that change on their
            # own schedule, which only the project can name.
            #
            # Measured rather than guessed: the first live probe was
            # halted for two cursor writes its agent never made. The
            # hourly watchers fired mid-card, and git cannot tell one
            # writer from another.
            churn = set(git.changed_under(root, project["churn"]))
            touched = [p for p in git.changed_under(root, project["shared"])
                       if p not in churn and not p.startswith("amik/")]
            if touched:
                edit.record_outcome(
                    root, take["id"],
                    "This card also changed shared state. That is LIVE "
                    "now — it is not on the card's branch, and dropping "
                    "the branch will not undo it:\n\n"
                    + "\n".join("- `{}`".format(p) for p in touched)
                    # Two commands, because a card parked in `review`
                    # keeps Amik's `skip-worktree` on these paths and
                    # git refuses a pathspec carrying it — "did not
                    # match any file(s) known to git", which names
                    # nothing and reads like the path is wrong. The
                    # lift is harmless where there is no flag to lift.
                    + "\n\nUndo is:\n\n```\ngit update-index "
                      "--no-skip-worktree -- <path>\ngit checkout {} "
                      "-- <path>\n```".format(
                        placed["data"].get("swept") or "<the sweep commit>"),
                    by="Amik")
                # A change that is live the instant it is made, landing
                # with nobody told, is the one outcome this must not
                # produce. An owner who already asked for a pause is not
                # told again that the loop imposed one.
                if not take.get("halt"):
                    edit.update(root, take["id"], {"halt": True}, by="amik")
                    edit.move(root, take["id"], "review", 0, by="amik")
                    landed["status"] = "review"

            # Home, unless the card is waiting to be looked at. A
            # halted card keeps its branch: the work worth looking at is
            # on it, and the board's top bar names it.
            #
            # A parked tree gets its protection BACK. The report above
            # needed the paths visible, but the branch is then somebody
            # else's for hours or days, and a bare shared path there is
            # captured by whatever commits next — which is how a worked
            # card's row came to say `review` on its branch and `ready`
            # on the trunk, where the loop would have taken it again.
            # `finish` does the lift on the way home, so the trunk is
            # never left holding a flag.
            if placed["data"]["branch"]:
                if landed.get("status") == "review":
                    git.protect(root, project["shared"])
                else:
                    git.finish(root, project["trunk"], project["shared"])
            return {"did": take["id"], "why": line, "landed": landed,
                    "returncode": out.returncode, "transcript": transcript}
    except Busy as exc:
        return {"did": None, "why": str(exc)}
    except ValueError as exc:
        return {"did": None, "why": str(exc)}
