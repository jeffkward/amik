"""The loop that works the board.

Everything here is about REFUSING correctly. A loop's dangerous states
are the ones where it runs when it should not — unarmed, twice at once,
on a board that is paused — and each of those is cheaper to test than the
one state where it works.

No test in this file spawns an agent. `run_agent` is the only thing that
does, and it is called with a command the fixtures set to something
harmless.
"""
import json
import os
import subprocess
import sys

import pytest

from amik import loop
from amik.core import board

ROWS = [{"id": "a-card", "title": "A card", "status": "ready",
         "planning": None, "rank": 1, "created_at": "2026-01-01T00:00:00",
         "updated_at": "2026-01-01T00:00:00"}]


def _toml(root, **kw):
    lines = ['verify = "true"', 'laws = "LAWS.md"']
    if kw.get("name"):
        lines.append('name = "{}"'.format(kw["name"]))
    if kw.get("armed"):
        lines.append("armed = true")
    if kw.get("agent"):
        lines.append("[agent]")
        lines.append('command = "{}"'.format(kw["agent"]))
    if (kw.get("notify") or kw.get("transcript") or kw.get("ceiling")
            or kw.get("notify_on") is not None):
        lines.append("[loop]")
        if kw.get("notify"):
            lines.append('notify = "{}"'.format(kw["notify"]))
        # A raw TOML literal, not a Python list: half of what this key has
        # to survive is being written WRONG, and a helper that only
        # emitted well-formed arrays could not express that.
        if kw.get("notify_on") is not None:
            lines.append("notify_on = {}".format(kw["notify_on"]))
        if kw.get("transcript"):
            lines.append("transcript = true")
        if kw.get("ceiling"):
            lines.append("ceiling = {}".format(kw["ceiling"]))
    with open(os.path.join(root, "amik", "amik.toml"), "w") as f:
        f.write("\n".join(lines) + "\n")
    return root


@pytest.fixture()
def ready(instance):
    from conftest import write_board
    write_board(instance, ROWS)
    with open(os.path.join(instance, "LAWS.md"), "w") as f:
        f.write("# The laws\n\nBe careful.\n")
    return instance


# ── the gates, cheapest first ────────────────────────────────────────


def test_an_unarmed_project_does_nothing(ready):
    """The first gate and the loudest. Absent means false and only a real
    boolean arms it — a gate a typo can open is not a gate."""
    _toml(ready)
    assert loop.work_once(ready) == {"did": None, "why": "not armed"}


def test_armed_is_re_read_every_tick_not_cached(ready):
    """Cached, disarming means finding and restarting a daemon at the
    moment someone already wants it stopped."""
    _toml(ready, armed=True)
    assert loop.armed(ready) is True
    _toml(ready)                                   # rewrite without it
    assert loop.armed(ready) is False


def test_a_project_that_declares_no_verify_cannot_be_worked(ready):
    with open(os.path.join(ready, "amik", "amik.toml"), "w") as f:
        f.write("armed = true\n")
    res = loop.work_once(ready)
    assert res["did"] is None and "verify" in res["why"]


def test_nothing_workable_is_an_answer_not_a_fault(instance):
    from conftest import write_board
    write_board(instance, [dict(ROWS[0], status="todo")])
    _toml(instance, armed=True, agent="true")
    res = loop.work_once(instance)
    assert res["did"] is None
    assert "nothing in Ready" in res["why"]


def test_a_paused_queue_says_which_card_paused_it(instance):
    """A halt is a gate the owner set. The loop reports the gate rather
    than reporting an empty queue, which would read as "no work"."""
    from conftest import write_board
    write_board(instance, [
        dict(ROWS[0], status="review", halt=True, id="the-gate"),
        dict(ROWS[0], id="behind-it")])
    _toml(instance, armed=True, agent="true")
    res = loop.work_once(instance)
    assert res["did"] is None
    assert "the-gate" in res["why"]


def test_a_dry_run_names_the_card_and_spawns_nothing(ready):
    _toml(ready, armed=True, agent="false")   # would fail if it ran
    res = loop.work_once(ready, dry_run=True)
    assert res["would"] == "a-card" and res["did"] is None


# ── one card at a time ───────────────────────────────────────────────


