import os
import asyncio
import random
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Iterable, Tuple
from flows.filters import ILE_DE_FRANCE_CITIES, GENEVA_CITIES  # :contentReference[oaicite:0]{index=0}

import requests
from dotenv import dotenv_values, find_dotenv
from dateutil import parser as dtparse

# DB helpers
from flows.db import upsert_offers, ensure_refs

# If you keep a secondary connection helper somewhere else, this preserves compatibility
try:
    from flows.db import connection  # type: ignore
except Exception:
    from flows.common.db import connection  # type: ignore


# =========================
# Config & Secrets loading
# =========================

def _prefect_variable_get(name: str) -> Optional[str]:
    """Get a Prefect Variable by name if running under Prefect; else None."""
    try:
        from prefect.variables import Variable  # imported lazily so local runs don't need Prefect
        return Variable.get(name, default=None)
    except Exception:
        return None

def _get_var(name_lc: str, name_uc: str) -> Optional[str]:
    """
    Look up a config value by:
      1) environment variable (lowercase or UPPERCASE)
      2) Prefect Variable (lowercase or UPPERCASE)
      3) .env (local dev) (lowercase or UPPERCASE)
    """
    # 1) Env
    v = os.getenv(name_lc) or os.getenv(name_uc)
    if v:
        return v

    # 2) Prefect Variable
    v = _prefect_variable_get(name_lc) or _prefect_variable_get(name_uc)
    if v:
        return v

    # 3) .env (local dev)
    cfg = dotenv_values(find_dotenv(usecwd=True))
    return cfg.get(name_lc) or cfg.get(name_uc)

def _load_api_keys() -> List[str]:
    keys: List[str] = []

    # Always start with the base key (no number)
    base_key = _get_var("theirstack_api_key", "THEIRSTACK_API_KEY")
    if base_key:
        keys.append(base_key)

    # Then check numbered keys up to 5
    for i in range(2, 6):
        k = _get_var(f"theirstack_api_key_{i}", f"THEIRSTACK_API_KEY_{i}")
        if k and k not in keys:
            keys.append(k)

    if not keys:
        raise RuntimeError(
            "Missing theirstack_api_key (and numbered variants). "
            "Set them as Work Pool env vars or Prefect Variables."
        )

    return keys

_API_KEYS: List[str] = _load_api_keys()

def _get_int(name_lc: str, name_uc: str, default: int) -> int:
    v = _get_var(name_lc, name_uc)
    if v is None or f"{v}".strip() == "":
        return default
    try:
        return int(v)
    except Exception:
        return default


# =========================
# Tunables
# =========================

API_URL = "https://api.theirstack.com/v1/jobs/search"

# API query knobs (can be overridden via env/variables)
POSTED_MAX_AGE_DAYS = _get_int("posted_max_age_days", "POSTED_MAX_AGE_DAYS", 15)

# If your API caps list size for job_id_not, set a number. None = send all.
_job_id_not_max_val = _get_var("job_id_not_max", "JOB_ID_NOT_MAX")
JOB_ID_NOT_MAX: Optional[int] = int(_job_id_not_max_val) if (_job_id_not_max_val or "").isdigit() else None

# Retry/backoff
MAX_RETRIES = _get_int("max_retries", "MAX_RETRIES", 5)
BACKOFF_BASE = float(_get_var("backoff_base", "BACKOFF_BASE") or 0.8)
BACKOFF_MAX = float(_get_var("backoff_max", "BACKOFF_MAX") or 10.0)
JITTER = float(_get_var("backoff_jitter", "BACKOFF_JITTER") or 0.4)

TRANSIENT_STATUSES = {408, 429, 500, 502, 503, 504}
# Include 402 so we rotate keys immediately on “Payment Required”
SWITCH_KEY_STATUSES = {401, 402, 403}


# =========================
# HTTP helpers
# =========================

def _sleep_backoff(attempt: int) -> None:
    delay = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_MAX)
    delay += random.random() * JITTER
    time.sleep(delay)

def _choose_key(attempt: int) -> Tuple[str, int]:
    """Round-robin the available keys by attempt number."""
    idx = attempt % len(_API_KEYS)
    return _API_KEYS[idx], idx

