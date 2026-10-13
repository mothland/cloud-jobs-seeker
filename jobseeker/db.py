"""Postgres access: migrations, upserts, and lookups. Works with Supabase or any Postgres 13+."""
from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import psycopg

from jobseeker.config import ROOT

log = logging.getLogger(__name__)

MIGRATIONS_DIR = ROOT / "migrations"

COLUMNS = [
    "offer_id", "source", "external_id", "search", "region", "job_title", "company", "url",
    "date_posted", "avg_salary_usd", "seniority", "technology_slugs", "locations",
    "remote", "hybrid", "employment_statuses", "salary_string", "company_domain",
]

UPSERT_SQL = f"""
INSERT INTO jobs.offers ({", ".join(COLUMNS)})
VALUES ({", ".join(["%s"] * len(COLUMNS))})
ON CONFLICT (offer_id) DO UPDATE SET
  {", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS if c != "offer_id")},
  last_seen_at = now()
"""



@contextmanager
def connect(url: str) -> Iterator[psycopg.Connection]:
    # prepare_threshold=None keeps this working behind Supabase's transaction pooler (port 6543).
    with psycopg.connect(url, prepare_threshold=None, connect_timeout=15) as conn:
        yield conn


def migrate(conn: psycopg.Connection) -> list[str]:
    """Apply any migrations/*.sql not yet recorded. Returns the names applied."""
    conn.execute("CREATE SCHEMA IF NOT EXISTS jobs")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS jobs.schema_migrations ("
        " name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
    )
    applied = {r[0] for r in conn.execute("SELECT name FROM jobs.schema_migrations")}
    done = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        log.info("Applying migration %s", path.name)
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO jobs.schema_migrations (name) VALUES (%s)", (path.name,))
        done.append(path.name)
    conn.commit()
    return done


def pending_migrations(conn: psycopg.Connection) -> list[str]:
    exists = conn.execute("SELECT to_regclass('jobs.schema_migrations') IS NOT NULL").fetchone()[0]
    applied = {r[0] for r in conn.execute("SELECT name FROM jobs.schema_migrations")} if exists else set()
    return [p.name for p in sorted(MIGRATIONS_DIR.glob("*.sql")) if p.name not in applied]


def recent_external_ids(conn: psycopg.Connection, source: str, days: int) -> list[str]:
    rows = conn.execute(
        "SELECT external_id FROM jobs.offers"
        " WHERE source = %s AND coalesce(date_posted, first_seen_at) >= now() - make_interval(days => %s)",
        (source, days),
    )
    return [r[0] for r in rows]


def upsert_offers(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(UPSERT_SQL, [[row.get(c) for c in COLUMNS] for row in rows])
    conn.commit()
    return len(rows)