def test_a_second_worker_is_refused_while_the_first_holds_the_lock(ready):
    """The tree is one shared working directory. Two agents editing it at
    once is a half-applied merge waiting to happen."""
    _toml(ready, armed=True, agent="true")
    with loop.Lock(ready, "a-card"):
        res = loop.work_once(ready)
    assert res["did"] is None
    assert "already being worked" in res["why"]


def test_a_dead_holders_lock_is_reclaimed(ready):
    """A crashed run must not wedge the board forever. Liveness is the
    pid, not a timeout — a card can legitimately take an hour."""
    _toml(ready, armed=True, agent="true")
    os.makedirs(os.path.join(ready, "amik"), exist_ok=True)
    with open(os.path.join(ready, "amik", ".lock"), "w") as f:
        json.dump({"pid": 999999, "card": "old", "since": "then"}, f)
    assert loop.work_once(ready)["did"] == "a-card"


def test_the_lock_is_released_even_when_the_agent_fails(ready):
    _toml(ready, armed=True, agent="false")
    loop.work_once(ready)
    assert not os.path.exists(os.path.join(ready, "amik", ".lock"))


# ── what the agent is handed ─────────────────────────────────────────


def test_the_prompt_carries_the_card_the_laws_and_the_verify(ready):
    """The card, not the project. A persistent session accretes the whole
    repository and pays for it every tick; a fresh invocation reads only
    what this card needs."""
    _toml(ready, armed=True, agent="true")
    project = board.amik_project(ready)["data"]
    card = board.amik_queue(ready)["data"]["take"]
    text = loop.prompt(ready, card, project)
    assert "A card" in text
    assert "Be careful." in text                   # the laws file
    assert project["verify"] in text
    assert "Never merge red." in text


