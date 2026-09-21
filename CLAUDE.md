# Amik — the laws

You are an agent working a board. This file is the contract. It is short
on purpose: everything in it was paid for by something going wrong.

## The two files

**`board.jsonl` holds card STATE. `cards/<id>.md` holds card PROSE.**
One JSON object per line, one markdown file per card.

`log.jsonl` is a THIRD file and it is not yours to write. The door
appends a line to it for every structural change — moves, creations,
questions, answers, outcomes, toggles, branches, discards, deletions —
so a card's history survives the one `updated_at` its row can hold.
Read it with `amik log`; never edit it, and never write it directly.

The split is the point. State is relational and reordering is bulk — one
drag renumbers a whole column, which is one file write here and would be
dozens in per-card frontmatter. Prose is individual and its diffs matter:
answering a question should show as the sentences that changed, not as a
rewritten kilobyte of escaped JSON.

**A card file carries no frontmatter.** That would duplicate state the
board owns, and two writers for one field is how a board and its file
drift apart. A card with no prose has no file.

## The doors

**Never edit `board.jsonl` by hand, and never write `cards/<id>.md`
directly.** One door writes them, and your brief names the exact
command for it — a line beginning with a python interpreter and `-m
amik`. Use that, not an import: the project you are working in may not
be written in Python at all, and `amik.core.edit` is on your path only
when the board happens to live inside Amik's own repository. An agent
that reached for it on a Bun project could not, and lawfully did
nothing, leaving its card in `doing`.

The verbs you have while working a card:

| Command | For |
|---|---|
| `move <id> <column> [--index N]` | status and rank |
| `outcome <id> "<text>" --model "<you>"` | what the card produced |
| `ask <id> "<heading>" --context "<what you know>"` | a question the owner must answer |
| `halt <id> [--off]` | pause for review, or release |
| `plan <id> --doc <path>` | a brainstorm landed: name the document. `--needs-brainstorm` puts the rung on, `--clear` takes it off |
| `status`, `log --card <id>` | read, changing nothing |

Each prints what it did or refuses and says why. A refusal is an
answer: act on it rather than working around it.

Creating and deleting cards are the owner's, in the page. Behind all of
it is `amik.core.edit`, which is the only writer:

| Verb | For |
|---|---|
| `create` | a new card, at the bottom of its column |
| `update` | title, body, planning, group, the handling toggles, `docs` |
| `move` | status and rank — the drag's business, and nothing else's |
| `ask` | a question the owner must answer |
| `record_outcome` | what the card produced |
| `set_branch` | the branch a card was built on, and clearing it |
| `delete` | the row and its prose together |

The door renumbers columns, stamps `created_at`/`updated_at`, refuses a
write it could not read back, and refuses a stale one. A hand-written line
gets none of that and nothing checks it.

`move` and `update` are separate on purpose. Status and rank belong to the
drag; everything else belongs to the form. One verb that did both would be
one writer for two different decisions.

## The columns

`inbox` → `todo` → `ready` → `doing` → `blocked` → `review` → `done`,
plus `someday` (shelved) and `abandoned` (closed against — one word for
one meaning since 2026-09-17; a card measured and disproven says so in
its own prose, where every other ruling lives).

**A new idea always lands in `inbox`.** Inbox means a decision is owed and
nothing else.

**`ready` is a PULL the owner makes, never a classification.** Nothing may
auto-fill it, or the column would only restate what To-Do says. `blocked`
and `review` carry the same rule: a card's presence in either is a
declaration, never something inferred on the card's behalf.

`blocked` is a card whose own work stopped on a question it cannot answer
itself. `review` is a card that is built and green, waiting on the owner.

## What a card owes — the ladder

Two rungs. **Absent means nothing owed.**

| Rung | Means |
|---|---|
| `needs-brainstorm` | open design questions — **blocks** |
| `has-plan` | a written plan, and the card names the document |

Clear it on every closed row: a done item owes nothing.

**Amik does not host the thinking**, and `.claude/skills/amik-brainstorm/SKILL.md`
is the round trip when you want one. A card owing `needs-brainstorm` is
discharged wherever you think — a conversation, a design session, a
document — and the card's id is the handle you carry into it. Coming
back, `plan` is the door: name what you wrote, or clear the rung if the
answer turned out to need nothing written down. An agent that finds
open design questions mid-card puts the rung ON rather than guessing an
answer, and says why on the card.

**A `ready` card owing a blocking rung is a contradiction — surface it,
never silently correct it.** That is the governing law of this whole
board: contradictions are reported, not repaired. Which of two conflicting
facts was meant is the owner's call, not yours.

## Handling — two independent toggles

- **⏸ `halt`** — land in `review` and pause the queue behind it. Nothing
  ranked below is worked until the card leaves that column.
- **▣ `requires_prototype`** — a design pass comes first. It **forces ⏸
  on**, because "build a design pass then merge whatever came out" is not
  a state anyone wants.

