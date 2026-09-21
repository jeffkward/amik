"""Reaching the two verbs from the board.

Abandon has no route of its own on purpose: a card reaches `abandoned`
by being DRAGGED there far more often than by any button, so the cleanup
belongs to the destination rather than to one way in. Otherwise a card
dropped with the gesture keeps its ref and one dropped with the button
does not, which is the kind of difference nobody discovers until they
are looking for a branch that should not exist.
"""

import json
import os

from amik.core import git


def _row(root):
    for line in open(os.path.join(root, "amik", "board.jsonl")):
        if line.strip():
            return json.loads(line)


def _fp(client):
    body = client.get("/amik").text
    return body.split('data-fingerprint="', 1)[1].split('"', 1)[0]


def test_discarding_over_http_returns_the_card_to_ready(repo_with_card):
    from amik.app.handle import handle
    status, _, _ = handle("DELETE", "/cards/a-card/work", None, b"",
                          root=repo_with_card, base="")
    assert status == 200
    assert _row(repo_with_card)["status"] == "ready"
    assert not git.branch_exists(repo_with_card, "card/a-card")


def test_DRAGGING_to_abandoned_drops_the_branch(repo_with_card):
    """The gesture, not the verb. This is the path that would have been
    missed by giving abandon its own route."""
    from amik.app.handle import handle
    body = b"to_status=abandoned&to_index=0"
    status, _, _ = handle("PATCH", "/cards/a-card/position", None, body,
                          root=repo_with_card, base="")
    assert status == 200
    assert _row(repo_with_card)["status"] == "abandoned"
    assert not git.branch_exists(repo_with_card, "card/a-card")


def test_dragging_ELSEWHERE_leaves_the_branch_alone(repo_with_card):
    """Only a close cleans up. A card moved to Doing is still in play."""
    from amik.app.handle import handle
    handle("PATCH", "/cards/a-card/position", None,
           b"to_status=doing&to_index=0", root=repo_with_card, base="")
    assert git.branch_exists(repo_with_card, "card/a-card")


def test_the_route_404s_without_a_board(instance):
    from amik.app.handle import handle
    status, _, _ = handle("DELETE", "/cards/x/work", None, b"",
                          root=str(instance), base="")
    assert status == 404
