"""Loads secrets from the environment (or .env) and searches from searches.toml."""
from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

# Real environment variables win over .env, so CI secrets are never shadowed.
load_dotenv(ROOT / ".env", override=False)


class ConfigError(Exception):
    pass


def database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise ConfigError(
            "DATABASE_URL is not set. Copy .env.example to .env and paste your "
            "Supabase connection string (Connect -> Session pooler)."
        )
    return url


def theirstack_api_keys() -> list[str]:
    raw = os.getenv("THEIRSTACK_API_KEYS", "")
    keys = list(dict.fromkeys(k.strip() for k in raw.split(",") if k.strip()))
    if not keys:
        raise ConfigError(
            "THEIRSTACK_API_KEYS is not set. Get a key at https://app.theirstack.com "
            "and put it in .env (comma-separate several keys to rotate between them)."
        )
    return keys


def redact(text: str) -> str:
    """Remove every value that comes from .env (connection string and its parts, API keys) from text.

    Use on anything printed, logged or shown: database driver errors, for one, include the host.
    """
    secrets = [os.getenv("DATABASE_URL", "").strip()]
    try:
        url = urlsplit(secrets[0])
        secrets += [url.password, url.hostname, url.username if url.username != "postgres" else None]
    except ValueError:
        pass
    secrets += [k.strip() for k in os.getenv("THEIRSTACK_API_KEYS", "").split(",")]
    secrets += [os.getenv("JOBSEEKER_GIT_TOKEN", "").strip()]
    for s in sorted({s for s in secrets if s and len(s) >= 4}, key=len, reverse=True):
        text = text.replace(s, "***")
    return text


def searches_path() -> Path:
    return Path(os.getenv("SEARCHES_FILE") or ROOT / "searches.toml")


# searches.toml key -> (TheirStack field, kind). Kinds: "text" = words/phrases, "regex" = regular
# expressions, "slug" = technology slugs, "enum" = values from ENUMS, "usd" = a number.
SEARCH_FILTERS: dict[str, tuple[str, str]] = {
    "titles": ("job_title_or", "text"),
    "exclude_titles": ("job_title_not", "text"),
    "title_patterns": ("job_title_pattern_or", "regex"),
    "title_patterns_all": ("job_title_pattern_and", "regex"),
    "exclude_title_patterns": ("job_title_pattern_not", "regex"),
    "description_words": ("job_description_contains_or", "text"),
    "exclude_description_words": ("job_description_contains_not", "text"),
    "description_patterns": ("job_description_pattern_or", "regex"),
    "description_patterns_all": ("job_description_pattern_and", "regex"),
    "exclude_description_patterns": ("job_description_pattern_not", "regex"),
    "technologies": ("job_technology_slug_or", "slug"),
    "technologies_all": ("job_technology_slug_and", "slug"),
    "exclude_technologies": ("job_technology_slug_not", "slug"),
    "exclude_companies": ("company_name_not", "text"),
    "seniority": ("job_seniority_or", "enum"),
    "employment": ("employment_statuses_or", "enum"),
    "workplace": ("workplace_types_or", "enum"),
    "min_salary_usd": ("min_salary_usd", "usd"),
    "max_salary_usd": ("max_salary_usd", "usd"),
}

ENUMS: dict[str, list[str]] = {
    "seniority": ["junior", "mid_level", "senior", "staff", "c_level"],
    "employment": ["full_time", "part_time", "contract", "temporary", "internship"],
    "workplace": ["on_site", "hybrid", "remote"],
}


@dataclass(frozen=True)
class Location:
    id: int
    name: str = ""


@dataclass(frozen=True)
class Region:
    name: str
    countries: list[str] = field(default_factory=list)
    exclude_countries: list[str] = field(default_factory=list)
    locations: list[Location] = field(default_factory=list)
    exclude_locations: list[Location] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)  # legacy: matched with TheirStack's deprecated pattern filter
    max_age_days: int | None = None


@dataclass(frozen=True)
class Search:
    name: str
    regions: list[Region]
    filters: dict[str, Any]  # TheirStack field -> value, only the ones that are set
    max_age_days: int | None = None
    max_results: int | None = None


@dataclass(frozen=True)
class Settings:
    max_age_days: int
    per_page: int
    run_budget: int
    exclude_seen_days: int
    searches: list[Search]


