"""Browsing offers, tracking applications, and dashboard numbers."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

STATUSES = ["new", "saved", "applied", "interview", "offer", "rejected", "not_interested"]
# How far along the pipeline a status is; rejected/not_interested don't advance it.
STAGE_RANK = {"saved": 1, "applied": 2, "interview": 3, "offer": 4}
SORTS = {
    "posted": "o.date_posted DESC NULLS LAST, o.first_seen_at DESC",
    "found": "o.first_seen_at DESC",
    "company": "lower(o.company) ASC NULLS LAST, o.date_posted DESC NULLS LAST",
    "updated": "a.updated_at DESC NULLS LAST, o.date_posted DESC NULLS LAST",
}
PAGE_SIZE = 50


class TrackerError(Exception):
    pass


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _offer_filters(f: dict[str, Any]) -> tuple[str, list[Any]]:
    """WHERE clause for the offers list. Every value is passed as a parameter."""
    where, params = ["TRUE"], []
    q = str(f.get("q") or "").strip()
    if q:
        where.append("(o.job_title ILIKE %s OR o.company ILIKE %s)")
        params += [_like(q), _like(q)]
    statuses = [s for s in f.get("statuses") or [] if s in STATUSES]
    if statuses:
        where.append("coalesce(a.status, 'new') = ANY(%s)")
        params.append(statuses)
    elif not f.get("show_hidden"):
        where.append("coalesce(a.status, 'new') <> 'not_interested'")
    for key, column in (("searches", "o.search"), ("regions", "o.region")):
        values = [str(v) for v in f.get(key) or []]
        if values:
            where.append(f"{column} = ANY(%s)")
            params.append(values)

    # "Contains" text filters on single fields.
    for key, expr in (("title", "o.job_title"), ("company", "o.company"),
                      ("location", "array_to_string(o.locations, ' ')"), ("notes", "a.notes")):
        text = str(f.get(key) or "").strip()
        if text:
            where.append(f"{expr} ILIKE %s")
            params.append(_like(text))

    seniority = [str(s) for s in f.get("seniority") or []]
    if seniority:
        known = [s for s in seniority if s != "unknown"]
        where.append("(o.seniority = ANY(%s)" + (" OR o.seniority IS NULL)" if "unknown" in seniority else ")"))
        params.append(known)

    modes = {
        "remote": "o.remote IS TRUE",
        "hybrid": "o.hybrid IS TRUE",
        "on_site": "(o.remote IS NOT TRUE AND o.hybrid IS NOT TRUE)",
    }
    work_clauses = [modes[w] for w in modes if w in (f.get("work") or [])]
    if work_clauses:
        where.append("(" + " OR ".join(work_clauses) + ")")

    technologies = [str(t).strip().lower() for t in f.get("technologies") or [] if str(t).strip()]
    if technologies:
        where.append("o.technology_slugs && %s")  # mentions any of them
        params.append(technologies)

    for key, cond in (("has_salary", "(o.salary_string IS NOT NULL OR o.avg_salary_usd IS NOT NULL)"),
                      ("has_notes", "coalesce(a.notes, '') <> ''"),
                      ("has_interview", "a.interview_at IS NOT NULL")):
        if f.get(key):
            where.append(cond)

    for key, column in (("posted_days", "coalesce(o.date_posted, o.first_seen_at)"), ("found_days", "o.first_seen_at")):
        days = f.get(key)
        if isinstance(days, int) and days > 0:
            where.append(f"{column} >= now() - make_interval(days => %s)")
            params.append(days)
    return " AND ".join(where), params


def list_offers(conn: psycopg.Connection, f: dict[str, Any]) -> dict[str, Any]:
    where, params = _offer_filters(f)
    order = SORTS.get(f.get("sort") or "posted", SORTS["posted"])
    page = max(0, int(f.get("page") or 0))
    base = f"FROM jobs.offers o LEFT JOIN jobs.applications a USING (offer_id) WHERE {where}"
    with conn.cursor(row_factory=dict_row) as cur:
        total = cur.execute(f"SELECT count(*) AS n {base}", params).fetchone()["n"]
        rows = cur.execute(
            f"""SELECT o.offer_id, o.job_title, o.company, o.url, o.search, o.region, o.locations,
                       o.date_posted, o.first_seen_at, o.remote, o.hybrid, o.seniority, o.salary_string,
                       coalesce(a.status, 'new') AS status, a.updated_at, a.applied_at, a.interview_at,
                       coalesce(a.notes, '') <> '' AS has_notes
                {base} ORDER BY {order} LIMIT %s OFFSET %s""",
            [*params, PAGE_SIZE, page * PAGE_SIZE],
        ).fetchall()
    return {"total": total, "page": page, "page_size": PAGE_SIZE, "rows": rows}


def facets(conn: psycopg.Connection) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        searches = [r["search"] for r in cur.execute("SELECT DISTINCT search FROM jobs.offers ORDER BY 1")]
        regions = [r["region"] for r in cur.execute("SELECT DISTINCT region FROM jobs.offers WHERE region IS NOT NULL ORDER BY 1")]
        counts = {r["status"]: r["n"] for r in cur.execute(
            "SELECT coalesce(a.status, 'new') AS status, count(*) AS n"
            " FROM jobs.offers o LEFT JOIN jobs.applications a USING (offer_id) GROUP BY 1"
        )}
    return {"searches": searches, "regions": regions, "status_counts": counts}


def get_offer(conn: psycopg.Connection, offer_id: str) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        offer = cur.execute(
            """SELECT o.*, coalesce(a.status, 'new') AS status, coalesce(a.notes, '') AS notes,
                      a.applied_at, a.interview_at, a.updated_at
               FROM jobs.offers o LEFT JOIN jobs.applications a USING (offer_id) WHERE o.offer_id = %s""",
            [offer_id],
        ).fetchone()
        if not offer:
            raise TrackerError("Offer not found")
        offer["events"] = cur.execute(
            "SELECT status, at FROM jobs.application_events WHERE offer_id = %s ORDER BY at", [offer_id]
        ).fetchall()
    return offer


def _parse_ts(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as e:
        raise TrackerError(f"Invalid date: {value}") from e


def update_offer(conn: psycopg.Connection, body: dict[str, Any]) -> dict[str, Any]:
    """Change status, notes and/or dates. Only the fields present in `body` are touched."""
    offer_id = str(body.get("offer_id") or "")
    status = body.get("status")
    if status is not None and status not in STATUSES:
        raise TrackerError(f"Unknown status: {status}")

    with conn.transaction():
        exists = conn.execute("SELECT 1 FROM jobs.offers WHERE offer_id = %s", [offer_id]).fetchone()
        if not exists:
            raise TrackerError("Offer not found")
        conn.execute("INSERT INTO jobs.applications (offer_id) VALUES (%s) ON CONFLICT DO NOTHING", [offer_id])
        current = conn.execute("SELECT status, applied_at FROM jobs.applications WHERE offer_id = %s FOR UPDATE",
                               [offer_id]).fetchone()

        sets, params = ["updated_at = now()"], []
        if status is not None and status != current[0]:
            sets.append("status = %s")
            params.append(status)
            conn.execute("INSERT INTO jobs.application_events (offer_id, status) VALUES (%s, %s)", [offer_id, status])
            if status == "applied" and current[1] is None and "applied_at" not in body:
                sets.append("applied_at = now()")
        if "notes" in body:
            sets.append("notes = %s")
            params.append(str(body["notes"] or "")[:20000])
        for key in ("applied_at", "interview_at"):
            if key in body:
                sets.append(f"{key} = %s")
                params.append(_parse_ts(body[key]))
        conn.execute(f"UPDATE jobs.applications SET {', '.join(sets)} WHERE offer_id = %s", [*params, offer_id])
    conn.commit()
    return get_offer(conn, offer_id)


def dashboard(conn: psycopg.Connection, f: dict[str, Any]) -> dict[str, Any]:
    """Numbers for the dashboard. `days` limits to offers found in that window; `search` to one search."""
    days = f.get("days") if isinstance(f.get("days"), int) and f["days"] > 0 else None
    search = str(f["search"]) if f.get("search") else None
    scope, params = ["TRUE"], []
    if days:
        scope.append("o.first_seen_at >= now() - make_interval(days => %s)")
        params.append(days)
    if search:
        scope.append("o.search = %s")
        params.append(search)
    scope_sql = " AND ".join(scope)
    weeks = 12 if not days or days > 84 else max(4, -(-days // 7))

    # Furthest stage each offer reached, from its history (a rejection after an interview still counts as an interview).
    reached = f"""
        WITH scoped AS (SELECT o.offer_id, o.search, o.company, coalesce(o.date_posted, o.first_seen_at) AS posted
                        FROM jobs.offers o WHERE {scope_sql}),
        reached AS (
            SELECT s.offer_id, s.search, s.company, s.posted,
                   max(CASE e.status WHEN 'saved' THEN 1 WHEN 'applied' THEN 2 WHEN 'interview' THEN 3 WHEN 'offer' THEN 4 ELSE 0 END) AS rank,
                   bool_or(e.status IN ('interview', 'offer', 'rejected')) AS answered
            FROM scoped s LEFT JOIN jobs.application_events e USING (offer_id)
            GROUP BY s.offer_id, s.search, s.company, s.posted
        )"""

    with conn.cursor(row_factory=dict_row) as cur:
        totals = cur.execute(
            f"""{reached}
                SELECT count(*) AS offers,
                       count(*) FILTER (WHERE rank >= 1) AS saved,
                       count(*) FILTER (WHERE rank >= 2) AS applied,
                       count(*) FILTER (WHERE rank >= 3) AS interview,
                       count(*) FILTER (WHERE rank >= 4) AS offer,
                       count(*) FILTER (WHERE rank >= 2 AND answered) AS answered
                FROM reached""",
            params,
        ).fetchone()
        new_this_week = cur.execute(
            f"SELECT count(*) AS n FROM jobs.offers o WHERE {scope_sql} AND o.first_seen_at >= now() - interval '7 days'",
            params,
        ).fetchone()["n"]

        weekly = cur.execute(
            f"""WITH weeks AS (
                    SELECT generate_series(date_trunc('week', now()) - make_interval(weeks => %s - 1),
                                           date_trunc('week', now()), interval '1 week') AS week
                )
                SELECT w.week,
                       (SELECT count(*) FROM jobs.offers o
                         WHERE {scope_sql} AND o.first_seen_at >= w.week AND o.first_seen_at < w.week + interval '1 week') AS found,
                       (SELECT count(DISTINCT e.offer_id) FROM jobs.application_events e JOIN jobs.offers o USING (offer_id)
                         WHERE {scope_sql} AND e.status = 'applied' AND e.at >= w.week AND e.at < w.week + interval '1 week') AS applied
                FROM weeks w ORDER BY w.week""",
            [weeks, *params, *params],
        ).fetchall()

        technologies = cur.execute(
            f"""SELECT t AS slug, count(*) AS n FROM jobs.offers o, unnest(o.technology_slugs) AS t
                WHERE {scope_sql} GROUP BY t ORDER BY n DESC, t LIMIT 12""",
            params,
        ).fetchall()

        by_search = cur.execute(
            f"""{reached}
                SELECT search, count(*) AS offers, count(*) FILTER (WHERE rank >= 2) AS applied,
                       count(*) FILTER (WHERE rank >= 3) AS interview, count(*) FILTER (WHERE rank >= 4) AS offer
                FROM reached GROUP BY search ORDER BY offers DESC""",
            params,
        ).fetchall()

        companies = cur.execute(
            f"""{reached}
                SELECT company, count(*) AS offers, count(*) FILTER (WHERE rank >= 2) AS applied,
                       count(*) FILTER (WHERE rank >= 3) AS interview, count(*) FILTER (WHERE rank >= 4) AS offer,
                       max(posted) AS last_posted
                FROM reached WHERE coalesce(company, '') <> ''
                GROUP BY company ORDER BY offers DESC, last_posted DESC NULLS LAST LIMIT 15""",
            params,
        ).fetchall()

        waiting = cur.execute(
            """SELECT o.offer_id, o.job_title, o.company, a.applied_at
               FROM jobs.applications a JOIN jobs.offers o USING (offer_id)
               WHERE a.status = 'applied' AND a.applied_at < now() - interval '14 days'
               ORDER BY a.applied_at LIMIT 10""",
        ).fetchall()
        upcoming = cur.execute(
            """SELECT o.offer_id, o.job_title, o.company, a.interview_at
               FROM jobs.applications a JOIN jobs.offers o USING (offer_id)
               WHERE a.interview_at >= now() - interval '1 day'
               ORDER BY a.interview_at LIMIT 10""",
        ).fetchall()

    return {
        "totals": {**totals, "new_this_week": new_this_week},
        "weekly": weekly,
        "technologies": technologies,
        "by_search": by_search,
        "companies": companies,
        "waiting": waiting,
        "upcoming": upcoming,
    }
