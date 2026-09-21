"""`handle()` may return a generator, and a streamed response carries no
Content-Length.

SSE cannot fit a contract whose body is complete bytes. The alternative
was a second embedding seam -- each host implementing /events itself --
which would make "handle() is the one seam" false. A generator is the
streaming primitive every Python web stack already accepts, so it says
"this is a stream" without naming anyone's framework.
"""

import io


class _Fake:
    """Enough of BaseHTTPRequestHandler to record what _send emitted."""

    def __init__(self):
        self.status = None
        self.headers_sent = {}
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.headers_sent[key] = value

    def end_headers(self):
        pass


def _send(out, headers=None):
    from amik.app.server import _Handler
    fake = _Fake()
    _Handler._send(fake, 200, headers or {"Content-Type": "text/plain"}, out)
    return fake


def test_bytes_still_carry_a_content_length():
    fake = _send(b"hello")
    assert fake.headers_sent["Content-Length"] == "5"
    assert fake.wfile.getvalue() == b"hello"


def test_a_generator_carries_no_content_length():
    """A length cannot be computed for a stream, and sending a wrong one
    makes a client wait for bytes that never come."""
    fake = _send(iter([b"a", b"b"]))
    assert "Content-Length" not in fake.headers_sent


def test_a_generator_is_written_chunk_by_chunk():
    fake = _send(iter([b"one ", b"two"]))
    assert fake.wfile.getvalue() == b"one two"
