"""One home for the rule that decides what a heading is.

It lived in three places — shared between the two section writers, and
separately inline in the reader — which is how a rule drifts. Fence
awareness would have made that four.
"""
from amik.core import markdown as amik_markdown


FENCED = '''## Questions

### How do I parse a fence?

Like this:

```python
### not a question, this is code
def f(): pass
```

That is the whole answer.
'''


def test_a_heading_inside_a_fence_is_not_a_heading():
    """A model writing an answer emits fenced code constantly, and a
    line-based parser cannot tell markup from a quoted example of it."""
    inside = [line for _, line, fenced in amik_markdown.walk(FENCED)
              if fenced and line.startswith("###")]
    assert inside == ["### not a question, this is code"]


def test_the_real_heading_is_still_found():
    live = [line for _, line, fenced in amik_markdown.walk(FENCED)
            if not fenced and line.startswith("### ")]
    assert live == ["### How do I parse a fence?"]


def test_a_tilde_fence_counts_too():
    prose = "~~~\n### in a tilde fence\n~~~\n### real\n"
    live = [line for _, line, fenced in amik_markdown.walk(prose)
            if not fenced and line.startswith("### ")]
    assert live == ["### real"]


def test_an_unclosed_fence_swallows_the_rest():
    """Deliberate: an unclosed fence is what the markdown renderer will
    do too, so the parser agreeing with it keeps the page and the data
    saying the same thing."""
    prose = "```\n### never closed\n### also inside\n"
    live = [line for _, line, fenced in amik_markdown.walk(prose)
            if not fenced and line.startswith("### ")]
    assert live == []


def test_a_heading_after_a_closed_backtick_fence_is_found():
    """Every fixture above puts the real heading BEFORE the fence, so a
    close check that only worked for `~~~` would still pass all of them.
    A heading that comes AFTER a closed ``` fence is the one shape that
    needs the backtick close to actually fire, rather than leaving the
    rest of the document fenced forever."""
    prose = "```\nfenced\n```\n\n### real\n"
    live = [line for _, line, fenced in amik_markdown.walk(prose)
            if not fenced and line.startswith("### ")]
    assert live == ["### real"]


def test_heading_text_strips_the_prefix():
    assert amik_markdown.heading_text("### Two  spaces", "### ") == "Two  spaces"
    assert amik_markdown.heading_text("## Review", "### ") is None
