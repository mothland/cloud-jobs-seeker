"""Runs every (search, region) query from searches.toml and stores the results."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from jobseeker import config, db
from jobseeker.config import Region, Search, Settings
from jobseeker.theirstack import TheirStackClient, build_payload, to_rows

log = logging.getLogger(__name__)


@dataclass
class Query:
    search: str
    region: Region
    filters: dict
    max_age_days: int
    max_results: int

    def payload(self, *, page: int, limit: int, exclude_ids: list[str]) -> dict:
        return build_payload(
            filters=self.filters, region=self.region, max_age_days=self.max_age_days,
            page=page, limit=limit, exclude_ids=exclude_ids,
        )


def plan(settings: Settings, only: list[str] | None = None) -> list[Query]:
    """Expand searches into one query per region. Max age: search > region > defaults."""
    searches: list[Search] = settings.searches
    if only:
        unknown = set(only) - {s.name for s in searches}
        if unknown:
            raise config.ConfigError(f"Unknown search(es): {sorted(unknown)}")
        searches = [s for s in searches if s.name in only]

    # The run budget is split evenly across queries; a search's max_results can only lower its share.
    pairs = [(s, r) for s in searches for r in s.regions]
    share = max(1, settings.run_budget // max(1, len(pairs)))
    return [
        Query(
            search=s.name,
            region=r,
            filters=s.filters,
            max_age_days=s.max_age_days or r.max_age_days or settings.max_age_days,
            max_results=min(share, s.max_results or share),
        )
        for s, r in pairs
    ]


def _pages(max_results: int, per_page: int) -> tuple[int, int]:
    """Page size and count. TheirStack pages by fixed size, so keep it constant across pages."""
    size = min(per_page, max_results)
    return size, -(-max_results // size)


def run(only: list[str] | None = None, dry_run: bool = False) -> dict:
    settings = config.load_settings()
    queries = plan(settings, only)
    planned = sum(q.max_results for q in queries)
    log.info("%d queries planned, up to %d results (run budget %d)", len(queries), planned, settings.run_budget)

    if dry_run:
        for q in queries:
            size, pages = _pages(q.max_results, settings.per_page)
            payload = q.payload(page=0, limit=size, exclude_ids=[])
            if os.getenv("JOBSEEKER_PRIVATE_SEARCHES"):  # searches came from a secret: don't echo them into CI logs
                log.info("[dry run] %s / %s: %d page(s) of %d", q.search, q.region.name, pages, size)
            else:
                log.info("[dry run] %s / %s: %d page(s) of %d\n  %s", q.search, q.region.name, pages, size,
                         json.dumps(payload, ensure_ascii=False))
        return {"queries": len(queries), "fetched": 0, "stored": 0, "dry_run": True}

    client = TheirStackClient(config.theirstack_api_keys())
    budget = settings.run_budget
    fetched = stored = 0

    with db.connect(config.database_url()) as conn:
        pending = db.pending_migrations(conn)
        if pending:
            raise config.ConfigError(f"Database is missing migrations {pending}. Run: python -m jobseeker setup")

        # TheirStack charges per job returned, so ask it to skip jobs we already have.
        seen = db.recent_external_ids(conn, "theirstack", settings.exclude_seen_days)
        log.info("Excluding %d already-stored jobs from the last %d days", len(seen), settings.exclude_seen_days)

        for q in queries:
            if budget <= 0:
                log.warning("Run budget used up; skipping %s / %s and the rest", q.search, q.region.name)
                break
            size, pages = _pages(min(q.max_results, budget), settings.per_page)
            log.info("%s / %s: up to %d page(s) of %d", q.search, q.region.name, pages, size)

            for page in range(pages):
                jobs = client.search(q.payload(page=page, limit=size, exclude_ids=seen))
                budget -= len(jobs)
                fetched += len(jobs)
                n = db.upsert_offers(conn, to_rows(jobs, search=q.search, region=q.region))
                stored += n
                log.info("  page %d: %d jobs, %d stored", page, len(jobs), n)
                if len(jobs) < size:
                    break

    log.info("Done: %d jobs fetched, %d stored", fetched, stored)
    return {"queries": len(queries), "fetched": fetched, "stored": stored, "dry_run": False}
