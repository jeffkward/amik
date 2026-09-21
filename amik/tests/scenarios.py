"""Boards to test against — every state a board can actually reach.

Deliberately generic. Not one card here comes from the project Amik grew
up in: these are a plausible small web project's cards, so the suite reads
the same to someone who has never seen that project, and so a fixture can
never quietly become documentation of somebody's private work.

Two kinds of state are covered, because two hands move this board:

  · what an OWNER can do — file a card, drag it anywhere, shelve it,
    close it against, answer a question, hand-edit the file into a shape
    no door would have written
  · what an AGENT can do — take the top of Ready, ask, record an outcome,
    halt on a failed verify, leave a branch behind

`board(*names)` assembles any subset. Each scenario is one card; a few
carry prose, and the prose is part of the scenario because questions and
outcomes live there rather than on the row.
"""

CARDS = {}


def _card(name, *, body=None, **row):
    row.setdefault("title", name.replace("_", " ").capitalize())
    row.setdefault("planning", None)
    CARDS[name] = (row, body)


# ── the ordinary lifecycle, one card per column ──────────────────────
_card("inbox_plain", id="add-a-dark-mode-toggle", status="inbox", rank=1,
      title="Add a dark mode toggle", group="ui")
_card("todo_plain", id="cache-the-search-index", status="todo", rank=1,
      title="Cache the search index", group="backend")
_card("ready_plain", id="rename-the-export-button", status="ready", rank=1,
      title="Rename the export button", group="ui")
_card("doing_plain", id="split-the-settings-page", status="doing", rank=1,
      title="Split the settings page", group="ui")
_card("review_plain", id="retry-failed-uploads", status="review", rank=1,
      title="Retry failed uploads", group="backend")
_card("done_plain", id="fix-the-timezone-offset", status="done", rank=1,
      title="Fix the timezone offset", group="backend",
      body="The offset was applied twice on import.\n\n"
           "## Outcome\n\nOne line in the parser. Covered by a test.\n")

# ── the owner shelving and closing ───────────────────────────────────
_card("someday_shelved", id="rewrite-the-css-from-scratch", status="someday",
      rank=1, title="Rewrite the CSS from scratch", group="ui",
      body="Not worth it while the design is still moving.\n\n"
           "**Back when.** The design stops changing weekly.\n")
_card("abandoned_plain", id="support-internet-explorer", status="abandoned",
      rank=1, title="Support Internet Explorer", group="ui")
# `retired` was a `closed_as` value until 2026-09-17. It is prose now,
# which is where every other ruling on this board lives -- and this
# fixture exists to prove a closed card with a ruling still renders as
# an ordinary abandoned card.
_card("abandoned_retired", id="preload-every-avatar", status="abandoned",
      rank=2, title="Preload every avatar", group="frontend",
      body="Measured: preloading made first paint slower, not faster.\n\n"
           "**Ruling.** Retired -- measured and disproven.\n")

# ── the readiness ladder ─────────────────────────────────────────────
_card("todo_needs_brainstorm", id="decide-the-plugin-boundary", status="todo",
      rank=2, title="Decide the plugin boundary", planning="needs-brainstorm",
      group="architecture")
_card("ready_has_plan", id="move-uploads-to-object-storage", status="ready",
      rank=2, title="Move uploads to object storage", planning="has-plan",
      group="backend", docs="docs/plans/uploads.md")

# ── questions: asked, answered, and the shapes that go wrong ─────────
_card("blocked_unanswered", id="pick-a-migration-tool", status="blocked",
      rank=1, title="Pick a migration tool", group="backend",
      body="Two candidates, and the choice is hard to reverse.\n\n"
           "## Questions\n\n### Which migration tool?\n\n"
           "> One is batteries-included and opinionated. The other is a\n"
           "> thin wrapper we would own. Both are fine; the difference is\n"
           "> who fixes it at 2am.\n")
_card("blocked_half_answered", id="choose-a-queue-backend", status="blocked",
      rank=2, title="Choose a queue backend", group="backend",
      body="## Questions\n\n### Redis or Postgres?\n\nPostgres — one less\n"
           "thing to run.\n\n### Who gets paged when it backs up?\n\n")
