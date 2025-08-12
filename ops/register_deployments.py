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
# strict config getters (ugh)
# -------------------------
def _prefect_var(name: str) -> str | None:
    try:
        from prefect.variables import Variable
        return Variable.get(name, default=None)
    except Exception:
        return None

def _get_required(name: str) -> str:
    v = os.getenv(name) or _prefect_var(name)
    if not v:
        raise RuntimeError(
            f"Missing required config '{name}'. "
            f"Set it as a Work Pool environment variable or a Prefect Variable (lowercase)."
        )
    return v

# ======== REQUIRED CONFIG ======================================
GIT_REPO_URL = _get_required("git_repo_url")
WORK_POOL_NAME = _get_required("work_pool_name")
DATABASE_URL   = _get_required("database_url")
# ===============================================================

# Titles by DB category (used inside each category deployment)
TITLE_MAP: Dict[str, List[str]] = {
    "data_engineer": ["Data Engineer", "Ingénieur Data", "Ingenieur data", "data architect", "architecte data"],
    "data_analyst": ["Data Analyst"],
    "cloud_engineer": [
        "Cloud Engineer", "Cloud Architect",
        "Ingénieur cloud", "ingenieur cloud", "architecte cloud",
    ],
    "dataops": ["DataOps", "Data Ops", "Data-Ops"],
    "mlops": ["MLOps", "ML Ops", "ML-Ops"]
    # Add more if you add rows in jobs.job_category_ref
}

async def fetch_categories() -> List[str]:
    """
    Read distinct categories from jobs.job_category_ref.
    Fall back to TITLE_MAP keys if DB is unreachable/empty.
    """
    sql = "SELECT category FROM jobs.job_category_ref ORDER BY category"
    try:
        async with connection() as conn:
            rows = await conn.fetch(sql)
        cats = [r["category"] for r in rows]
        return cats or list(TITLE_MAP.keys())
    except Exception:
        return list(TITLE_MAP.keys())

def _mask_db_url(url: str) -> str:
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)

async def register_for_category(cat: str) -> None:
    """
    ONE deployment per DB category.
    The flow will split by country (CH, then FR) and fair-split per title.
    """
    titles = TITLE_MAP.get(cat, [cat.replace("_", " ").title()])

    params = {
        # search filters
        "titles": titles,
        "category": cat,

        # fair split: 2 calls per title (CH + FR), compute per-call share inside the flow
        "split_by_country": True,

        # country-specific knobs
        "ch_country_codes": ["CH"],
        "ch_location_preset": "geneva",
        "ch_posted_max_age_days": 30,

        "fr_country_codes": ["FR"],
        "fr_location_preset": "ile_de_france",
        "fr_posted_max_age_days": 7,

        # weekly budget: 400/mo → ~100/wk; flow divides by (len(titles)*2)
        "total_weekly_budget": 100,
        # leave per_call_limit unset so it auto-computes from titles × countries
        # "per_call_limit": 10,
    }

    name = f"{cat}-weekly"
    print(f"→ Registering deployment: {name} | params={params}")

    flow = await ingest_offers.from_source(
        source=GIT_REPO_URL,
        entrypoint="flows/ingest_offers.py:ingest_offers",
    )

    schedule = IntervalSchedule(interval=timedelta(days=7))

    await flow.deploy(
        name=name,
        work_pool_name=WORK_POOL_NAME,
        parameters=params,
        schedule=schedule,
        build=[{
            "prefect.deployments.steps.pip_install_requirements": {
                "requirements": "requirements.txt"
            }
        }],
    )
    print(f"   ✓ {name} registered/updated")

async def main() -> None:
    print(f"[DB] database_url: {_mask_db_url(DATABASE_URL)}")
    cats = await fetch_categories()
    print(f"Found categories: {cats}")
    for cat in cats:
        await register_for_category(cat)
    print("✅ All deployments registered/updated.")

if __name__ == "__main__":
    asyncio.run(main())