def _str_list(value, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ConfigError(f"{where} must be a list of non-empty strings")
    return [v.strip() for v in value]


def _pos_int(value, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ConfigError(f"{where} must be a positive integer")
    return value


def _countries(value, where: str) -> list[str]:
    codes = [c.upper() for c in _str_list(value, where)]
    bad = [c for c in codes if not re.fullmatch(r"[A-Z]{2}", c)]
    if bad:
        raise ConfigError(f"{where}: {bad} aren't 2-letter country codes (e.g. FR, CA)")
    return codes


def _locations(value, where: str) -> list[Location]:
    example = '{ id = 3012874, name = "Île-de-France" }'
    if not isinstance(value, list):
        raise ConfigError(f"{where} must be a list of entries like {example}")
    out = []
    for item in value:
        if isinstance(item, int) and not isinstance(item, bool):
            item = {"id": item}
        loc_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(loc_id, int) or isinstance(loc_id, bool):
            raise ConfigError(f"{where}: each entry needs a numeric id, like {example}")
        out.append(Location(id=loc_id, name=str(item.get("name", ""))))
    return out


def _filter_value(key: str, kind: str, value, where: str):
    if kind == "usd":
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise ConfigError(f"{where}.{key} must be a positive number")
        return value
    items = _str_list(value, f"{where}.{key}")
    if kind == "enum":
        bad = [v for v in items if v not in ENUMS[key]]
        if bad:
            raise ConfigError(f"{where}.{key}: unknown value(s) {bad}; allowed: {ENUMS[key]}")
    elif kind == "regex":
        for pattern in items:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ConfigError(f"{where}.{key}: invalid regular expression {pattern!r} ({e})") from e
    elif kind == "slug":
        items = [v.lower() for v in items]
    return items


def load_settings(path: Path | None = None) -> Settings:
    path = path or searches_path()
    if not path.exists():
        raise ConfigError(f"Searches file not found: {path}")
    with path.open("rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{path.name}: {e}") from e

    d = data.get("defaults", {})
    defaults = {
        "max_age_days": _pos_int(d.get("max_age_days", 15), "defaults.max_age_days"),
        "per_page": _pos_int(d.get("per_page", 25), "defaults.per_page"),
        "run_budget": _pos_int(d.get("run_budget", 40), "defaults.run_budget"),
        "exclude_seen_days": _pos_int(d.get("exclude_seen_days", 30), "defaults.exclude_seen_days"),
    }

    regions: dict[str, Region] = {}
    for name, r in data.get("regions", {}).items():
        where = f"regions.{name}"
        region = Region(
            name=name,
            countries=_countries(r["countries"], f"{where}.countries") if r.get("countries") else [],
            exclude_countries=_countries(r["exclude_countries"], f"{where}.exclude_countries") if r.get("exclude_countries") else [],
            locations=_locations(r.get("locations", []), f"{where}.locations"),
            exclude_locations=_locations(r.get("exclude_locations", []), f"{where}.exclude_locations"),
            cities=_str_list(r["cities"], f"{where}.cities") if r.get("cities") else [],
            max_age_days=_pos_int(r["max_age_days"], f"{where}.max_age_days") if "max_age_days" in r else None,
        )
        if not region.countries and not region.locations:
            raise ConfigError(f"{where} needs at least one country or location")
        regions[name] = region

    known_keys = set(SEARCH_FILTERS) | {"name", "regions", "max_age_days", "max_results"}
    searches: list[Search] = []
    for i, s in enumerate(data.get("search", [])):
        name = s.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"search #{i + 1} needs a name")
        where = f"search '{name}'"
        if any(x.name == name for x in searches):
            raise ConfigError(f"{where} is defined twice")
        typos = sorted(set(s) - known_keys)
        if typos:
            raise ConfigError(f"{where}: unknown setting(s) {typos}")
        region_names = _str_list(s.get("regions"), f"{where}.regions")
        unknown = [r for r in region_names if r not in regions]
        if unknown:
            raise ConfigError(f"{where} uses unknown region(s) {unknown}; defined: {sorted(regions)}")

        filters = {
            api_field: _filter_value(key, kind, s[key], where)
            for key, (api_field, kind) in SEARCH_FILTERS.items()
            if s.get(key) not in (None, [], "")
        }
        if "job_title_or" not in filters and "job_title_pattern_or" not in filters:
            raise ConfigError(f"{where} needs titles (or title_patterns)")
        lo, hi = filters.get("min_salary_usd"), filters.get("max_salary_usd")
        if lo and hi and lo > hi:
            raise ConfigError(f"{where}: min_salary_usd is higher than max_salary_usd")

        searches.append(Search(
            name=name,
            regions=[regions[r] for r in region_names],
            filters=filters,
            max_age_days=_pos_int(s["max_age_days"], f"{where}.max_age_days") if "max_age_days" in s else None,
            max_results=_pos_int(s["max_results"], f"{where}.max_results") if "max_results" in s else None,
        ))

    if not searches:
        raise ConfigError(f"{path.name} defines no [[search]] entries")

    return Settings(searches=searches, **defaults)
