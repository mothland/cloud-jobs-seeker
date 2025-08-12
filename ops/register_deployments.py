# ops/register_deployments.py
from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Dict, List
from datetime import timedelta

import sys
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from prefect.client.schemas.schedules import IntervalSchedule
from flows.db import connection
from flows.ingest_offers import ingest_offers

# -------------------------
# strict config getters 😑
# -------------------------
def _prefect_var(name: str) -> str | None:
    try:
        from prefect.variables import Variable
        return Variable.get(name, default=None)
    except Exception:
        return None

def _get_required(name: str) -> str:
    """
    Require a value from either env var or Prefect Variable (lowercase only).
    No dotenv, no uppercase. Cry loudly if missing.
    """
    v = os.getenv(name) or _prefect_var(name)
    if not v:
        raise RuntimeError(
            f"Missing required config '{name}'. "
            f"Set it as a Work Pool environment variable or a Prefect Variable (lowercase)."
        )
    return v

# ======== REQUIRED CONFIG ======================================
# Only accept lowercase names, from env or Prefect Variables
GIT_REPO_URL = _get_required("git_repo_url")
WORK_POOL_NAME = _get_required("work_pool_name")
DATABASE_URL   = _get_required("database_url")  # fail fast if not provided
# ===============================================================

# Titles to use per DB category (search filters)
TITLE_MAP: Dict[str, List[str]] = {
    "data_engineer": ["Data Engineer", "Ingénieur Data", "Ingenieur data"],
    "data_analyst": ["Data Analyst"],
    "cloud_engineer": ["Cloud Engineer", "Cloud Architect", "Ingénieur cloud", "ingenieur cloud", "architecte cloud"],
    "dataops": ["DataOps", "Data Ops", "DataOps"],
}

async def fetch_categories() -> List[str]:
    """
    Read distinct categories from jobs.job_category_ref.
    We now REQUIRE database_url to be set (preflight above).
    If the DB is momentarily unreachable, we fall back to TITLE_MAP
    so you can still register deployments.
    """
    sql = "SELECT category FROM jobs.job_category_ref ORDER BY category"
    try:
        async with connection() as conn:
            rows = await conn.fetch(sql)
        cats = [r["category"] for r in rows]
        return cats or list(TITLE_MAP.keys())
    except Exception:
        # Still allow registration to proceed
        return list(TITLE_MAP.keys())

async def register_for_category(cat: str) -> None:
    titles = TITLE_MAP.get(cat, [cat.replace("_", " ").title()])

    # Combine France and Switzerland into a single plan
    plans = [
        (f"{cat}-idf-switzerland", {"titles": titles, "category": cat, "location_preset": "combined_france_switzerland", "page_limit": 2, "per_page": 50}),
    ]

    for name, params in plans:
        print(f"→ Registering deployment: {name} | params={params}")

        # from_source is async — serverless pulls from your Git repo
        flow = await ingest_offers.from_source(
            source=GIT_REPO_URL,
            entrypoint="flows/ingest_offers.py:ingest_offers",
        )

        # Every 7 days (weekly)
        schedule = IntervalSchedule(interval=timedelta(days=7))

        await flow.deploy(
            name=name,
            work_pool_name=WORK_POOL_NAME,
            parameters=params,
            schedule=schedule,
        )
        print(f"   ✓ {name} registered/updated")

async def main() -> None:
    # Log masked DB URL so we know what we used
    masked = re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", DATABASE_URL)
    print(f"[DB] database_url: {masked}")

    cats = await fetch_categories()
    print(f"Found categories: {cats}")
    for cat in cats:
        await register_for_category(cat)

    print("✅ All deployments registered/updated.")

if __name__ == "__main__":
    asyncio.run(main())