def _post_with_retries(url: str, payload: Dict[str, Any], timeout: int = 20) -> Dict[str, Any]:
    """
    POST with:
    - key rotation (immediate on 401/402/403, round-robin per attempt)
    - retries with exponential backoff for transient failures (429/5xx/timeout)
    - never logs actual keys; only key index.
    """
    last_err: Optional[Exception] = None
    session = requests.Session()

    for attempt in range(MAX_RETRIES):
        key, key_idx = _choose_key(attempt)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        }

        try:
            resp = session.post(url, json=payload, headers=headers, timeout=timeout)
            status = resp.status_code
            print(f"[API] Attempt {attempt+1}/{MAX_RETRIES} using key#{key_idx} → Status {status}")

            if 200 <= status < 300:
                return resp.json()

            # Unauthorized / Payment Required / Forbidden → rotate key immediately (no sleep)
            if status in SWITCH_KEY_STATUSES:
                last_err = requests.HTTPError(f"{status} auth/quota error; rotating key")
                continue  # next attempt uses next key

            # Transient statuses → backoff + retry
            if status in TRANSIENT_STATUSES:
                last_err = requests.HTTPError(f"Transient HTTP {status}; will retry")
                _sleep_backoff(attempt)
                continue

            # Any other non-2xx → propagate
            resp.raise_for_status()

        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e
            print(f"[API] Network error: {type(e).__name__} → retrying…")
            _sleep_backoff(attempt)
            continue
        except requests.HTTPError as e:
            last_err = e
            print(f"[API] Non-retriable HTTP error: {e}")
            break
        except Exception as e:
            last_err = e
            print(f"[API] Unexpected error: {e} (not retrying)")
            break

    # Exhausted retries
    if last_err:
        raise last_err
    raise RuntimeError("Request failed for unknown reasons after retries")


# =========================
# Utilities & Transform
# =========================

def _chunk(seq: List[str], n: int) -> Iterable[List[str]]:
    for i in range(0, len(seq), n):
        yield seq[i: i + n]

def _classify_category(title: str) -> str:
    t = (title or "").lower()
    if any(k in t for k in ["data engineer", "ingénieur data", "ingénieur données"]):
        return "data_engineer"
    if any(k in t for k in ["data analyst", "analyst", "analyste data", "analyste de données"]):
        return "data_analyst"
    if "cloud" in t:
        return "cloud_engineer"
    if "dataops" in t or "data ops" in t:
        return "dataops"
    return "data_engineer"

def _parse_date(s: Optional[str], default_tz_utc: bool = True):
    if not s:
        return None
    try:
        dt = dtparse.isoparse(s)
        if dt.tzinfo is None and default_tz_utc:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


_IDF_SET = {c.lower() for c in ILE_DE_FRANCE_CITIES}
_GENEVA_SET = {c.lower() for c in GENEVA_CITIES}

def _infer_country_for_city(city: Optional[str]) -> Optional[str]:
    if not city:
        return None
    c = city.strip().lower()
    if c in _IDF_SET:
        return "FR"
    if c in _GENEVA_SET:
        return "CH"
    return None

def _locations_to_strings(locations: List[Dict[str, Any]]) -> List[str]:
    """
    Build display-friendly location strings and inject a country code when possible.
    Priority:
      1) Use API "country_code" if present
      2) Else infer from city membership (Île-de-France -> FR, Geneva -> CH)
    """
    out: List[str] = []
    for loc in locations or []:
        city = (loc.get("city") or "").strip() or None
        state = (loc.get("state") or "").strip() or None
        cc = (loc.get("country_code") or "").strip().upper() or None

        if not cc:
            cc = _infer_country_for_city(city)

        # Assemble best string we can
        parts = [p for p in (city, state, cc) if p]
        if parts:
            out.append(", ".join(parts))

    # de-dupe while preserving order
    seen = set()
    deduped: List[str] = []
    for s in out:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped


def transform_jobs_for_db(api_json: Dict[str, Any], category_override: Optional[str] = None) -> List[Dict[str, Any]]:
    items = api_json.get("data") or api_json.get("results") or api_json.get("jobs") or []
    now_utc = datetime.now(timezone.utc)
    rows: List[Dict[str, Any]] = []

    print(f"[TRANSFORM] Raw jobs received: {len(items)}")

    for j in items:
        ext_id = j.get("id")
        if not ext_id:
            continue

        url = j.get("url") or j.get("final_url") or j.get("source_url")
        job_title = j.get("job_title") or ""
        row_category = category_override or _classify_category(job_title)

        row = {
            "offer_id": f"theirstack:{ext_id}",
            "source": "theirstack",
            "external_id": str(ext_id),
            "job_title": job_title,
            "company": j.get("company"),
            "url": url,
            "date_posted": _parse_date(j.get("date_posted")),
            "avg_salary_usd": j.get("avg_annual_salary_usd"),
            "seniority": j.get("seniority"),
            "technology_slugs": j.get("technology_slugs", []),
            "locations": _locations_to_strings(j.get("locations", [])),
            "category": row_category,
            "created_at": _parse_date(j.get("discovered_at")) or now_utc,
        }
        rows.append(row)

    print(f"[TRANSFORM] DB-ready rows: {len(rows)}")
    return rows