_card("ready_answered", id="add-a-health-endpoint", status="ready", rank=3,
      title="Add a health endpoint", group="backend",
      body="## Questions\n\n### Should it check the database?\n\n"
           "Yes — a health check that does not touch the db reports\n"
           "healthy while every request fails.\n")
_card("ready_two_questions", id="split-the-api-client", status="ready", rank=4,
      title="Split the API client", group="frontend",
      body="## Questions\n\n### Split by resource or by verb?\n\n"
           "By resource.\n\n### Keep the old export?\n\n"
           "> It has two known callers.\n")

# ── contradictions the board SURFACES rather than corrects ───────────
_card("conflict_ready_blocking", id="design-the-audit-log", status="ready",
      rank=5, title="Design the audit log", planning="needs-brainstorm",
      group="architecture")
_card("conflict_plan_no_doc", id="shard-the-job-queue", status="ready",
      rank=6, title="Shard the job queue", planning="has-plan",
      group="backend")
_card("conflict_question_column", id="tidy-the-error-copy", status="todo",
      rank=3, title="Tidy the error copy", group="ui",
      body="## Questions\n\n### Which tone?\n\n")
_card("duplicate_heading", id="rotate-the-api-keys", status="ready", rank=7,
      title="Rotate the API keys", group="security",
      body="## Questions\n\n### When?\n\nQuarterly.\n\n### When?\n\n")

# ── the handling toggles, and what an agent leaves behind ────────────
_card("halt_in_review", id="upgrade-the-router", status="review", rank=2,
      title="Upgrade the router", group="frontend", halt=True,
      body="## Outcome\n\nGreen on the branch. Not merged — paused for a\n"
           "look before it lands.\n")
# Every card branches since 2026-09-17, so this fixture is a card that
# HAS a branch rather than one asking for one -- which is the state the
# board actually carries now.
# rank 4, not 8. It read 8 until 2026-09-20 -- a Ready rank left behind
# when the card was moved -- which made `review` rank 1,2,8,3 and the
# assembled board the one shape no real board can be: a column the door
# would have renumbered. Harmless while this was only a component
# catalogue; wrong the moment anything asserts contiguity over it.
_card("on_a_branch", id="replace-the-date-picker", status="review", rank=4,
      title="Replace the date picker", group="ui",
      branch="card/replace-the-date-picker")
_card("done_with_branch", id="extract-the-mailer", status="done", rank=2,
      title="Extract the mailer", group="backend",
      branch="card/extract-the-mailer",
      body="## Outcome\n\nBuilt on a branch, green, waiting to be landed.\n")
_card("prototype_card", id="try-a-compact-card-layout", status="review", rank=3,
      title="Try a compact card layout", group="ui",
      requires_prototype=True, halt=True)
_card("agent_working", id="tighten-the-csv-parser", status="doing", rank=2,
      title="Tighten the CSV parser", group="backend", raised_by="agent")
_card("two_outcomes", id="speed-up-the-dashboard", status="done", rank=3,
      title="Speed up the dashboard", group="frontend",
      body="## Outcome\n\nFirst pass: cached the aggregate.\n\n---\n\n"
           "Second pass, after review: the cache was the wrong layer.\n")

# ── prose an owner hand-edited into a shape no door would write ──────
_card("unclosed_fence", id="document-the-webhook", status="todo", rank=4,
      title="Document the webhook", group="docs",
      body="Example payload:\n\n```json\n{\"event\": \"ping\"}\n")
_card("fenced_heading", id="explain-the-retry-policy", status="todo", rank=5,
      title="Explain the retry policy", group="docs",
      body="The doc should show a heading, like:\n\n```\n## Questions\n```\n\n"
           "...without that being one.\n")
_card("no_prose", id="bump-the-node-version", status="todo", rank=6,
      title="Bump the node version", group="ops")
_card("no_group", id="something-unfiled", status="inbox", rank=2,
      title="Something unfiled")
_card("unranked", id="arrived-without-a-rank", status="inbox",
      title="Arrived without a rank")


def board(*names):
    """The rows and prose for a named subset, in the order given."""
    if not names:
        names = tuple(CARDS)
    rows, prose = [], {}
    for n in names:
        row, body = CARDS[n]
        rows.append(dict(row))
        if body:
            prose[row["id"]] = body
    return rows, prose


def every():
    """Every scenario. What the render test walks, so a component that
    only appears in a rare state is still exercised."""
    return board(*CARDS)
