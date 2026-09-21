"""What the bar says, and when a card is shown as being worked.

Three things that were all one mistake: a board that could never be
worked said nothing about it, a card sitting in Doing on such a board
claimed an agent had it, and the branch pill was labelled with a count
of commits rather than being the thing you click.
"""

import os

from tests.test_amik_page import _board

ROW = {"id": "a", "title": "T", "status": "doing", "planning": None,
       "rank": 1, "created_at": "2026-09-14", "updated_at": "2026-09-14"}

WORKS = 'verify = "true"\narmed = true\n[agent]\ncommand = "an-agent"\n'
PAUSED = 'verify = "true"\narmed = false\n[agent]\ncommand = "an-agent"\n'


def _toml(root, text):
    os.makedirs(os.path.join(root, "amik"), exist_ok=True)
    with open(os.path.join(root, "amik", "amik.toml"), "w",
              encoding="utf-8") as f:
        f.write(text)


# ── the spinner tells the truth ─────────────────────────────────────

def test_a_board_no_agent_can_work_shows_NO_spinner(instance, client):
    """The lie this closes. `doing` is the agent's column, but a board
    with nothing declared has no agent to be in it -- and a card lands
    there by hand, which is the whole of the manual board."""
    _board(instance, [ROW])
    html = client.get("/amik").text
    assert "akworking" not in html
    assert "An agent is working this card" not in html


def test_PAUSING_DOES_NOT_HIDE_A_CARD_ALREADY_RUNNING(instance, client):
    """The page's own pause message promises the card in Doing will
    finish. Hiding its spinner would contradict the sentence this
    application shows two clicks earlier."""
    _board(instance, [ROW])
    _toml(instance, PAUSED)
    assert "akworking" in client.get("/amik").text


def test_the_reader_is_what_decides(empty_board):
    """Not the template. Anything else reading `working` -- the pause
    message counts cards in Doing -- has to get the same answer."""
    from amik.core import board
    _toml(empty_board, WORKS)
    from conftest import write_board
    write_board(empty_board, [ROW])
    row = next(c for col in board.amik(empty_board)["data"]["columns"]
               for c in col["cards"])
    assert row["working"] is True
    _toml(empty_board, 'armed = true\n')
    row = next(c for col in board.amik(empty_board)["data"]["columns"]
               for c in col["cards"])
    assert row["working"] is False