def test_the_prompt_goes_to_stdin_not_argv(ready):
    """Every CLI has stdin; no two spell a prompt the same way in flags,
    and argv has quoting and length limits a card's prose will meet."""
    import unittest.mock as mock
    _toml(ready, armed=True, agent="an-agent --flag")
    project = board.amik_project(ready)["data"]
    card = board.amik_queue(ready)["data"]["take"]
    with mock.patch.object(loop.subprocess, "run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        loop.run_agent(ready, card, project)
    argv, kwargs = run.call_args[0][0], run.call_args.kwargs
    assert argv == ["an-agent", "--flag"], "the command was not split"
    assert "A card" in kwargs["input"], "the prompt did not go to stdin"
    assert not any("A card" in a for a in argv), "the prompt is in argv"


def test_a_card_may_name_its_own_model(ready):
    """Routing is an explicit choice ON the card, never inferred from its
    text — judging difficulty in advance is the judgement nobody makes
    reliably."""
    _toml(ready, armed=True, agent=sys.executable + " -c pass")
    project = board.amik_project(ready)["data"]
    card = dict(board.amik_queue(ready)["data"]["take"], model="haiku")
    import unittest.mock as mock
    with mock.patch.object(loop.subprocess, "run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        loop.run_agent(ready, card, project, model=card["model"])
    assert "--model" in run.call_args[0][0]
    assert "haiku" in run.call_args[0][0]


def test_no_agent_command_is_a_refusal_not_a_guess(ready):
    """Amik names no vendor. A project that has not said what works its
    cards has not said, and guessing `claude` would be the same mistake
    as guessing a test command."""
    _toml(ready, armed=True)
    project = board.amik_project(ready)["data"]
    card = board.amik_queue(ready)["data"]["take"]
    with pytest.raises(ValueError, match="no .agent. command"):
        loop.run_agent(ready, card, project)


# ── the record it leaves ─────────────────────────────────────────────


def test_a_transcript_is_off_unless_asked_for(ready):
    """It is every file the agent read. A default that records that is a
    default nobody inspected."""
    _toml(ready, armed=True, agent="true")
    assert board.amik_project(ready)["data"]["transcript"] is False
    loop.work_once(ready)
    assert not os.path.isdir(os.path.join(ready, "amik", "runs"))


def test_a_transcript_lands_beside_the_board_not_on_the_card(ready):
    """On the card it would bury the prose and make every diff
    unreadable. The card is what a person reads; this is the escape
    hatch."""
    _toml(ready, armed=True, agent="echo hello", transcript=True)
    res = loop.work_once(ready)
    assert res["transcript"] and os.path.isfile(res["transcript"])
    assert "amik/runs/a-card" in res["transcript"].replace(os.sep, "/")
    card = os.path.join(ready, "amik", "cards", "a-card.md")
    assert not os.path.exists(card) or "hello" not in open(card).read()


def test_notify_failing_never_fails_the_run(ready):
    """Telling someone is the last thing that happens and the least
    important. A broken notify command must not turn a worked card into
    a failed one."""
    _toml(ready, armed=True, agent="true",
          notify="/nonexistent/command/that/is/not/there")
    assert loop.work_once(ready)["did"] == "a-card"


def test_no_notify_command_means_silence(ready):
    _toml(ready, armed=True, agent="true")
    assert board.amik_project(ready)["data"]["notify"] == ""


# ── where the card landed ────────────────────────────────────────────


def _tick(root, agent=lambda: None, returncode=0):
    """One tick with the agent replaced, collecting what notify was told.

    Three things go out through `subprocess.run` now — the agent, notify,
    and git, since the reader detects the trunk when the project has not
    declared one. One spy sees all three and tells them apart by the
    command, which is the same thing the caller does.

    Only notify is collected. A git call is machinery, not something
    anybody was told.
    """
    import unittest.mock as mock
    said = []

    def spy(argv, **kw):
        if argv[0] == "the-agent":
            agent()
            return subprocess.CompletedProcess(argv, returncode, "", "")
        if argv[0] == "git":
            return subprocess.CompletedProcess(argv, 1, "", "")
        said.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    with mock.patch.object(loop.subprocess, "run", spy):
        loop.work_once(root)
    return said


def _finish(root, status, outcome=None):
    """What an agent does on its way out: move the card, and say what it
    produced."""
    from amik.core import edit as e

    def done():
        if outcome:
            e.record_outcome(root, "a-card", outcome, model="a model")
        e.move(root, "a-card", status, 0)
    return done


def test_absent_notify_on_means_review_and_blocked(ready):
    """The two columns that mean the loop stopped and is waiting on a
    person. Every other landing is a card that finished and can be read
    whenever."""
    _toml(ready, armed=True, agent="true", notify="say")
    assert board.amik_project(ready)["data"]["notify_on"] == [
        "review", "blocked"]


def test_a_clean_close_says_nothing(ready):
    """A card that closed itself needs nobody. Before this, it arrived the
    same way as one waiting on a human."""
    _toml(ready, armed=True, agent="the-agent", notify="say")
    assert _tick(ready, _finish(ready, "done", "Built it.")) == []


def test_a_card_left_in_review_names_the_card_the_column_and_why(ready):
    _toml(ready, armed=True, agent="the-agent", notify="say")
    said = _tick(ready, _finish(ready, "review", "Verify failed on three "
                                "tests. The rest of it is here."))
    assert len(said) == 1
    line = said[0][-1]
    assert said[0][0] == "say"
    assert "a-card" in line
    assert "review" in line
    assert "Verify failed on three tests." in line
    assert "The rest of it" not in line          # one sentence, not a page


def test_a_DECLARED_NAME_says_which_board_spoke(ready):
    """Two boards are two servers, and Amik says so itself -- but one
    person can point both at the same notifier rather than run a second
    bot for the second board. Without the name the two are
    indistinguishable: a card id and a column say nothing about which
    project they belong to."""
    _toml(ready, armed=True, agent="the-agent", notify="say",
          name="Niiwin Lite")
    line = _tick(ready, _finish(ready, "review", "Verify failed."))[0][-1]
    assert line.startswith("Niiwin Lite")
    assert "a-card" in line and "review" in line


def test_an_UNDECLARED_name_changes_nothing(ready):
    """Amik guesses no name anywhere else and will not start here. One
    board pointed at one notifier needs no prefix, and an empty one
    would be a separator with nothing in front of it."""
    _toml(ready, armed=True, agent="the-agent", notify="say")
    line = _tick(ready, _finish(ready, "review", "Verify failed."))[0][-1]
    assert line.startswith("amik worked")


def test_blocked_is_announced_too(ready):
    _toml(ready, armed=True, agent="the-agent", notify="say")
    assert _tick(ready, _finish(ready, "blocked", "It needs a ruling.")) != []


def test_a_listed_column_can_be_any_column(ready):
    """Someone who wants every close lists more. The default is a default,
    not the set of columns Amik is willing to talk about."""
    _toml(ready, armed=True, agent="the-agent", notify="say",
          notify_on='["done"]')
    assert _tick(ready, _finish(ready, "done", "Built it.")) != []
    assert _tick(ready, _finish(ready, "review", "Waiting.")) == []


def test_an_empty_list_is_silence_without_deleting_the_command(ready):
    """Going quiet must not cost the string you will want back."""
    _toml(ready, armed=True, agent="the-agent", notify="say", notify_on="[]")
    assert board.amik_project(ready)["data"]["notify"] == "say"
    assert _tick(ready, _finish(ready, "review", "Waiting on you.")) == []


def test_a_typo_falls_back_to_the_default_not_to_silence(ready):
    """`notify_on = "review"` is a string, and a string is iterable — read
    as a list of statuses it would match by substring. The cheap direction
    of this mistake is hearing about a card you did not need to; the
    expensive one is a board waiting on you in a column nothing
    announced."""
    _toml(ready, armed=True, agent="true", notify="say",
          notify_on='"review"')
    assert board.amik_project(ready)["data"]["notify_on"] == [
        "review", "blocked"]


def test_a_column_is_matched_however_it_was_spelled(ready):
    _toml(ready, armed=True, agent="true", notify="say",
          notify_on='[" Review "]')
    assert board.amik_project(ready)["data"]["notify_on"] == ["review"]


def test_a_card_whose_row_vanished_is_always_announced(ready):
    """An unknown landing is not a status anyone configured, and silence
    about a card that went somewhere unreadable is the one thing this
    filter must not buy."""
    from amik.core import edit as e
    _toml(ready, armed=True, agent="the-agent", notify="say")
    said = _tick(ready, lambda: e.delete(ready, "a-card"))
    assert len(said) == 1
    assert "nowhere the board can see" in said[0][-1]


def test_hearing_about_a_failure_means_listening_for_ready(ready):
    """A card the agent failed on is put BACK, so `ready` is the column a
    failure lands in. It is not in the default, which is the price of a
    default built on where a card is rather than on how it got there."""
    _toml(ready, armed=True, agent="the-agent", notify="say")
    assert _tick(ready, returncode=1) == []
    _toml(ready, armed=True, agent="the-agent", notify="say",
          notify_on='["ready"]')
    assert _tick(ready, returncode=1) != []


def test_the_newest_outcome_is_the_one_reported():
    """Outcomes append, so a card worked twice carries both — and the one
    worth telling someone about is the one that just happened."""
    line = loop.landing_line("a-card", "review", "\n".join([
        "Built the first half.", "", "*Worked by an old model*", "",
        "Then it broke.", "", "*Worked by a newer one*"]))
    assert "Then it broke." in line
    assert "first half" not in line


def test_an_outcome_written_before_attribution_existed_still_reads():
    assert "Just this." in loop.landing_line("a-card", "review", "Just this.")


def test_a_sentence_is_not_cut_at_a_version_number_or_a_bolded_word():
    line = loop.landing_line("a-card", "review", "**Built.** Ships in v1.2 "
                             "of the thing. And then more.")
    assert "v1.2 of the thing." in line
    assert "And then more" not in line


def test_a_dry_run_reports_on_an_unarmed_board(ready):
    """"Not armed" is the right answer to "did you work a card" and a
    useless one to "what would you work". Both checks are free, so there
    is no reason to make someone arm the board to find out."""
    _toml(ready)
    res = loop.work_once(ready, dry_run=True)
    assert res["would"] == "a-card"
    assert res["armed"] is False
    assert res["did"] is None


def test_a_dry_run_on_an_unarmed_board_still_spawns_nothing(ready):
    """The reporting must not become a way in. `false` exits 1, so a card
    that was actually worked would be visible in the result."""
    _toml(ready, agent="false")
    res = loop.work_once(ready, dry_run=True)
    assert "returncode" not in res
    assert not os.path.exists(os.path.join(ready, "amik", ".lock"))


def test_the_loop_moves_the_card_to_doing_before_the_agent_starts(ready):
    """One line write, and it is the only thing that tells a person the
    work has begun. Left to the agent it happens whenever that agent gets
    round to reading its instructions — on a large card, minutes of the
    board saying nothing is happening while something is."""
    _toml(ready, armed=True, agent="true")
    import unittest.mock as mock
    seen = {}

    def spy(*a, **kw):
        seen["column"] = next(
            c["status"] for col in board.amik(ready)["data"]["columns"]
            for c in col["cards"] if c["id"] == "a-card")
        return subprocess.CompletedProcess([], 0, "", "")

    with mock.patch.object(loop.subprocess, "run", spy):
        loop.work_once(ready)
    assert seen["column"] == "doing"


def test_a_card_the_agent_failed_on_goes_back_to_ready(ready):
    """`doing` is invisible to the queue, so a card stranded there
    silently stops being work. This restores what the LOOP changed — not
    an agent promoting its own card, which stays forbidden."""
    _toml(ready, armed=True, agent="false")          # exits 1
    loop.work_once(ready)
    col = next(c["status"] for col in board.amik(ready)["data"]["columns"]
               for c in col["cards"] if c["id"] == "a-card")
    assert col == "ready"


def test_a_card_the_agent_moved_itself_is_left_alone(ready):
    """Only a card still sitting in `doing` is put back. One the agent
    moved to `review` or `blocked` on its way out has been placed
    deliberately, and moving it would overwrite a decision."""
    _toml(ready, armed=True, agent="false")
    import unittest.mock as mock

    def spy(*a, **kw):
        from amik.core import edit as e
        e.move(ready, "a-card", "review", 0)
        return subprocess.CompletedProcess([], 1, "", "")

    with mock.patch.object(loop.subprocess, "run", spy):
        loop.work_once(ready)
    col = next(c["status"] for col in board.amik(ready)["data"]["columns"]
               for c in col["cards"] if c["id"] == "a-card")
    assert col == "review"


# ── whose laws ──────────────────────────────────────────────────────

def test_the_brief_carries_AMIKS_OWN_laws_without_being_asked(ready):
    """They are about the BOARD -- what a column means, when a card may
    close, how to ask a question -- and they ship with the package.

    Making every project copy them into its own file would be Amik
    asking to be told something it knows, and every copy would drift
    from the version the code enforces. The example config claimed this
    happened before it did.
    """
    _toml(ready, armed=True, agent="true")
    project = board.amik_project(ready)["data"]
    card = board.amik_queue(ready)["data"]["take"]
    text = loop.prompt(ready, card, project)
    assert "board.jsonl` holds card STATE" in text


def test_the_projects_own_laws_come_AFTER_amiks(ready):
    """Both, in that order. Amik's are the board's rules; the project's
    are everything Amik cannot know."""
    _toml(ready, armed=True, agent="true")
    project = board.amik_project(ready)["data"]
    card = board.amik_queue(ready)["data"]["take"]
    text = loop.prompt(ready, card, project)
    assert "Be careful." in text                       # the project's
    assert text.index("board.jsonl` holds card STATE") < text.index(
        "Be careful.")


def test_a_project_with_no_laws_file_still_gets_amiks(instance):
    """Declaring none is ordinary. It should not cost you the board's
    own rules."""
    from conftest import write_board
    write_board(instance, ROWS)
    with open(os.path.join(instance, "amik", "amik.toml"), "w") as f:
        f.write('verify = "true"\narmed = true\n[agent]\ncommand = "true"\n')
    project = board.amik_project(instance)["data"]
    card = board.amik_queue(instance)["data"]["take"]
    assert "board.jsonl` holds card STATE" in loop.prompt(
        instance, card, project)


# ── the door an agent can actually reach ────────────────────────────

def test_the_brief_NAMES_the_write_door(ready):
    """The fault this closes: the laws say `amik.core.edit` is the only
    writer, and that module is importable in Amik's own repository and
    nowhere else. An agent on a Bun project reached for it, could not,
    and left the card in `doing` having lawfully done nothing."""
    _toml(ready, armed=True, agent="the-agent")
    project = board.amik_project(ready)["data"]
    text = loop.prompt(ready, {"id": "a-card", "title": "A card"}, project)
    assert "-m amik" in text
    for verb in ("move", "outcome", "ask", "halt"):
        assert " " + verb + " <card-id>" in text, verb


def test_the_door_is_named_with_THIS_interpreter(ready):
    """Not the bare `amik` command. A loop started from a virtualenv
    hands its child a PATH that may not carry that console script, and a
    command the agent cannot run is the same as no door at all."""
    import sys as _sys
    assert loop._door(ready).startswith(_sys.executable)


def test_the_door_carries_an_ABSOLUTE_root(ready):
    """An agent that changes directory mid-card would otherwise write to
    whichever board it happened to be standing in."""
    assert " --root /" in loop._door(ready)
