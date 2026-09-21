"""The standalone server: `python3 -m amik.app`.

**Bound to 127.0.0.1, and there is no setting for that.** A board holds a
project's unreleased plans, so exposing it should take deliberate effort
OUTSIDE Amik — an SSH tunnel. A `host` key in a config file is the one
failure mode an open-source dev tool must not ship: committed to a public
repo, permanent, and easy to forget. There is nothing to misconfigure
because there is nothing to configure.
"""
import argparse
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import loop as amik_loop
from ..core import board, init as amik_init

from .handle import handle

HOST = "127.0.0.1"


class _Handler(BaseHTTPRequestHandler):
    server_version = "amik"
    root = "."

    def _run(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        # A cross-origin write is refused here the same way it is in a
        # host: loopback is not a permission model, it is only a smaller
        # audience. A missing Origin is allowed — that is curl, not a
        # browser being driven by someone else's page.
        if method in ("POST", "PATCH", "PUT", "DELETE"):
            origin = (self.headers.get("Origin") or "").lower()
            if origin and origin not in self._allowed():
                self._send(403, {"Content-Type": "text/plain"},
                           b"Forbidden: cross-origin write")
                return
        status, headers, out = handle(method, self.path.split("?", 1)[0],
                                      None, body, root=self.root)
        self._send(status, headers, out)

    def _allowed(self):
        port = self.server.server_address[1]
        return {f"http://{HOST}:{port}", f"http://localhost:{port}"}

    def _send(self, status, headers, out):
        # `out` is bytes, or an iterable of bytes for a streamed response.
        # A stream has no computable length, and a Content-Length that
        # disagrees with the body makes a client wait forever for bytes
        # that are not coming — so a stream sends none and the connection
        # close is the terminator.
        streaming = not isinstance(out, (bytes, bytearray))
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        if not streaming:
            self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        if not streaming:
            self.wfile.write(out)
            return
        # A client going away is how a stream normally ENDS — a closed tab
        # is not an error — so the broken pipe stops the generator rather
        # than taking the thread down with a traceback.
        try:
            for chunk in out:
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        self._run("GET")

    def do_POST(self):
        self._run("POST")

    def do_PATCH(self):
        self._run("PATCH")

    def do_DELETE(self):
        self._run("DELETE")

    def log_message(self, fmt, *args):
        pass                                  # the board is not a weblog


def _seeded_line(res):
    """What the seed did, or nothing at all.

    Empty when a board was already there. Seven files appearing in
    somebody's repository is worth a line; a board that was already
    there is not, and a line about it on every start is one nobody
    reads by the third one.

    A refusal is said rather than swallowed. It is the only place it
    would be said — `init`'s refusal reaches a person through the
    command they typed, and this one has nobody looking.
    """
    if not res["ok"]:
        return "amik: " + res["reason"]
    if not res["data"]["seeded"]:
        return ""
    line = ("amik: no board here, so the starter board was written to "
            + os.path.join(res["data"]["root"], "amik/board.jsonl"))
    if res["data"]["config"]:
        line += "\n      and a config to fill in at amik/amik.toml"
    return line


def _banner(root, port):
    """What this process is, in two lines.

    The second line is load-bearing. Serving and working are one
    process now, and there is no `launchctl list` left to ask whether a
    board is being worked — so a server that is silently not going to
    work anything has to say so at the moment it starts, rather than
    when somebody wonders why nothing happened.

    The reason comes from the same reader `status` asks, so the two
    cannot give different accounts of one board.
    """
    root = os.path.abspath(root)
    # The ladder itself lives in the reader, and this asks it. It used
    # to live here AND in `status`, worded almost the same; the page now
    # needs the same sentence, and a third copy is how one board comes
    # to give two accounts of itself.
    will = board.amik_will_work(root)
    why = ("working cards: yes" if will["ok"]
           else "working cards: no — " + will["reason"])
    return (f"amik → http://{HOST}:{port}  (board: {root})\n"
            f"       {why}")


def serve(root=".", port=4455, loop=True, forever=True):
    """The board, and the loop that works it.

    One process, one port, one board. Two boards are two of these, and
    the port is the only thing they collide on — which is a collision a
    person meets immediately and fixes with a flag, unlike the launchd
    Label this replaced, which collided silently and stopped the first
    board being watched.
    """
    root = os.path.abspath(root)
    _Handler.root = root
    try:
        httpd = ThreadingHTTPServer((HOST, port), _Handler)
    except OSError as exc:
        # Not a traceback. Two boards at once is the ordinary case now,
        # and the second one meets this on its first run.
        print(f"amik: cannot listen on {HOST}:{port} — {exc.strerror}.\n"
              f"      Another board is probably already there; "
              f"try --port {port + 1}.", file=sys.stderr)
        return False
    port = httpd.server_address[1]
    # flush=True, because this is almost always redirected. stdout is
    # block-buffered when it is not a terminal, so a server that runs
    # forever never fills the buffer and the banner never appears —
    # which is exactly the case it exists for: a board started as a
    # daemon, whose log is the only way to know whether it will work
    # cards.
    # A BOARD FIRST, if there is none. The install is `pip install`,
    # `cd`, `serve`, and a project that then shows an empty page has
    # been told to run a second command it did not know about.
    #
    # After the bind, so a second board that cannot have the port does
    # not write seven files on its way to failing. Before the banner,
    # because the banner reports on a board and this is what there is
    # to report on.
    said = _seeded_line(amik_init.seed_if_empty(root))
    if said:
        print(said, flush=True)
    print(_banner(root, port), flush=True)
    if loop:
        # A DAEMON thread. A card's verify runs for minutes: on a
        # request thread that is a board which stops answering, and on a
        # non-daemon thread it is a server that will not exit.
        threading.Thread(target=amik_loop.tick_forever, args=(root,),
                         daemon=True, name="amik-loop").start()
    if not forever:
        httpd.server_close()
        return True
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(prog="amik", description="Serve the board.")
    ap.add_argument("--root", default=".",
                    help="the directory holding amik/ (default: here)")
    ap.add_argument("--port", type=int, default=4455)
    args = ap.parse_args(argv)
    serve(args.root, args.port)
