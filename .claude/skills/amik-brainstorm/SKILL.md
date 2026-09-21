---
name: amik-brainstorm
description: Discharge an Amik card that owes a brainstorm — read the card, think it through with the owner, write the plan, and record it back on the board so the queue can take it. Use this whenever someone names an Amik card id and wants to think about it, says a card "needs a brainstorm" or is "blocked on design", asks what to do about a card the queue is skipping, or wants to plan a card before it is built. Also use it when a board reports a card skipped for a blocking rung. Do NOT use it for working a card that is already planned, for ordinary brainstorming with no card behind it, or for questions about how Amik itself works.
user-invocable: true
---

# /amik-brainstorm

*Ships with Amik at `.claude/skills/amik-brainstorm/`. Working in a
project that ADOPTED Amik rather than in Amik itself? Copy this file
into that project's own `.claude/skills/` — Amik writes nothing outside
its own folder, so it will not put it there for you.*

Amik tracks that thinking is owed. It does not host the thinking, and it
will not pretend to. A card carrying `needs-brainstorm` is skipped by
the queue and says why, and it stays there until a person decides
something.

This skill is the round trip: board → conversation → board.

## The shape of it

1. **Find the card.** The id is the handle. If you were given one, use
   it. If you were given a description, `amik status` names what the
   queue is skipping and why.
2. **Read it before thinking about it.** The card's prose is the brief,
   and its questions are decisions already asked for by name.
3. **Think it through with the owner**, using the
   `superpowers:brainstorming` skill. That skill owns the process —
   classify the work, ask one question at a time, propose approaches,
   present a design, get approval. Do not restate it here; invoke it.
4. **Write the plan where the build can open it.** A repo-relative
   markdown file, in whatever docs directory the project already uses.
5. **Record it on the board**, which is the step that unblocks the card.

## Reading the card

```bash
amik --root <project> status          # what is skipped, and why
amik --root <project> log --card <id> # what has happened to it
```

The card's prose lives at `<project>/amik/cards/<id>.md`. Read it
directly. A `## Questions` section holds decisions someone already
asked for — those are the brainstorm's agenda, not extra work.

## Recording the result

```bash
amik --root <project> plan <id> --doc docs/the-plan.md
```

That sets the rung to `has-plan` and names the document, which is what
takes the card off the blocked list. Both halves matter: the rung
claims a plan exists and the document is where it is named, so a rung
without one draws "plan not named" on the card.

Sometimes the honest answer is that no plan is needed:

```bash
amik --root <project> plan <id> --clear
```

"Thought about it, nothing to write down" is a real result. The rung
says what a card still *owes*, and a card that owes nothing carries
none.

If the conversation turns up a question only the owner can settle,
`ask` puts it on the card and holds it there rather than guessing:

```bash
amik --root <project> ask <id> "Which store?" --context "what you know"
```

## Two things not to do

**Do not move the card to Ready.** That is the owner's pull, always,
and it is the one rule in this board that nothing else may take. Clear
the rung and leave the card where it is; they will pull it when they
want it next.

**Do not build it.** A brainstorm ends with a plan, not a branch. The
card gets worked later, by an agent reading the document you wrote —
which is the whole reason the plan has to be a file rather than a
conversation nobody can reopen.

## When the plan is the interesting part

A plan good enough to build from says what to do and why the
alternatives lost. If the conversation settled something by ruling
against an option, write that down — a plan that records only the
winner invites the same argument again in three weeks.
