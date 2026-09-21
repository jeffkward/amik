"""One home for the rule that decides what a heading is.

A card's prose is hand-written markdown, and a model answering a question
fills it with fenced code constantly. A heading matcher that only looks at
line prefixes cannot tell a real `### ` heading from one quoted inside a
fenced block -- so every caller that walks a card's structure needs to
know where the fences are, not just where the headings are.
"""


def walk(prose):
    """Yield `(index, stripped_line, in_fence)` for every line of `prose`.

    `stripped_line` is right-stripped only, matching how a heading prefix
    is matched elsewhere: `"### "` has to appear at the start of the line
    as written, not after collapsing leading indentation.

    `in_fence` is true for a line strictly between a fence's open and
    close markers -- the marker lines themselves read `False`, since they
    are punctuation, not content. A fence opens on a line whose stripped
    form starts with ``` or `~~~` and closes on the next such line. An
    unclosed fence swallows everything after it: that is what a markdown
    renderer does too, so a caller that agrees with it keeps the page and
    the data saying the same thing.
    """
    lines = str(prose).split("\n")
    in_fence = False
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            yield i, stripped, False
            continue
        yield i, stripped, in_fence


def heading_text(stripped, prefix):
    """The heading text a stripped line declares under `prefix` (`"## "`
    or `"### "`), or None when the line does not carry that prefix at
    all.

    Whatever follows the prefix, stripped -- not a rebuilt `prefix +
    heading` compared with `==`, which agrees with neither a heading that
    carries inner whitespace nor this function's own callers unless they
    all go through it.
    """
    if not stripped.startswith(prefix):
        return None
    return stripped[len(prefix):].strip()


# The sections the card modal promotes to tabs of their own. A card's
# BODY is the prose before them: rendering them as prose as well would
# show the same text twice on one card.
PROMOTED = ("## Questions", "## Outcome")


def split_promoted(prose):
    """`(body, promoted)` -- a card's own prose, and the sections that
    have tabs of their own.

    The split is the FIRST promoted heading rather than each section cut
    out where it sits. Both writers append, so a promoted section runs to
    the end of the file on every card that has one; taking the first
    heading as the boundary gives the reader that RENDERS a body and the
    writer that puts an edited one back a single rule to agree on, which
    is what stops a save splicing over what the page just showed.

    Prose written after a promoted section therefore rides in `promoted`
    -- out of the body editor's reach, kept verbatim rather than moved,
    because the prose is the owner's and a reorder is a rewrite.

    Fence-aware through `walk`: a heading quoted inside a fenced block is
    content, not structure.
    """
    lines = str(prose).split("\n")
    for i, stripped, fenced in walk(prose):
        if not fenced and stripped in PROMOTED:
            return "\n".join(lines[:i]), "\n".join(lines[i:])
    return str(prose), ""


def context_span(lines):
    """How many of `lines` are the asker's CONTEXT, not the answer.

    A question's body is `> quoted` context written by whoever asked,
    then the owner's answer. The boundary: skip leading blanks, then take
    the contiguous run of blockquote lines; the first line that is
    neither blank nor quoted begins the answer, and nothing after it can
    be reclassified. A body with no leading quote has no context at all.

    The span ends at the LAST quote line, so a blank after it belongs to
    the answer region -- where it strips to nothing, and where a writer
    splicing an answer in wants the room.

    Reader and writer must agree on this or a save splices over the
    context the page just rendered, so it lives here rather than in
    either of them. One known edge, and it fails safe: an ANSWER that
    opens with a quote reads as context, which leaves the question
    unanswered and the card held -- the queue declines to take a card
    rather than taking one nobody answered.
    """
    last = 0
    for i, line in enumerate(lines):
        stripped = str(line).strip()
        if not stripped:
            continue
        if not stripped.startswith(">"):
            break
        last = i + 1
    return last
