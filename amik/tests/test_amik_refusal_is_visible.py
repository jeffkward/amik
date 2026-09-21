"""A refused write says so where the owner is looking.

The board page carries an alert banner, and until now it was the only
place a refusal was reported. But a card is edited inside a <dialog>
opened with showModal(), which puts it in the browser's TOP LAYER and
paints a backdrop over the page beneath it. A banner on the page is
therefore unreachable -- not scrolled off, not subtle, covered -- for
exactly the period when the most refusals happen.

The symptom is not a wrong message. It is Save appearing to do nothing
at all, which sends you looking for a broken button instead of reading
the reason the server already gave.
"""

from tests.test_amik_page import _js


def _rendered(scenario):
    """The real page, not the template: both banners are emitted by the
    callout macro, so the ids exist only once Jinja has run."""
    from amik.app.handle import handle
    root = scenario("ready_plain")
    status, _, body = handle("GET", "/", {}, b"", root, "")
    assert status == 200, status
    return body.decode() if isinstance(body, bytes) else body


def _dialog_markup(html):
    """Everything between the card dialog's open tag and its close."""
    start = html.index('<dialog id="akdlg"')
    end = html.index("</dialog>", start)
    return html[start:end]


def test_the_refusal_banner_lives_inside_the_card_dialog(scenario):
    html = _rendered(scenario)
    assert 'id="akdlgmsg"' in html, "no in-dialog banner at all"
    assert 'id="akdlgmsg"' in _dialog_markup(html), (
        "the banner is on the page, which the dialog's backdrop covers")


def test_the_page_banner_is_still_outside_it(scenario):
    """Writes that happen with no card open -- a drag, the quick-add --
    have nothing in the top layer to paint into."""
    html = _rendered(scenario)
    assert 'id="akstale"' in html
    assert 'id="akstale"' not in _dialog_markup(html)


def test_the_transport_paints_both():
    """One sentence, both layers. A refusal reported to only one of them
    is invisible for half the ways a write can be started."""
    src = _js("amik.js")
    assert "akdlgmsg" in src and "akstale" in src
    body = src[src.index("window.akBanners"):src.index("window.akSend")]
    assert "akstale" in body and "akdlgmsg" in body


def test_a_refusal_does_not_follow_you_to_the_next_card():
    """The banner is hidden again when a card opens, or the last card's
    failure reads as this one's."""
    src = _js("amik.js")
    opening = src[src.index("clean = snapshot();"):src.index("dlg.showModal()")]
    assert "akQuiet" in opening, opening
