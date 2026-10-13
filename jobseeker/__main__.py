"""CLI: python -m jobseeker {setup,run,ui} [options]"""
from __future__ import annotations

import argparse
import logging
import sys
import traceback

from jobseeker import config, db, ingest
from jobseeker.theirstack import TheirStackError


def cmd_setup(_args) -> None:
    settings = config.load_settings()
    print(f"✓ {config.searches_path().name}: {len(settings.searches)} search(es), "
          f"{len(ingest.plan(settings))} query(ies) per run")

    keys = config.theirstack_api_keys()
    print(f"✓ THEIRSTACK_API_KEYS: {len(keys)} key(s)")

    with db.connect(config.database_url()) as conn:
        print("✓ Connected to the database")
        applied = db.migrate(conn)
        print(f"✓ Migrations applied: {', '.join(applied)}" if applied else "✓ Schema already up to date")
        count = conn.execute("SELECT count(*) FROM jobs.offers").fetchone()[0]
        print(f"✓ jobs.offers has {count} row(s)")

    print("\nReady. Try: python -m jobseeker run --dry-run")


def cmd_run(args) -> None:
    ingest.run(only=args.search or None, dry_run=args.dry_run)


def cmd_ui(args) -> None:
    from jobseeker.ui.server import serve

    serve(port=args.port, open_browser=not args.no_browser)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobseeker", description="Collect job offers from TheirStack into Postgres.")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("setup", help="check config, connect to the database and create/upgrade the schema")

    p_run = sub.add_parser("run", help="fetch new jobs and store them")
    p_run.add_argument("--search", action="append", metavar="NAME", help="only run this search (repeatable)")
    p_run.add_argument("--dry-run", action="store_true", help="print the API queries without calling the API or database")

    p_ui = sub.add_parser("ui", help="open a settings page in your browser (no .env editing needed)")
    p_ui.add_argument("--port", type=int, default=8765)
    p_ui.add_argument("--no-browser", action="store_true", help="print the link instead of opening it")

    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Nothing from .env may reach the output (CI logs can be public), so every message goes through redact().
    for handler in logging.getLogger().handlers:
        handler.setFormatter(_RedactingFormatter(handler.formatter))

    try:
        {"setup": cmd_setup, "run": cmd_run, "ui": cmd_ui}[args.command](args)
    except config.ConfigError as e:
        print(f"Config error: {config.redact(str(e))}", file=sys.stderr)
        return 2
    except TheirStackError as e:
        print(f"TheirStack error: {config.redact(str(e))}", file=sys.stderr)
        return 1
    except db.psycopg.OperationalError as e:
        print(f"Database connection failed: {config.redact(str(e))}\n"
              "Check DATABASE_URL. On Supabase, use the Session pooler string, and make sure the project isn't paused.",
              file=sys.stderr)
        return 1
    except Exception as e:  # a traceback could include connection details; show it only with -v, redacted
        if args.verbose:
            print(config.redact(traceback.format_exc()), file=sys.stderr)
        print(f"Unexpected error: {type(e).__name__}: {config.redact(str(e))}"
              + ("" if args.verbose else " (run with -v for details)"), file=sys.stderr)
        return 1
    return 0


class _RedactingFormatter(logging.Formatter):
    def __init__(self, inner: logging.Formatter | None):
        super().__init__()
        self._inner = inner or logging.Formatter()

    def format(self, record: logging.LogRecord) -> str:
        return config.redact(self._inner.format(record))


if __name__ == "__main__":
    sys.exit(main())
