"""Local web app: browse and track offers, see a dashboard, and edit .env / searches.toml.

Listens on 127.0.0.1 only, and every API call must carry the random token from the URL,
so other websites open in the same browser can't read or change your data. Offer text comes
from the internet, so pages are served with a strict Content-Security-Policy as well.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import tempfile
import threading
import tomllib
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from jobseeker import config, db, ingest, tracker
from jobseeker.theirstack import TheirStackClient, TheirStackError

STATIC_DIR = Path(__file__).with_name("static")
STATIC_TYPES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
ENV_PATH = config.ROOT / ".env"
SECRET_KEYS = ("DATABASE_URL", "THEIRSTACK_API_KEYS")

_run_lock = threading.Lock()


# ---------- .env ----------

def _env_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_env(updates: dict[str, str]) -> None:
    """Set keys in .env, keeping every other line (comments, other variables) as it was."""
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    if not lines and (config.ROOT / ".env.example").exists():
        lines = (config.ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    remaining = dict(updates)
    for i, line in enumerate(lines):
        m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and m.group(1) in remaining:
            key = m.group(1)
            lines[i] = f"{key}={_env_quote(remaining.pop(key))}"
    lines += [f"{k}={_env_quote(v)}" for k, v in remaining.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ.update(updates)  # config reads os.environ, which .env was loaded into at startup


def secrets_state() -> dict[str, Any]:
    """Whether each secret is set; never any part of its value."""
    keys = [k for k in os.getenv("THEIRSTACK_API_KEYS", "").split(",") if k.strip()]
    return {"database_url_set": bool(os.getenv("DATABASE_URL", "").strip()), "api_key_count": len(keys)}


# ---------- searches.toml ----------

def _toml_value(v: Any, indent: str = "") -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)  # JSON string escapes are valid TOML basic strings
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {_toml_value(x)}" for k, x in v.items()) + " }"
    if isinstance(v, list):
        items = [_toml_value(x) for x in v]
        if v and all(isinstance(x, dict) for x in v):  # one inline table per line
            return "[\n" + "\n".join(f"{indent}  {x}," for x in items) + f"\n{indent}]"
        if sum(len(x) + 2 for x in items) <= 80:
            return "[" + ", ".join(items) + "]"
        rows, row = [], ""
        for item in items:
            if row and len(row) + len(item) > 90:
                rows.append(row.rstrip())
                row = ""
            row += item + ", "
        rows.append(row.rstrip())
        return "[\n" + "\n".join(f"{indent}  {r}" for r in rows) + f"\n{indent}]"
    raise TypeError(f"can't write {type(v).__name__} to TOML")


TOML_HEADER = """\
# What to search for. Edited with `python -m jobseeker ui`; you can also edit it by hand.
# See the README ("Configuring searches") for what each setting does.
"""


def to_toml(data: dict[str, Any]) -> str:
    out = [TOML_HEADER, "[defaults]"]
    out += [f"{k} = {_toml_value(v)}" for k, v in data.get("defaults", {}).items()]
    for name, region in data.get("regions", {}).items():
        out += ["", f"[regions.{_toml_value(name) if not re.fullmatch(r'[A-Za-z0-9_-]+', name) else name}]"]
        out += [f"{k} = {_toml_value(v)}" for k, v in region.items()]
    for search in data.get("search", []):
        out += ["", "[[search]]"]
        out += [f"{k} = {_toml_value(v)}" for k, v in search.items()]
    return "\n".join(out) + "\n"


def _clean_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop empty optional fields the form sends, so the file only holds what was set."""
    def compact(d: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in d.items() if v not in (None, "", [])}

    def location(loc: dict[str, Any]) -> dict[str, Any]:
        # Keep only id + name; the UI also carries display fields that don't belong in the file.
        return {"id": loc["id"], "name": loc["name"]} if loc.get("name") else {"id": loc["id"]}

    regions = {
        r["name"]: compact({
            k: ([location(x) for x in v] if k in ("locations", "exclude_locations") and v else v)
            for k, v in r.items() if k != "name"
        })
        for r in payload.get("regions", []) if r.get("name")
    }
    return {
        "defaults": compact(payload.get("defaults", {})),
        "regions": regions,
        "search": [compact(s) for s in payload.get("searches", [])],
    }