# =========================
# API facade
# =========================

def search_jobs(
    job_titles: Optional[List[str]] = None,
    job_descriptions: Optional[List[str]] = None,
    locations: Optional[List[str]] = None,
    limit: int = 20,
    page: int = 0,
    posted_max_age_days: int = POSTED_MAX_AGE_DAYS,
    country_codes: Iterable[str] = ("FR",),
    blur_company_data: bool = False,   # False => usable company names
    timeout: int = 20,
    job_id_not: Optional[List[str]] = None,  # exclude existing IDs in DB
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "include_total_results": False,
        "order_by": [{"desc": True, "field": "date_posted"}],
        "posted_at_max_age_days": posted_max_age_days,
        "job_country_code_or": list(country_codes),
        "page": page,
        "limit": limit,
        "blur_company_data": blur_company_data,
    }
    if job_titles:
        payload["job_title_or"] = job_titles
    if job_descriptions:
        payload["job_description_or"] = job_descriptions
    if locations:
        payload["job_location_pattern_or"] = locations
    if job_id_not:
        payload["job_id_not"] = list(job_id_not)

    print(
        f"[API] Page {page} x {limit} | titles={job_titles} "
        f"| desc?={'yes' if job_descriptions else 'no'} "
        f"| cities={len(locations) if locations else 0} | countries={list(country_codes)} "
        f"| job_id_not={len(job_id_not) if job_id_not else 0}"
    )

    return _post_with_retries(API_URL, payload, timeout=timeout)


# =========================
# DB helpers
# =========================

async def get_existing_theirstack_external_ids(days: int = 30) -> List[str]:
    """
    Fetch all external_id values for offers where source='theirstack'
    and date_posted is within the last `days` days.
    Returns strings because the API expects string IDs.
    """
    sql = f"""
        SELECT external_id
        FROM jobs.offers
        WHERE source = 'theirstack'
          AND date_posted >= (CURRENT_DATE - INTERVAL '{days} days')
    """
    async with connection() as conn:
        rows = await conn.fetch(sql)
    return [str(r["external_id"]) for r in rows]


# =========================
# Runner (Flow body)
# =========================

async def ingest_jobs(
    titles: Optional[List[str]] = None,
    descriptions: Optional[List[str]] = None,
    locations: Optional[List[str]] = None,
    page_limit: int = 3,
    per_page: int = 50,
    category_override: Optional[str] = None,
    country_codes: Iterable[str] = ("FR",),
):
    await ensure_refs()

    # Collect existing theirstack IDs once and reuse for all requests
    existing_ids = await get_existing_theirstack_external_ids()
    print(f"[INGEST] Existing theirstack external_ids to exclude: {len(existing_ids)}")

    # Optionally limit the exclusion list size if your API has limits
    if JOB_ID_NOT_MAX is not None and len(existing_ids) > JOB_ID_NOT_MAX:
        print(f"[WARN] Truncating job_id_not from {len(existing_ids)} to {JOB_ID_NOT_MAX} due to configured cap.")
        job_id_not_for_api = existing_ids[:JOB_ID_NOT_MAX]
    else:
        job_id_not_for_api = existing_ids

    total_upserted = 0
    for page in range(page_limit):
        print(f"[INGEST] === Page {page} ===")
        api_json = search_jobs(
            job_titles=titles,
            job_descriptions=descriptions,
            locations=locations,
            limit=per_page,
            page=page,
            blur_company_data=False,
            country_codes=country_codes,
            job_id_not=job_id_not_for_api,  # exclude already-seen IDs
        )

        rows = transform_jobs_for_db(api_json, category_override=category_override)
        if not rows:
            print("[INGEST] No rows; stopping.")
            break

        print(f"[DB] Upserting {len(rows)} rows...")
        n = await upsert_offers(rows)
        print(f"[DB] Upserted {n} rows.")
        total_upserted += n

        if len(rows) < per_page:
            print("[INGEST] Last page (less than per_page).")
            break

    print(f"[DONE] Total offers upserted: {total_upserted}")