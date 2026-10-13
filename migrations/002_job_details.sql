-- Fields the new search filters work on, so you can see why a job matched. Safe to run more than once.

ALTER TABLE jobs.offers ADD COLUMN IF NOT EXISTS remote               boolean;
ALTER TABLE jobs.offers ADD COLUMN IF NOT EXISTS hybrid               boolean;
ALTER TABLE jobs.offers ADD COLUMN IF NOT EXISTS employment_statuses  text[] NOT NULL DEFAULT '{}';
ALTER TABLE jobs.offers ADD COLUMN IF NOT EXISTS salary_string        text;
ALTER TABLE jobs.offers ADD COLUMN IF NOT EXISTS company_domain       text;
