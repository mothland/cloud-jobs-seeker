-- Your progress on each offer, kept apart from jobs.offers so new runs never overwrite it.
-- Safe to run more than once.

CREATE TABLE IF NOT EXISTS jobs.applications (
    offer_id      text PRIMARY KEY REFERENCES jobs.offers (offer_id) ON DELETE CASCADE,
    status        text NOT NULL DEFAULT 'new'
                  CHECK (status IN ('new', 'saved', 'applied', 'interview', 'offer', 'rejected', 'not_interested')),
    notes         text NOT NULL DEFAULT '',
    applied_at    timestamptz,
    interview_at  timestamptz,               -- next (or last) interview
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS applications_status_idx ON jobs.applications (status);

-- One row per status change, for timelines and the dashboard funnel.
CREATE TABLE IF NOT EXISTS jobs.application_events (
    id        bigserial PRIMARY KEY,
    offer_id  text NOT NULL REFERENCES jobs.offers (offer_id) ON DELETE CASCADE,
    status    text NOT NULL,
    at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS application_events_offer_idx ON jobs.application_events (offer_id, at);
CREATE INDEX IF NOT EXISTS application_events_status_idx ON jobs.application_events (status, at);
CREATE INDEX IF NOT EXISTS offers_first_seen_idx ON jobs.offers (first_seen_at DESC);