Default is neither.

**Where the work goes is not a toggle.** Every card is worked on its own
branch, and Amik puts the tree there before you start. `⎇
branch_requested` was retired 2026-09-17: it asked a question with one
answer, and the tap it took was one among several in a modal opened
mostly to re-rank from.

## Working a card

1. Read the queue. `board.amik_queue(root)` names the take, what is behind
   it, why each skipped card was skipped, and the halt that paused it.
   **Do not pick a card by eye** — disagreeing with the queue silently is
   how the board and the work drift apart.
2. Read the file `amik.toml`'s `laws` key names, before touching anything.
3. The card is already in `doing` — the loop moved it there before
   starting you, so the board showed work had begun without waiting
   for you to read this. Move it on yourself when you are finished.
4. Verify with `amik.toml`'s `verify` command. It has no default: a
   project that has not declared how it is verified cannot be agent-worked,
   because guessing a test command is how a loop reports green on nothing.
5. Record an outcome, then close it.

**Never move a card to `ready`.** That is the owner's pull, always.

**`board.amik_agent_may_close(card)` is the rule for Done** — ask it
rather than re-deriving it. It requires a non-empty outcome and refuses a
card carrying ⏸ or ▣, reading `requires_prototype` directly rather than
trusting a halt to have been forced.

**If verify fails and you cannot fix it, the card halts.** Set `halt`
yourself, through the door, and leave it in `review` naming what failed.
It is the same field the owner sets by hand, so they clear it the same
way. The alternative is merging red or silently skipping work.

## Questions

A question is a `### ` heading under `## Questions`. Whatever is written
beneath it is the answer; an empty section is an unanswered question.

**Anything you need the owner to DECIDE goes through `ask`, never as prose
in the body.** Prose gives them no answer box and no hold on the card.
`ask` refuses a heading the card already carries — a duplicate is not
harmless, because the first occurrence wins on read, so an answer meant
for the second writes into the first.

A leading blockquote under the heading is the ASKER's context, not the
answer. Put what you know there — options, measurements, what you already
tried. Written anywhere else it lands in the box the owner types into and
marks the question answered.

**An unanswered question holds its card.** The queue skips it and says so,
even from `ready`.

**Saving the last answer on a `blocked` card returns it to Ready**, at the
bottom, and only when the card has no question left unanswered. That is
not the board auto-filling Ready, which nothing may do: answering is the
owner's own gesture and the drag back was the second half of it. It
changes nothing for you — an agent still never moves a card to Ready.
This is the owner's pull arriving through the answer box instead of the
drag.

## Outcomes

`record_outcome` writes what the card produced, into `## Outcome`.

**It APPENDS, never overwrites** — the same law a ruling carries. A card
worked twice has two outcomes and the second does not supersede the first.

An outcome is what happened, not why. The body carries rulings; an outcome
that starts arguing duplicates them. Write it as the card leaves `doing`,
not reconstructed afterwards from memory.

**Name your model.** `record_outcome(..., model="Opus 5")` — every entry
carries a line saying who wrote it. A board is worked by more than one
model over its life, and by one whose quality moves under it; without
attribution that difference reads as "the board got worse" with nothing
to point at. The harness is read from the environment and cannot be
misreported. The model is knowable only to you, so pass it. Omitting it
writes "model unrecorded", which is visible on purpose — a gap you cannot
see is a gap nobody closes.

**The outcome is a self-report.** It explains; it does not prove. The
evidence is the version history and a green verify.

## Prose is the owner's

You may append through the doors. You may not tidy, reflow or rewrite what
the owner wrote. A card whose prose carries an unclosed fence is a card
you surface, not one you repair.

## The loop

`amik work --once` works the top of Ready, if the project is armed.

**`armed` is re-read every tick**, never cached — disarming is a one-line
edit that takes effect on the next card, not a daemon to find and
restart. Absent means false and only a real boolean opens it: a gate a
typo can open is not a gate.

**One card at a time, enforced by a lock.** The tree is a shared working
directory and two agents editing it at once is a half-applied merge. A
dead holder's lock is reclaimed by pid, not by a timeout — a card can
legitimately take an hour.

**The agent is named by the project, not by Amik.** `[agent] command` in
`amik.toml`, and the prompt goes to its STDIN: every CLI has stdin, no
two spell a prompt the same way in flags. A card may name its own
`model`, which is an explicit choice ON the card — never inferred from
its text, because judging a card's difficulty in advance is the
judgement nobody makes reliably.

**Each card gets a fresh agent and a small brief** — the card, the laws
file, the verify command. Not the project. A persistent session accretes
the whole repository and pays for it on every tick.

**Cheapest check first.** Armed, then whether the board moved, then
whether there is a take, then spawn. The first three are free. The rule
is not "never a timer" — it is never wake a PAID step on one.
