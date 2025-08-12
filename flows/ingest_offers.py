# flows/ingest_offers.py
from typing import List, Optional, Dict, Any, Tuple
from prefect import flow, get_run_logger

from flows.theirstack import ingest_jobs
from flows.filters import (
    LOCATION_PRESETS,
    ILE_DE_FRANCE_CITIES,
    PRESET_COUNTRIES,
)

MAX_PER_PAGE_SUPPORTED = 50  # safety cap for the upstream API


def _resolve_locations(preset: Optional[str]) -> List[str]:
    if not preset:
        return ILE_DE_FRANCE_CITIES
    return LOCATION_PRESETS.get(preset, ILE_DE_FRANCE_CITIES)


def _country_tuple_list(
    split_by_country: bool,
    generic_countries: Optional[List[str]],
    ch_preset: Optional[str],
    fr_preset: Optional[str],
    ch_country_codes: Optional[List[str]],
    fr_country_codes: Optional[List[str]],
) -> List[Tuple[str, List[str], List[str]]]:
    """
    Returns a list of (label, country_codes, locations) to iterate over.
    - When split_by_country=True, use CH and FR slices with their own presets.
    - Otherwise, use generic country list and a single preset.
    """
    slices: List[Tuple[str, List[str], List[str]]] = []

    if split_by_country:
        # Switzerland slice
        ch_codes = ch_country_codes or ["CH"]
        ch_locs = _resolve_locations(ch_preset or "geneva")
        slices.append(("CH", ch_codes, ch_locs))

        # France slice
        fr_codes = fr_country_codes or ["FR"]
        fr_locs = _resolve_locations(fr_preset or "ile_de_france")
        slices.append(("FR", fr_codes, fr_locs))
        return slices

    # Fallback: generic mode
    countries = generic_countries or ["FR"]
    # Use preset countries to pick a sensible default locations list
    # If mixed countries, caller should pass an explicit preset/locations;
    # here we keep a simple default to IDF if unset.
    locations = _resolve_locations("ile_de_france")
    for code in countries:
        slices.append((code, [code], locations))
    return slices


@flow(name="ingest-offers")
async def ingest_offers(
    # API filters
    titles: Optional[List[str]] = None,
    descriptions: Optional[List[str]] = None,

    # Legacy single-preset inputs (kept for compatibility; mostly ignored in fair-split mode)
    location_preset: Optional[str] = "idf",
    locations: Optional[List[str]] = None,
    countries: Optional[List[str]] = None,

    # Fair-split controls
    split_by_country: bool = False,

    # Country-specific knobs (used when split_by_country=True)
    ch_country_codes: Optional[List[str]] = None,
    ch_location_preset: Optional[str] = None,
    ch_posted_max_age_days: Optional[int] = None,

    fr_country_codes: Optional[List[str]] = None,
    fr_location_preset: Optional[str] = None,
    fr_posted_max_age_days: Optional[int] = None,

    # Global freshness default if country-specific not set
    posted_max_age_days: int = 15,

    # Weekly budget (e.g., 100/wk if 400/mo)
    total_weekly_budget: int = 100,

    # Hard override per-call limit (skips budget math); if None we compute it
    per_call_limit: Optional[int] = None,

    # DB category to store; e.g. "data_engineer"
    category: Optional[str] = None,
):
    """
    One deployment per category. Inside, we iterate countries × titles and
    enforce a per-call cap so scarce regions (CH) aren't drowned by FR.

    Fair-split logic:
      - calls = len(titles) * len(country_slices)
      - per_call = per_call_limit or floor(total_weekly_budget / calls)
      - page_limit is fixed to 1; per_page = per_call (<= MAX_PER_PAGE_SUPPORTED)
      - Remainder (if any) is distributed to the first few calls

    Country selection:
      - If split_by_country=True, build two slices: CH then FR, each with its own preset and freshness.
      - Else, use `countries` and a single locations preset (legacy mode).
    """
    logger = get_run_logger()

    # Sensible defaults
    titles = titles or ["Data Engineer"]

    # Build the (label, country_codes, locations) plan
    country_slices = _country_tuple_list(
        split_by_country=split_by_country,
        generic_countries=countries,
        ch_preset=ch_location_preset,
        fr_preset=fr_location_preset,
        ch_country_codes=ch_country_codes,
        fr_country_codes=fr_country_codes,
    )

    # Compute budget per call
    num_calls = max(1, len(titles) * len(country_slices))
    if per_call_limit is None:
        base_per_call = max(1, total_weekly_budget // num_calls)
    else:
        base_per_call = max(1, per_call_limit)

    # Cap to API constraint, and figure out remainder for fair distribution
    per_page_base = min(base_per_call, MAX_PER_PAGE_SUPPORTED)
    remainder = max(0, total_weekly_budget - per_page_base * num_calls)

    # For legacy single-preset mode, ensure locations/countries are resolved
    if locations is None and not split_by_country:
        locations = LOCATION_PRESETS.get(location_preset or "", ILE_DE_FRANCE_CITIES)
    if countries is None and not split_by_country:
        preset_countries = PRESET_COUNTRIES.get(location_preset or "idf", ["FR"])
        countries = preset_countries

    logger.info(
        "Ingest plan | category=%s | titles=%s | split_by_country=%s | total_weekly_budget=%d | num_calls=%d | per_page_base=%d | remainder=%d",
        category, titles, split_by_country, total_weekly_budget, num_calls, per_page_base, remainder
    )

    call_index = 0  # used to distribute remainder (+1) to first N calls

    # Iterate countries first (so CH goes first when split_by_country=True), then titles
    for label, country_codes, locs in country_slices:
        # Determine freshness per country (fallback to global)
        country_age_days = posted_max_age_days
        if split_by_country:
            if label == "CH" and ch_posted_max_age_days is not None:
                country_age_days = ch_posted_max_age_days
            if label == "FR" and fr_posted_max_age_days is not None:
                country_age_days = fr_posted_max_age_days

        for title in titles:
            # Distribute any leftover 1s to early calls for perfect sum == total_weekly_budget
            per_page_this_call = per_page_base + (1 if call_index < remainder else 0)
            call_index += 1

            logger.info(
                "→ Call %d/%d | country=%s codes=%s | title=%s | per_page=%d | page_limit=1 | posted_max_age_days=%d",
                call_index, num_calls, label, country_codes, title, per_page_this_call, country_age_days
            )

            await ingest_jobs(
                titles=[title],
                descriptions=descriptions,
                locations=locs,
                page_limit=1,                    # exactly one page per (title × country)
                per_page=per_page_this_call,     # computed fair-share per-call cap
                category_override=category,
                country_codes=country_codes,
                # NOTE: If/when theirstack.search_jobs() accepts posted_max_age_days,
                # pass it through there. For now we log it for visibility.
                # Example (when wired): posted_max_age_days=country_age_days,
            )

    logger.info("Ingest completed ✅")
    return {
        "status": "ok",
        "category": category,
        "titles": titles,
        "split_by_country": split_by_country,
        "countries_run": [c[0] for c in country_slices],
        "calls": num_calls,
        "per_page_base": per_page_base,
        "remainder_distributed": remainder,
        "total_weekly_budget": total_weekly_budget,
    }