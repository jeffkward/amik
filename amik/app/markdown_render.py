"""Markdown, small and dependency-free.

Enough for what a card holds: paragraphs, emphasis, code, lists, links
and fenced blocks. Input is escaped FIRST and markup is built after, so
the escaping cannot be undone by a later substitution.

Not a CommonMark implementation and not trying to be. A board's prose is
written by the people and agents working it, and the failure this guards
against is a stray angle bracket, not an exotic nesting case.

Links are ordinary markdown. There is no wiki syntax and no resolver:
a board's prose points at files and URLs, and a link that needs a lookup
table to mean anything is a link the next reader cannot follow.
"""
import html
import re


def markdown(text):
    """Tiny markdown → HTML: paragraphs, **bold**, *italics* and - lists.
    No external deps; input is escaped first."""
    out = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue
        # Runs of bullets become lists WHEREVER they sit in the block.
        # Requiring the whole block to be bullets meant the commonest
        # shape in the fleet's own output — a bold lead line and then
        # items — collapsed into one paragraph with the dashes inline.
        run, is_list = [], False

        def _flush(run, is_list):
            if not run:
                return
            if is_list:
                items = "".join(f"<li>{inline_markdown(' '.join(item))}</li>"
                                for item in run)
                out.append(f"<ul>{items}</ul>")
            else:
                out.append(f"<p>{inline_markdown(' '.join(run))}</p>")
        for line in lines:
            if line.startswith(("- ", "* ")):
                if not is_list:
                    _flush(run, is_list)
                    run, is_list = [], True
                run.append([line[2:]])
            elif is_list:
                # A wrapped bullet continues its item. This prose is
                # hand-written at about 72 columns, so most items run to
                # a second line, and treating one as a paragraph of its
                # own closed the list and left the rest of the sentence
                # hanging under it.
                run[-1].append(line)
            else:
                run.append(line)
        _flush(run, is_list)
    return "\n".join(out)


def inline_markdown(s):
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    return s
