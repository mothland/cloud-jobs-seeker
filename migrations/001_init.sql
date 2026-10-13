-- Initial schema. Safe to run more than once.

CREATE SCHEMA IF NOT EXISTS jobs;

CREATE TABLE IF NOT EXISTS jobs.offers (
    offer_id          text PRIMARY KEY,          -- "<source>:<external_id>"
    source            text        NOT NULL,      -- e.g. "theirstack"
    external_id       text        NOT NULL,
    search            text        NOT NULL,      -- name of the [[search]] in searches.toml
    region            text,                      -- name of the [regions.*] entry
    job_title         text,
    company           text,
    url               text,
    date_posted       timestamptz,
    avg_salary_usd    numeric,
    seniority         text,
    technology_slugs  text[]      NOT NULL DEFAULT '{}',
    locations         text[]      NOT NULL DEFAULT '{}',
    first_seen_at     timestamptz NOT NULL DEFAULT now(),
    last_seen_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS offers_source_posted_idx ON jobs.offers (source, date_posted DESC);
CREATE INDEX IF NOT EXISTS offers_search_idx        ON jobs.offers (search);
