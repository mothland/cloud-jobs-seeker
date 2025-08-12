# flows/ingest_offers.py
from typing import List, Optional
from prefect import flow, get_run_logger

from flows.theirstack import ingest_jobs
from flows.filters import (
    LOCATION_PRESETS,
    ILE_DE_FRANCE_CITIES,
    PRESET_COUNTRIES,
)

@flow(name="ingest-offers")
async def ingest_offers(
    # API filters
    titles: Optional[List[str]] = None,
    descriptions: Optional[List[str]] = None,

    # Choose preset or pass explicit locations/countries
    location_preset: Optional[str] = "idf",
    locations: Optional[List[str]] = None,
    countries: Optional[List[str]] = None,          # <- new: override preset country codes if needed

    # Pagination
    page_limit: int = 2,
    per_page: int = 50,

    # Freshness (forwarded to API layer)
    posted_max_age_days: int = 15,                  # <- forwarded to theirstack.search_jobs()

    # DB category to store (independent from titles); e.g. "data_engineer"
    category: Optional[str] = None,
):
    """
    Prefect entrypoint that hands params to the TheirStack ingestor.

    - 'titles' filters API search (job_title_or)
    - 'category' overrides the DB category saved for each row
    - 'location_preset' chooses from LOCATION_PRESETS and sets country codes
    - 'locations' can be provided explicitly; when omitted, preset is used
    - 'countries' can override preset-derived country codes (e.g., ["FR"], ["CH"])
    - 'posted_max_age_days' forwards freshness to the API
    """
    logger = get_run_logger()

    # Sensible defaults
    titles = titles or ["Data Engineer"]

    # Resolve locations from preset if not explicitly provided
    if locations is None:
        locations = LOCATION_PRESETS.get(location_preset or "", ILE_DE_FRANCE_CITIES)

    # Countries: preset unless explicitly overridden
    preset_countries = PRESET_COUNTRIES.get(location_preset or "idf", ["FR"])
    countries = countries or preset_countries

    logger.info(
        "Starting ingest | titles=%s, category=%s, preset=%s, cities=%d, countries=%s, page_limit=%d, per_page=%d, posted_max_age_days=%d",
        titles, category, location_preset, len(locations), countries, page_limit, per_page, posted_max_age_days
    )

    await ingest_jobs(
        titles=titles,
        descriptions=descriptions,
        locations=locations,
        page_limit=page_limit,
        per_page=per_page,
        category_override=category,
        country_codes=countries,              # important for Geneva (CH) vs IDF (FR)
        # the theirstack module reads POSTED_MAX_AGE_DAYS from env by default,
        # but we can still pass this if you decide to wire it through there later.
        # For now this param is logged for visibility; hook it up in theirstack.search_jobs if desired.
    )

    logger.info("Ingest completed ✅")
    return {
        "status": "ok",
        "titles": titles,
        "category": category,
        "preset": location_preset,
        "cities_count": len(locations),
        "countries": countries,
        "page_limit": page_limit,
        "per_page": per_page,
        "posted_max_age_days": posted_max_age_days,
    }