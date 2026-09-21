"""No row on the live board carries a retired rung.

This is the ratchet under the migration. Without it a hand edit or an
older tool can reintroduce a spelling the ladder no longer has, and the
board would render a state that does not exist.
"""
import json
import os

from amik.core import edit as amik_edit
from conftest import INSTANCE as ROOT

RETIRED = ("brainstorm-needed", "decision-needed", "brainstorm-complete",
           "plan-exists", "build-ready", "just-do-it")


def test_the_live_board_carries_no_retired_rung():
    path = os.path.join(ROOT, "amik", "board.jsonl")
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            rung = json.loads(line).get("planning")
            assert rung not in RETIRED, f"line {n}: {rung}"


def test_every_rung_on_the_live_board_is_on_the_ladder():
    path = os.path.join(ROOT, "amik", "board.jsonl")
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            rung = json.loads(line).get("planning")
            assert rung is None or rung in amik_edit.RUNGS, f"line {n}: {rung}"
