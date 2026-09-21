# Amik

**A kanban board an agent can work.** Cards live as files in your repository, you move them between columns in a browser, and an agent picks up the top of Ready and builds it — verifying against your own test command before it closes anything.

```bash
curl -fsSL https://raw.githubusercontent.com/jeffkward/amik/main/install.sh | bash
```

and then from your project directory:

```bash
amik serve
```

The board is at **http://localhost:4455**.

The first run writes a board with seven starter cards that explain themselves by being worked. Delete them when they have done their job. To install from a clone instead, `git clone` this repo and run `bash install.sh`.

## Why files

A card's state is a line in `board.jsonl` and its prose is `cards/<id>.md`, so a card changes in the same commit as the code it describes, and `git log` answers what happened without a second system to ask. An agent reads and writes the same files you do.

State and prose are split because reordering is bulk and prose is individual: dragging one card renumbers a whole column, which is one write here and would be dozens if rank lived in per-card frontmatter — while answering a question should show as three lines in `git diff` rather than a replaced kilobyte of escaped JSON.

| `board.jsonl` | Card STATE. One JSON object per line, hand-editable. `rank` orders a column, 1 at the top |
| `cards/<id>.md` | One card's PROSE. Plain markdown, no frontmatter |
| `log.jsonl` | What has HAPPENED — moves, questions, answers, outcomes, toggles, retries. `amik log` reads it |
| `amik.toml` | **The only file an agent needs to be told about.** How this project is verified, which file holds its laws |
| `prototypes/<id>/` | A card's design pass, deleted when the card is done |

## Declaring your project

**One line stands between a new install and a working board**, and it is `verify`. Everything else ships filled in.

```toml
verify = ""                 # ← the only thing you must declare
laws   = "CLAUDE.md"        # what an agent reads first
armed  = true               # the kill switch

[agent]                     # preloaded for Claude Code; any CLI that
command = "claude -p ..."   # reads a prompt on stdin will do

[state]                     # stops a card's branch capturing the board
shared = ["amik/board.jsonl", "amik/cards"]
```

`verify` has no default because a test command invented on a project's behalf is how a loop reports success on nothing. The shipped file explains every other value where it sits.

The agent command is the one place Amik names a vendor. It is preloaded because a fresh board that cannot work a card is worse than an opinion, and the flags matter: an unattended agent missing a tool it needs asks permission, gets no answer, and waits — which looks exactly like a board with nothing to do.

`armed` is **not the gate that matters** — `verify` and `[agent] command` both refuse until declared, so nothing runs before you have said what works your cards and how you check them. `armed` is the kill switch: set it false and the next tick stops, without deleting the configuration you will want back. It is re-read every tick, so nothing needs restarting.

# How the board works

## The columns

`inbox` → `todo` → `ready` → `doing` → `blocked` → `review` → `done`, plus `someday` (shelved) and `abandoned` (closed against).

**A new idea always lands in `inbox`.** Inbox means a decision is owed and nothing else.

**`ready` is a pull the owner makes, never a classification.** Nothing may auto-fill it — a column anything can write into only restates the one before it. The same holds for `blocked` and `review`: a card's presence in either is a declaration, never something inferred on the card's behalf.

`blocked` is one card whose own work stopped on a question it cannot answer. The queue is not stuck; this card is. `review` is built, suite green, waiting on a person alone.

## Contradictions are surfaced, never corrected

This is the board's governing law, and most of what follows is an instance of it. When a card's own fields disagree, Amik draws a ⚠ chip and the queue declines to take it. Nothing is quietly fixed, because which of the two facts was meant is the owner's call.

Two combinations say so today: a `ready` card still owing a blocking rung, and a `has-plan` card naming no document — that rung's whole value is pointing at something the build can open.

## What a card owes

`planning` says what a card still owes before it can be built. Absent means nothing owed, and it is cleared on every closed row.

| Rung | Means |
|---|---|
| `needs-brainstorm` | open design questions — **blocks** |
| `has-plan` | a written plan, and the card names the document |

**Amik does not host the thinking.** A card owing `needs-brainstorm` is discharged wherever you do that — a conversation with an agent, a design session, a document — and the card's id is the handle you carry into it. Coming back, one command records the result:

```bash
amik plan tighten-the-parser --doc docs/parser-plan.md
amik plan tighten-the-parser --clear          # turned out to need none
```

The board tracks that thinking is owed and never pretends to do it. [`.claude/skills/amik-brainstorm/`](.claude/skills/amik-brainstorm/SKILL.md) is a skill for the round trip — read the card, think it through, write the plan, record it — and copies into your own project's `.claude/skills/` if you want it there.

## Questions

A question is a `### ` heading under `## Questions` in the card's prose. Whatever is written beneath it is the answer; an empty section is an unanswered question. There is no separate field and no second place to look.