def save_settings(payload: dict[str, Any]) -> None:
    text = to_toml(_clean_settings(payload))
    # Your edits go to the git-ignored searches.local.toml, never the committed example.
    path = Path(os.environ["SEARCHES_FILE"]) if os.getenv("SEARCHES_FILE") else config.ROOT / "searches.local.toml"
    # Validate exactly what will be written before replacing the real file.
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False, encoding="utf-8") as tmp:
        tmp.write(text)
    try:
        config.load_settings(Path(tmp.name))
    finally:
        os.unlink(tmp.name)
    if path.exists():
        path.with_name(path.name + ".bak").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(text, encoding="utf-8")


def load_raw_settings() -> dict[str, Any]:
    path = config.searches_path()
    if not path.exists():
        return {"defaults": {}, "regions": [], "searches": []}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {
        "defaults": data.get("defaults", {}),
        "regions": [{"name": n, **r} for n, r in data.get("regions", {}).items()],
        "searches": data.get("search", []),
    }


# ---------- actions ----------

class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


def _with_logs(fn) -> dict[str, Any]:
    cap = _Capture()
    logger = logging.getLogger("jobseeker")
    logger.addHandler(cap)
    try:
        result = fn()
    finally:
        logger.removeHandler(cap)
    return {"result": result, "logs": cap.lines}


def test_db() -> dict[str, Any]:
    url = config.database_url()
    with db.connect(url) as conn:
        pending = db.pending_migrations(conn)
        rows = None if pending else conn.execute("SELECT count(*) FROM jobs.offers").fetchone()[0]
    return {"pending": pending, "rows": rows}


def run_setup() -> dict[str, Any]:
    with db.connect(config.database_url()) as conn:
        applied = db.migrate(conn)
        rows = conn.execute("SELECT count(*) FROM jobs.offers").fetchone()[0]
    return {"applied": applied, "rows": rows}


_FIELD_TO_KEY = {api_field: key for key, (api_field, _) in config.SEARCH_FILTERS.items()}


def dry_run() -> list[dict[str, Any]]:
    settings = config.load_settings()
    out = []
    for q in ingest.plan(settings):
        r = q.region
        where = [", ".join(r.countries)] if r.countries else []
        where += [loc.name or str(loc.id) for loc in r.locations]
        if r.cities and not r.locations:
            where.append(f"{len(r.cities)} cities")
        out.append({
            "search": q.search, "region": r.name, "where": " · ".join(where),
            "filters": [_FIELD_TO_KEY[f] for f in q.filters if f != "job_title_or"],
            "max_age_days": q.max_age_days, "max_results": q.max_results,
            "payload": q.payload(page=0, limit=min(settings.per_page, q.max_results), exclude_ids=[]),
        })
    return out


def _client() -> TheirStackClient:
    return TheirStackClient(config.theirstack_api_keys(), timeout=15)


def lookup_locations(body: dict[str, Any]) -> list[dict[str, Any]]:
    name = str(body.get("name", "")).strip()
    if len(name) < 2:
        return []
    rows = _client().locations(name, body.get("country_code") or None)
    return [{
        "id": r.get("id"), "name": r.get("name"),
        "label": r.get("display_name") or ", ".join(x for x in (r.get("name"), r.get("admin1_name"), r.get("country_name")) if x),
        "kind": r.get("feature_name") or r.get("feature_code") or "",
        "country_code": r.get("country_code"),
    } for r in rows if isinstance(r, dict) and r.get("id") is not None]


def lookup_technologies(body: dict[str, Any]) -> list[dict[str, Any]]:
    query = str(body.get("q", "")).strip()
    if len(query) < 2:
        return []
    return [{"slug": r.get("slug"), "name": r.get("name"), "category": r.get("category") or "", "jobs": r.get("jobs")}
            for r in _client().technologies(query) if r.get("slug")]


def count_matches(body: dict[str, Any]) -> dict[str, Any]:
    """Total jobs TheirStack has for one planned query. Asks for 1 result, so it costs at most 1 credit."""
    settings = config.load_settings()
    query = next((q for q in ingest.plan(settings, [body.get("search")])
                  if q.region.name == body.get("region")), None)
    if query is None:
        raise config.ConfigError("That search/region pair isn't in the saved searches.")
    payload = query.payload(page=0, limit=1, exclude_ids=[])
    payload["include_total_results"] = True
    meta = _client().search_page(payload).get("metadata") or {}
    total = meta.get("total_results")
    if total is None:
        raise TheirStackError("TheirStack didn't return a total for this query.")
    return {"total": total}


