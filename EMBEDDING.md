# Embedding Amik in another app

Most people should ignore this file. `amik serve` is the way in, and it
is one command. This is for the case where a board should appear inside
an application you already run, under your own routes and your own
authentication.

Amik has no ASGI app to mount, because a mountable app would tie it to
one framework. The seam is a function instead:

```python
from amik.app import handle

@app.api_route("/amik{rest:path}",
               methods=["GET", "POST", "PATCH", "DELETE"])
async def amik(rest: str, request: Request):
    status, headers, body = handle(
        request.method, "/amik" + rest, dict(request.query_params),
        await request.body(), root=PROJECT_ROOT, base="/amik")
    return Response(body, status_code=status, headers=headers)
```

Ten lines, and that is the whole of it — which is what makes "any stack"
true rather than aspirational. Adapt the four strings in and the three
out to whatever your framework calls them.

`base` is the prefix you mounted at, and Amik uses it to build every
link and form action it renders. Get it wrong and the board renders but
nothing it points at resolves.

`root` is the directory holding `amik/`. It is a parameter rather than
a global because one process can serve more than one board.

**Authentication is the host's.** Amik has no login and will not grow
one: it is a function behind your routes, so whatever guards the route
guards the board. Standalone it binds to `127.0.0.1` for the same
reason — a board holds a project's unreleased plans, and exposing it
should take deliberate effort outside Amik.

**The loop is not included.** `handle()` serves a board; it does not
work one. If you want cards worked inside a host application, run
`amik work --if-changed` from whatever scheduler that application
already has.