- **An unanswered question holds its card.** Even in Ready, the queue skips it and says why.
- **Any non-empty answer releases it.** `n/a` works as well as a paragraph — "take this anyway" is a real answer.
- **A leading blockquote is the asker's CONTEXT, not an answer** — options, measurements, what was already tried. Written anywhere else it lands in the box the owner types into and marks the question answered.
- **Saving the last answer on a `blocked` card returns it to Ready**, at the bottom. Answering is the pull, and the drag back was the forgotten half of the same gesture.
- **An agent asks through the door**, which refuses a heading the card already carries. The first occurrence wins on read, so an answer meant for a duplicate would write into the original.

## Handling — two toggles

- **⏸ halt** — land in `review` and pause the queue behind it. Nothing ranked below is worked until the card moves on.
- **▣ prototype** — a design pass comes first, and it forces ⏸ on, because "build a design pass then merge whatever came out" is not a state anyone wants.

Default is neither. On a closed card both are locked rather than cleared: they stop being levers and become the record of how the card was handled.

**Where the work goes is not a toggle.** Every card is worked on `card/<id>`, and Amik puts the tree there before the agent starts.

## Working the board

`amik serve` serves the board and works it. One process, one port, one board.

```
$ amik serve
amik → http://127.0.0.1:4455  (board: /path/to/your/project)
       working cards: yes
```

The second line is the one to read. If the board will not be worked it says so there and why — an undeclared `verify`, no `[agent] command`, `armed` not true — rather than leaving you to wonder later why nothing happened.

**How it notices.** A timer that watches a file: every second it stats `board.jsonl` and works the queue only when that has moved, so a quiet board costs one stat and nothing else. Dragging a card into Ready IS the write, so there is nothing else to poll.

**A board is worked only while it is served.** For a machine that is always on that is no restriction. For a laptop that closes, the loop closes with it — more honest than a background job that keeps spending while nobody is looking. If you want a board worked with nothing serving, `amik work --if-changed` is one command and any scheduler you already have will run it.

Two boards are two servers on two ports, sharing nothing but the installed code. `amik serve --no-loop` serves a board without working it.

```bash
cd ~/code/one && amik serve
cd ~/code/two && amik serve --port 4456
```

The first takes 4455 and the second is told to take 4456.

### Running it as a service

Amik ships no file for this on purpose — a plist is macOS, a unit is systemd, and a tool that guesses which you have is wrong somewhere. The recipe is the same three facts in all of them:

- **the command** — `amik serve`, with `--port` if this is not your only board
- **the working directory** — the project, the one holding `amik/`
- **the interpreter** — the full path to the `amik` in your virtualenv. This is the one people get wrong: a service starts with almost no `PATH`.

Send its output somewhere you will read. The first two lines say whether the board will be worked, and that log is the only place it is written down.

## What an agent does with a card

Each card goes to a fresh agent with a small brief: the card, the laws file, and the verify command. Not the project — a persistent session accretes the whole repository and pays for it on every tick.

1. Read the queue. It names the take, what is behind it, and why each skipped card was skipped. Picking a card by eye is how the board and the work drift apart.
2. Build it, on the branch Amik has already put the tree on.
3. Verify with the project's own command.
4. Record an outcome and close it — or, **if verify fails and cannot be fixed, set `halt` and leave the card in `review` naming what failed.** The alternative is merging red.

**An agent never moves a card to `ready`.** That is the owner's pull, always. Done is the agent's to set only when the card did not halt and there is nothing left to authorise.

## Being told what happened

`[loop] notify` is any command. Amik appends a one-line summary and runs it, so anything that can take a string on argv will do.

```
Niiwin Lite · amik worked tighten-the-parser → review — Verify failed on three tests.
```

The board's `name` leads the line when it has one, which means several boards can point at a single notifier without a second bot behind each. `notify_on` decides which landings are worth saying; absent, it is `review` and `blocked`, the two columns that mean the loop stopped and is waiting on a person.

## Prototypes

One directory per card having a design pass, at `amik/prototypes/<card-id>/index.html`. The stylesheets it wears are declared once in `amik.toml`, so a prototype looks like the application it is prototyping without anyone editing the file.

**They are not tracked by git.** A prototype's lifetime is its card's, and a tracked one lives on a single branch where every other branch cannot see it.

## Also here

- **[EMBEDDING.md](EMBEDDING.md)** — putting a board inside an application you already run, under your own routes and authentication.
- **[CLAUDE.md](CLAUDE.md)** — the laws an agent works under. Short on purpose: everything in it was paid for by something going wrong.

## This repository's own board

Amik is built with Amik, and that board is not in this repository. It is ignored the same way the lock and the run transcripts are — it holds whoever is working here and what they are thinking about next, which is theirs rather than the project's.

What ships instead is `amik/starter/`, the seven cards every new board begins with. A fresh clone therefore has no board, which is also the only state a board can be written into: seeding refuses an instance that already has one.

A project that adopts Amik should do the opposite and **track its board**. A card changing in the same commit as the code it describes is the whole premise.

### Working on Amik itself

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```

That last line is also what this repository declares as its `verify`, interpreter named in full. A card here is verified by an unattended process holding almost no PATH, where a bare `pytest` is either not found or — worse — found and the wrong one.