def _with_db(fn):
    with db.connect(config.database_url()) as conn:
        pending = db.pending_migrations(conn)
        if pending:
            raise config.ConfigError(f"The database needs updating ({', '.join(pending)}). "
                                     "Go to Settings → Connections → Create / update tables.")
        return fn(conn)


def real_run() -> dict[str, Any]:
    if not _run_lock.acquire(blocking=False):
        raise config.ConfigError("A run is already in progress.")
    try:
        return _with_logs(ingest.run)
    finally:
        _run_lock.release()


# ---------- HTTP ----------

class Handler(BaseHTTPRequestHandler):
    token: str = ""
    port: int = 0

    def log_message(self, *args) -> None:  # keep the terminal quiet
        pass

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: Any) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False, default=str).encode(), "application/json; charset=utf-8")

    def _host_ok(self) -> bool:
        # Blocks DNS-rebinding: only accept requests addressed to this machine by name.
        return self.headers.get("Host", "") in {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    def do_GET(self) -> None:
        if not self._host_ok():
            return self._send(HTTPStatus.FORBIDDEN, b"Forbidden", "text/plain")
        name = self.path.split("?")[0].lstrip("/") or "index.html"
        # Only plain file names that exist directly in static/, so no path can escape the folder.
        path = STATIC_DIR / name
        if re.fullmatch(r"[a-z0-9_-]+\.(html|css|js)", name) and path.is_file():
            ctype = STATIC_TYPES[path.suffix] + "; charset=utf-8"
            return self._send(HTTPStatus.OK, path.read_bytes(), ctype)
        self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain")

    def do_POST(self) -> None:
        if not self._host_ok() or not secrets.compare_digest(self.headers.get("X-Token", ""), self.token):
            return self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON"})

        try:
            data = self._dispatch(self.path, body)
        except KeyError:
            return self._json(HTTPStatus.NOT_FOUND, {"error": "unknown action"})
        except (config.ConfigError, TheirStackError, tracker.TrackerError) as e:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": config.redact(str(e))})
        except db.psycopg.OperationalError as e:
            return self._json(HTTPStatus.BAD_REQUEST,
                              {"error": config.redact(f"Database connection failed: {e}".strip()), "code": "db_connect"})
        except Exception as e:  # surface anything else in the page instead of a silent failure
            logging.getLogger(__name__).error("UI action failed: %s", config.redact(f"{type(e).__name__}: {e}"))
            return self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": config.redact(f"{type(e).__name__}: {e}")})
        self._json(HTTPStatus.OK, data)

    def _dispatch(self, path: str, body: dict[str, Any]) -> Any:
        if path == "/api/state":
            return {"secrets": secrets_state(), "settings": load_raw_settings(),
                    "searches_file": str(config.searches_path().name)}
        if path == "/api/secrets":
            updates = {}
            if body.get("database_url", "").strip():
                updates["DATABASE_URL"] = body["database_url"].strip()
            keys = [k.strip() for k in body.get("api_keys", []) if k.strip()]
            if keys:
                updates["THEIRSTACK_API_KEYS"] = ",".join(dict.fromkeys(keys))
            if updates:
                write_env(updates)
            return {"secrets": secrets_state(), "saved": sorted(updates)}
        if path == "/api/settings":
            save_settings(body)
            return {"settings": load_raw_settings()}
        if path == "/api/locations":
            return lookup_locations(body)
        if path == "/api/technologies":
            return lookup_technologies(body)
        if path == "/api/count":
            return count_matches(body)
        if path == "/api/offers":
            return _with_db(lambda c: {**tracker.list_offers(c, body), "facets": tracker.facets(c)})
        if path == "/api/offer":
            return _with_db(lambda c: tracker.get_offer(c, str(body.get("offer_id") or "")))
        if path == "/api/offer/update":
            return _with_db(lambda c: tracker.update_offer(c, body))
        if path == "/api/dashboard":
            return _with_db(lambda c: {**tracker.dashboard(c, body), "facets": tracker.facets(c)})
        actions = {"/api/test-db": test_db, "/api/setup": run_setup, "/api/dry-run": dry_run, "/api/run": real_run}
        return actions[path]()


def serve(port: int = 8765, open_browser: bool = True) -> None:
    Handler.token = secrets.token_urlsafe(24)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    Handler.port = server.server_address[1]
    url = f"http://127.0.0.1:{Handler.port}/#t={Handler.token}"
    print(f"Jobseeker: {url}\n(Only reachable from this computer. Press Ctrl+C to stop.)")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
