"""`python3 -m amik` — the board's command line.

    amik serve            the board in a browser, loopback only
    amik work --once      work one card, if the project is armed
    amik status           what the queue would do, changing nothing
    amik land             merge every card that is owed one
    amik init             put a starter board into this project
"""
import argparse
import json
import os
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="amik")
    ap.add_argument("--root", default=".",
                    help="the directory holding amik/ (default: here)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    srv = sub.add_parser("serve", help="serve the board on 127.0.0.1")
    srv.add_argument("--port", type=int, default=4455)
    srv.add_argument("--no-loop", action="store_true",
                     help="serve the board without working it — for "
                          "looking at one you do not want touched")

    wrk = sub.add_parser("work", help="work the top of Ready")
    wrk.add_argument("--once", action="store_true",
                     help="one card, then stop")
    wrk.add_argument("--if-changed", action="store_true",
                     help="do nothing unless the board moved since the "
                          "last look — what a trigger uses, so a firing "
                          "on an unmoved board costs one stat")
    wrk.add_argument("--dry-run", action="store_true",
                     help="say which card would be worked, and stop")

    sub.add_parser("status", help="what the queue would do, changing nothing")

    # ── the write doors ─────────────────────────────────────────────
    #
    # The SAME `core.edit` functions the page calls, with a mouth an
    # agent can reach whatever the host project is written in. The laws
    # name `amik.core.edit` as the only writer, and that module is
    # importable in this repository -- because the package sits in the
    # working directory -- and nowhere else. A card dragged to Ready on
    # a Bun project was picked up, worked by an agent that could not
    # reach the door it was ordered to use, and left in `doing` with no
    # outcome: it did the only lawful thing available, which was
    # nothing.
    #
    # Only the verbs a card needs WHILE BEING WORKED. Creating and
    # deleting stay the owner's, in the page; an agent that could delete
    # a card is one bad turn from deleting the board.
    mv = sub.add_parser("move", help="move a card to a column")
    mv.add_argument("card")
    mv.add_argument("status")
    mv.add_argument("--index", type=int, default=0,
                    help="position in the column, 0 is the top")

    oc = sub.add_parser("outcome", help="record what a card produced")
    oc.add_argument("card")
    oc.add_argument("text")
    oc.add_argument("--model", default=None,
                    help="the model that did the work; omitted writes "
                         "'model unrecorded', which is visible on purpose")

    ak = sub.add_parser("ask", help="raise a question the owner must answer")
    ak.add_argument("card")
    ak.add_argument("heading")
    ak.add_argument("--context", default=None,
                    help="what you already know — options, measurements, "
                         "what you tried. Lands as a blockquote, which is "
                         "the asker's half rather than the answer")

    ht = sub.add_parser("halt", help="pause a card for review, or release it")
    ht.add_argument("card")
    ht.add_argument("--off", action="store_true",
                    help="clear the halt instead of setting it")

    # ── the way back in from a brainstorm ───────────────────────────
    #
    # `needs-brainstorm` blocks a card and the queue skips it saying so.
    # Amik hosts no thinking, deliberately -- the ladder says what a
    # card still OWES, and discharging it happens wherever you think.
    # This is the door back: name the document you wrote, or say the
    # card turned out to need none.
    pl = sub.add_parser("plan", help="record the result of a brainstorm")
    pl.add_argument("card")
    pl.add_argument("--doc", action="append", default=None, metavar="PATH",
                    help="a document the build can open; repeat for more. "
                         "Sets the rung to has-plan")
    rung = pl.add_mutually_exclusive_group()
    rung.add_argument("--clear", action="store_true",
                      help="no plan needed after all — drop the rung. "
                           "\"thought about it, nothing to write down\" is "
                           "a real answer")
    rung.add_argument("--needs-brainstorm", action="store_true",
                      dest="needs_brainstorm",
                      help="open design questions — put the rung ON, which "
                           "blocks the card until it is discharged")

    lg = sub.add_parser("log", help="what has happened to this board")
    lg.add_argument("--card", default=None,
                    help="one card's history rather than the whole board")
    lg.add_argument("-n", type=int, default=40,
                    help="how many of the most recent to show (0 for all)")
    lg.add_argument("--json", action="store_true",
                    help="the raw lines, for something reading rather "
                         "than somebody looking")

    sub.add_parser("land", help="merge every card owed a merge, verifying "
                                "each from the MERGED tree")

    sub.add_parser("init", help="put a starter board into this project; "
                                "refuses one that already has a board")

    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)

    if args.cmd == "init":
        from .core.init import init
        res = init(root)
        print(json.dumps(res, indent=1))
        # A refusal here IS a fault: somebody asked for a board and did
        # not get one, unlike the loop's refusals which are answers.
        return 0 if res["ok"] else 1

    if args.cmd == "serve":
        from .app.server import serve
        return 0 if serve(root, args.port,
                          loop=not args.no_loop) is not False else 1

    from . import loop
    from .core import board

    if args.cmd == "status":
        project = board.amik_project(root)
        queue = board.amik_queue(root)
        # A project that cannot be read has no `armed` to report, and
        # printing `false` for it is the first thing a new board shows
        # and the easiest thing to misread: the config says true, and
        # the actual problem is an undeclared verify command. Say which.
        # The SAME reader the banner prints. `project["ok"]` only says
        # the config parsed, which is a different question -- and a
        # `status` that answers it while the banner answers the other
        # is one board giving two accounts of itself.
        will = board.amik_will_work(root)
        print(json.dumps({
            "ready_to_work": will["ok"],
            "why_not": None if will["ok"] else will["reason"],
            "armed": bool(project["ok"] and project["data"]["armed"]),
            "agent": (project["data"]["agent"] if project["ok"] else ""),
            "take": (queue["data"]["take"] or {}).get("id")
            if queue["ok"] else None,
            "queued": [c["id"] for c in queue["data"]["queued"]]
            if queue["ok"] else [],
            "skipped": queue["data"]["skipped"] if queue["ok"] else [],
        }, indent=1))
        return 0

    # Every write goes through `core.edit`, so a refusal here is the
    # door's own words rather than a traceback -- an agent reads stdout
    # and cannot act on a stack trace.
    if args.cmd == "plan":
        from .core import edit
        if args.clear:
            fields = {"planning": ""}
        elif args.needs_brainstorm:
            fields = {"planning": "needs-brainstorm"}
        elif args.doc:
            fields = {"planning": "has-plan", "docs": args.doc}
        else:
            # `has-plan` claims a plan exists and `docs` is where it is
            # named; the card draws "plan not named" when that field is
            # empty. Writing one without the other would be filing the
            # contradiction rather than resolving it.
            print("nothing to record: pass --doc PATH, or --clear if the "
                  "card turned out to need no plan, or --needs-brainstorm "
                  "to put the rung on")
            return 1
        res = edit.update(root, args.card, fields)
        print(json.dumps(res, indent=1))
        return 0 if res["ok"] else 1

    if args.cmd in ("move", "outcome", "ask", "halt"):
        from .core import edit
        if args.cmd == "move":
            res = edit.move(root, args.card, args.status, args.index)
        elif args.cmd == "outcome":
            res = edit.record_outcome(root, args.card, args.text,
                                      model=args.model)
        elif args.cmd == "ask":
            res = edit.ask(root, args.card, args.heading,
                           context=args.context)
        else:
            res = edit.update(root, args.card, {"halt": not args.off})
        print(json.dumps(res, indent=1))
        return 0 if res["ok"] else 1

    if args.cmd == "log":
        from .core import log as history
        entries = history.read(root, limit=args.n or None, card=args.card)
        if not entries:
            # An answer, not an error. A board nobody has touched since
            # this shipped has no history and is not broken.
            print("no history yet"
                  + (" for {!r}".format(args.card) if args.card else "")
                  + " — amik/log.jsonl is written as cards move")
            return 0
        for entry in entries:
            print(json.dumps(entry, ensure_ascii=False) if args.json
                  else history.line(entry))
        return 0

    if args.cmd == "land":
        print(json.dumps(loop.land(root), indent=1))
        return 0

    res = (loop.work_once(root, dry_run=args.dry_run) if args.once
           else loop.work(root, dry_run=args.dry_run,
                          if_changed=args.if_changed))
    print(json.dumps(res, indent=1))
    # 0 when it worked a card or correctly declined; a refusal is an
    # answer, not a fault, and a scheduler must not treat it as one.
    return 0


if __name__ == "__main__":
    sys.exit(main())
