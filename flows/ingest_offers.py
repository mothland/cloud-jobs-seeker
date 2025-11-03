# flows/ingest_offers.py
from typing import List, Optional, Dict, Any, Tuple
from prefect import flow, get_run_logger

from flows.theirstack import ingest_jobs
from flows.filters import (
    LOCATION_PRESETS,
    ILE_DE_FRANCE_CITIES,
    PRESET_COUNTRIES,
)

MAX_PER_PAGE_SUPPORTED = 25  # set to API cap (TheirStack free plan limit)


def _resolve_locations(preset: Optional[str]) -> List[str]:
    if not preset:
        return ILE_DE_FRANCE_CITIES
    return LOCATION_PRESETS.get(preset, ILE_DE_FRANCE_CITIES)


def _country_tuple_list(
    split_by_country: bool,
    generic_countries: Optional[List[str]],
    ca_preset: Optional[str],
    fr_preset: Optional[str],
    ca_country_codes: Optional[List[str]],
    fr_country_codes: Optional[List[str]],
) -> List[Tuple[str, List[str], List[str]]]:
    slices: List[Tuple[str, List[str], List[str]]] = []

    if split_by_country:
        ca_codes = ca_country_codes or ["CA"]
        ca_locs = _resolve_locations(ca_preset or "toronto")
        slices.append(("CA", ca_codes, ca_locs))

        fr_codes = fr_country_codes or ["FR"]
        fr_locs = _resolve_locations(fr_preset or "ile_de_france")
        slices.append(("FR", fr_codes, fr_locs))
        return slices

    countries = generic_countries or ["FR"]
    locations = _resolve_locations("ile_de_france")
    for code in countries:
        slices.append((code, [code], locations))
    return slices


@flow(name="ingest-offers")
async def ingest_offers(
    titles: Optional[List[str]] = None,
    descriptions: Optional[List[str]] = None,
    location_preset: Optional[str] = "idf",
    locations: Optional[List[str]] = None,
    countries: Optional[List[str]] = None,
    split_by_country: bool = False,
    ca_country_codes: Optional[List[str]] = None,
    ca_location_preset: Optional[str] = None,
    ca_posted_max_age_days: Optional[int] = None,
    fr_country_codes: Optional[List[str]] = None,
    fr_location_preset: Optional[str] = None,
    fr_posted_max_age_days: Optional[int] = None,
    posted_max_age_days: int = 15,
    total_weekly_budget: int = 100,
    category: Optional[str] = None,
):
    logger = get_run_logger()
    titles = titles or ["Data Engineer"]

    country_slices = _country_tuple_list(
        split_by_country=split_by_country,
        generic_countries=countries,
        ca_preset=ca_location_preset,
        fr_preset=fr_location_preset,
        ca_country_codes=ca_country_codes,
        fr_country_codes=fr_country_codes,
    )

    num_slices = len(country_slices)
    per_country_budget = max(1, total_weekly_budget // max(1, num_slices))

    logger.info(
        "Ingest plan | category=%s | titles=%s | total_weekly_budget=%d | per_country_budget=%d | slices=%s",
        category, titles, total_weekly_budget, per_country_budget, [c[0] for c in country_slices]
    )

    call_index = 0
    for label, country_codes, locs in country_slices:
        country_age_days = posted_max_age_days
        if split_by_country:
            if label == "CA" and ca_posted_max_age_days is not None:
                country_age_days = ca_posted_max_age_days
            if label == "FR" and fr_posted_max_age_days is not None:
                country_age_days = fr_posted_max_age_days

        call_index += 1

        # 💡 Compute pagination dynamically
        page_limit = max(1, (per_country_budget + MAX_PER_PAGE_SUPPORTED - 1) // MAX_PER_PAGE_SUPPORTED)
        per_page_this_call = min(MAX_PER_PAGE_SUPPORTED, per_country_budget)

        logger.info(
            "→ Call %d | country=%s | codes=%s | titles=%s | per_page=%d | page_limit=%d | posted_max_age_days=%d",
            call_index, label, country_codes, titles, per_page_this_call, page_limit, country_age_days
        )

        await ingest_jobs(
            titles=titles,
            descriptions=descriptions,
            locations=locs,
            page_limit=page_limit,
            per_page=per_page_this_call,
            category_override=category,
            country_codes=country_codes,
        )

    logger.info("Ingest completed ✅")
    return {
        "status": "ok",
        "category": category,
        "titles": titles,
        "countries_run": [c[0] for c in country_slices],
        "calls": len(country_slices),
        "per_country_budget": per_country_budget,
        "total_weekly_budget": total_weekly_budget,
    }