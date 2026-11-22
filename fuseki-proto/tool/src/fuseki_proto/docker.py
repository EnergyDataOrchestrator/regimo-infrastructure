"""Thin wrappers around `docker compose` and the Fuseki HTTP endpoints.

Only the standard library is used here (``subprocess`` + ``urllib``) so that
the only third-party runtime dependency of the CLI is ``click``.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Directory of the tool (i.e. where pyproject.toml lives) so that the compose
# project / data dir resolve regardless of the caller's CWD.
TOOL_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = TOOL_DIR.parent / "data"
DEFAULT_BACKUPS_DIR = DATA_DIR / "backups"


# ---------------------------------------------------------------------------
# docker compose helpers
# ---------------------------------------------------------------------------
def compose(*args: str, cwd: Path, check: bool = True,
            capture: bool = False) -> subprocess.CompletedProcess:
    """Run `docker compose ...` in `cwd`, streaming output to the user.

    With ``capture=True`` stdout/stderr are captured (returns str) instead of
    streamed, for commands whose output we need to parse (e.g. `ps --format json`).
    """
    cmd = ["docker", "compose", *args]
    return subprocess.run(cmd, cwd=str(cwd), check=check,
                          capture_output=capture, text=capture)


def container_status(service: str, cwd: Path) -> str:
    """Return a short state string ("running"/"exited"/"missing") for a service."""
    try:
        proc = compose(
            "ps", "--format", "json", service, cwd=cwd, check=False,
            capture=True,
        )
        output = (proc.stdout or "").strip()
    except Exception:  # docker compose itself failed
        return "unknown"
    if proc.returncode != 0 or not output:
        return "missing"
    # `docker compose ps --format json` may emit a single JSON object or a
    # stream of them; take the first non-empty object in either case.
    info = _parse_first_json(output)
    return (info.get("State") or "").lower() or "unknown"


def _parse_first_json(output: str) -> dict:
    """Parse the first JSON object in (possibly multi-object stream) output."""
    decoder = json.JSONDecoder()
    i = 0
    n = len(output)
    while i < n:
        while i < n and output[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        try:
            obj, i = decoder.raw_decode(output, i)
            return obj
        except json.JSONDecodeError:
            i += 1
    return {}


def wait_for_ping(base_url: str, dataset: str, user: str, password: str,
                  timeout: float = 60.0) -> bool:
    """Poll a live data-service query endpoint until it answers HTTP 200.

    The (server-only) jena-fuseki-server build does NOT expose `/$/ping` / UI
    admin endpoints, so liveness is probed with a trivial SPARQL query against
    a dataset's `/query` endpoint instead.
    """
    url = dataset_query_url(base_url, dataset)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            http_get(url, user=user, password=password)
            return True
        except Exception:
            time.sleep(1.0)
    return False


def dataset_query_url(base_url: str, dataset: str) -> str:
    """URL that runs a trivial query against a dataset (used as liveness probe)."""
    q = "SELECT * WHERE { ?s ?p ?o } LIMIT 1"
    return f"{base_url}/{dataset}/query?query={urllib.parse.quote(q, safe='')}"


def dump_graph(base_url: str, dataset: str, user: str, password: str,
               accept: str = "text/turtle") -> bytes:
    """Dump the whole dataset as RDF (CONSTRUCT over the default graph).

    The (server-only) jena-fuseki-server build has no `/$/backup` admin
    endpoint, so backups are a CONSTRUCT dump from the dataset `/query`
    endpoint — the same RDF the dataset serves.
    """
    q = "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"
    url = f"{base_url}/{dataset}/query"
    headers = {"Authorization": _basic_auth_header(user, password),
               "Accept": accept}
    request = urllib.request.Request(
        url + "?query=" + urllib.parse.quote(q, safe=""),
        headers=headers, method="GET")
    with urllib.request.urlopen(request) as resp:
        return resp.read()


# ---------------------------------------------------------------------------
# Fuseki HTTP client (stdlib only)
# ---------------------------------------------------------------------------
def _basic_auth_header(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {token}"


def _req(method: str, url: str, user: str, password: str,
         data: bytes | None = None, content_type: str | None = None,
         accept: str | None = None, timeout: float = 30.0):
    headers = {"Authorization": _basic_auth_header(user, password)}
    if content_type:
        headers["Content-Type"] = content_type
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return resp.status, resp.read()


def http_get(url: str, user: str, password: str) -> bytes:
    _, body = _req("GET", url, user, password)
    return body


def http_upload(url: str, user: str, password: str, source: Path,
                content_type: str | None = None) -> bytes:
    """POST a local file (Turtle, JSON-LD, ...) to `url`."""
    data = source.read_bytes()
    status, body = _req(
        "POST", url, user, password, data=data,
        content_type=content_type or guess_content_type(source), timeout=120.0,
    )
    if status >= 400:
        raise RuntimeError(f"HTTP {status}: {body.decode(errors='replace')}")
    return body


def http_update(query: str, update_url: str, user: str, password: str) -> None:
    """Fire a SPARQL-UPDATE query against an endpoint (may 4xx; captured)."""
    data = query.encode()
    _, body = _req("POST", update_url, user, password, data=data,
                   content_type="application/sparql-update")
    sys.stdout.write(body.decode(errors="replace"))


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------
def guess_content_type(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".ttl": "text/turtle",
        ".nt": "application/n-triples",
        ".nq": "application/n-quads",
        ".rdf": "application/rdf+xml",
        ".owl": "application/rdf+xml",
        ".json": "application/ld+json",
        ".jsonld": "application/ld+json",
        ".trig": "application/trig",
    }.get(ext, "text/turtle")
