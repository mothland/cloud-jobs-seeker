# flows/db.py
import os
import re
import asyncio
import asyncpg
from contextlib import asynccontextmanager
from typing import AsyncIterator, Iterable, Dict, Any, List
from dotenv import dotenv_values, find_dotenv

# --- Helpers ----------------------------------------------------
def _mask_url(u: str | None) -> str:
    if not u:
        return ""
    # Hide only the password part in logs
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", u)

def _load_database_url() -> str:
    env_url = os.getenv("database_url")
    if env_url:
        return env_url

    try:
        from prefect.variables import Variable
        var_url = Variable.get("database_url", default=None)
        if var_url:
            return var_url
    except Exception:
        pass

    cfg = dotenv_values(find_dotenv(usecwd=True))
    if cfg.get("database_url"):
        return cfg["database_url"]

    raise RuntimeError(
        "database_url not found. Set it as a Work Pool env var, a Prefect Variable, or in a local .env."
    )


database_url = _load_database_url()

print(f"[DB] database_url: {_mask_url(database_url) or '(not set!)'}")

# --- Pool -------------------------------------------------------
_pool: asyncpg.Pool | None = None

async def _init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            database_url,
            min_size=1,
            max_size=5,
            statement_cache_size=0,
        )
    return _pool

@asynccontextmanager
async def connection() -> AsyncIterator[asyncpg.Connection]:
    pool = await _init_pool()
    async with pool.acquire() as conn:
        yield conn

# --- Write helpers ---------------------------------------------
async def upsert_offers(rows: Iterable[Dict[str, Any]], chunk_size: int = 500) -> int:
    rows_list: List[Dict[str, Any]] = list(rows)
    if not rows_list:
        return 0

    cols = [
        "offer_id","source","external_id","job_title","company","url",
        "date_posted","avg_salary_usd","seniority","technology_slugs",
        "locations","category","created_at"
    ]

    insert_sql = f"""
    INSERT INTO jobs.offers ({", ".join(cols)})
    VALUES ({", ".join(f"${i}" for i in range(1, len(cols)+1))})
    ON CONFLICT (offer_id) DO UPDATE SET
      source = EXCLUDED.source,
      external_id = EXCLUDED.external_id,
      job_title = EXCLUDED.job_title,
      company = EXCLUDED.company,
      url = EXCLUDED.url,
      date_posted = EXCLUDED.date_posted,
      avg_salary_usd = EXCLUDED.avg_salary_usd,
      seniority = EXCLUDED.seniority,
      technology_slugs = EXCLUDED.technology_slugs,
      locations = EXCLUDED.locations,
      category = EXCLUDED.category;
    """

    async with connection() as conn:
        for i in range(0, len(rows_list), chunk_size):
            chunk = rows_list[i:i+chunk_size]
            values = [[row.get(c) for c in cols] for row in chunk]
            await conn.executemany(insert_sql, values)
    return len(rows_list)

async def ensure_refs() -> None:
    sql = """
    INSERT INTO jobs.job_category_ref (category) VALUES
      ('data_engineer'), ('data_analyst'), ('cloud_engineer'), ('dataops'), ('platform_engineer')
    ON CONFLICT (category) DO NOTHING;
    """
    async with connection() as conn:
        await conn.execute(sql)