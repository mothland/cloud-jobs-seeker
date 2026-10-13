"""TheirStack client: retries with backoff, and rotates API keys on auth/quota errors."""
from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from typing import Any

import requests

from jobseeker.config import Region

log = logging.getLogger(__name__)

BASE_URL = "https://api.theirstack.com"
SEARCH_PATH = "/v1/jobs/search"
LOCATIONS_PATH = "/v0/catalog/locations"
KEYWORDS_PATH = "/v0/catalog/keywords"

MAX_ATTEMPTS = 6
BACKOFF_BASE = 1.0
BACKOFF_MAX = 30.0
TRANSIENT_STATUSES = {408, 429, 500, 502, 503, 504}
# 402 = out of credits on this key; 401/403 = bad or restricted key. Try the next key right away.
SWITCH_KEY_STATUSES = {401, 402, 403}


class TheirStackError(Exception):
    pass


class TheirStackClient:
    def __init__(self, api_keys: list[str], timeout: int = 30):
        if not api_keys:
            raise ValueError("at least one API key is required")
        self._keys = api_keys
        self._dead: set[int] = set()  # keys that returned 401/402/403 during this run
        self._timeout = timeout
        self._session = requests.Session()

    def _live_keys(self) -> list[int]:
        return [i for i in range(len(self._keys)) if i not in self._dead]

    def _request(self, method: str, path: str, *, json: dict | None = None, params: dict | None = None) -> Any:
        last_error = "no attempts made"
        for attempt in range(MAX_ATTEMPTS):
            live = self._live_keys()
            if not live:
                raise TheirStackError(f"All {len(self._keys)} API key(s) were rejected. Last error: {last_error}")
            idx = live[attempt % len(live)]

            try:
                resp = self._session.request(
                    method,
                    BASE_URL + path,
                    json=json,
                    params=params,
                    headers={"Authorization": f"Bearer {self._keys[idx]}", "Accept": "application/json"},
                    timeout=self._timeout,
                )
            except (requests.Timeout, requests.ConnectionError) as e:
                last_error = f"{type(e).__name__}: {e}"
                log.warning("Network error on attempt %d/%d (%s), retrying", attempt + 1, MAX_ATTEMPTS, type(e).__name__)
                self._backoff(attempt)
                continue

            status = resp.status_code
            if 200 <= status < 300:
                return resp.json()

            detail = resp.text.strip().replace("\n", " ")[:300]
            last_error = f"HTTP {status}: {detail}"
            if status in SWITCH_KEY_STATUSES:
                log.warning("Key #%d rejected (HTTP %d: %s); switching key", idx, status, detail)
                self._dead.add(idx)
            elif status in TRANSIENT_STATUSES:
                log.warning("HTTP %d on attempt %d/%d, retrying", status, attempt + 1, MAX_ATTEMPTS)
                self._backoff(attempt, resp.headers.get("Retry-After"))
            else:
                raise TheirStackError(f"Request rejected: {last_error}\nRequest: {json or params}")

        raise TheirStackError(f"Gave up after {MAX_ATTEMPTS} attempts. Last error: {last_error}")

    def search_page(self, payload: dict[str, Any]) -> dict[str, Any]:
        """The full response: `data` (jobs) and `metadata` (totals, when requested)."""
        return self._request("POST", SEARCH_PATH, json=payload)

    def search(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return self.search_page(payload).get("data") or []

    def locations(self, name: str, country_code: str | None = None, limit: int = 15) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"name": name, "limit": limit}
        if country_code:
            params["country_code"] = country_code.upper()
        body = self._request("GET", LOCATIONS_PATH, params=params)
        return body.get("data", body) if isinstance(body, dict) else body

    def technologies(self, query: str, limit: int = 15) -> list[dict[str, Any]]:
        body = self._request("GET", KEYWORDS_PATH, params={"name_pattern": query, "keyword_type": "technology", "limit": limit})
        return body.get("data") or []

    @staticmethod
    def _backoff(attempt: int, retry_after: str | None = None) -> None:
        if retry_after and retry_after.isdigit():
            delay = min(float(retry_after), BACKOFF_MAX)
        else:
            delay = min(BACKOFF_BASE * 2 ** attempt, BACKOFF_MAX) + random.random()
        time.sleep(delay)


def build_payload(
    *,
    filters: dict[str, Any],
    region: Region,
    max_age_days: int,
    page: int,
    limit: int,
    exclude_ids: list[str],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "order_by": [{"desc": True, "field": "date_posted"}],
        "posted_at_max_age_days": max_age_days,
        "page": page,
        "limit": limit,
        "include_total_results": False,
        **filters,
    }
    if region.countries:
        payload["job_country_code_or"] = region.countries
    if region.exclude_countries:
        payload["job_country_code_not"] = region.exclude_countries
    if region.locations:
        payload["job_location_or"] = [{"id": loc.id} for loc in region.locations]
    elif region.cities:
        # Deprecated by TheirStack in favour of job_location_or; kept so old configs keep working.
        payload["job_location_pattern_or"] = region.cities
    if region.exclude_locations:
        payload["job_location_not"] = [{"id": loc.id} for loc in region.exclude_locations]
    ids = [int(i) for i in exclude_ids if i.isdigit()]
    if ids:
        payload["job_id_not"] = ids
    return payload


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _location_strings(locations: list[dict[str, Any]] | None, fallback_country: str | None) -> list[str]:
    out: list[str] = []
    for loc in locations or []:
        city = (loc.get("city") or loc.get("name") or "").strip()
        state = (loc.get("state") or loc.get("admin1_name") or "").strip()
        country = (loc.get("country_code") or fallback_country or "").strip().upper()
        text = ", ".join(p for p in (city, state, country) if p)
        if text and text not in out:
            out.append(text)
    return out


def to_rows(jobs: list[dict[str, Any]], *, search: str, region: Region) -> list[dict[str, Any]]:
    # Only guess a missing country when the region covers exactly one.
    fallback_country = region.countries[0] if len(region.countries) == 1 else None
    rows = []
    for j in jobs:
        ext_id = j.get("id")
        if ext_id is None:
            continue
        rows.append({
            "offer_id": f"theirstack:{ext_id}",
            "source": "theirstack",
            "external_id": str(ext_id),
            "search": search,
            "region": region.name,
            "job_title": j.get("job_title"),
            "company": j.get("company"),
            "url": j.get("url") or j.get("final_url") or j.get("source_url"),
            "date_posted": _parse_dt(j.get("date_posted")),
            "avg_salary_usd": j.get("avg_annual_salary_usd"),
            "seniority": j.get("seniority"),
            "technology_slugs": j.get("technology_slugs") or [],
            "locations": _location_strings(j.get("locations"), fallback_country),
            "remote": j.get("remote"),
            "hybrid": j.get("hybrid"),
            "employment_statuses": j.get("employment_statuses") or [],
            "salary_string": j.get("salary_string"),
            "company_domain": j.get("company_domain"),
        })
    return rows
