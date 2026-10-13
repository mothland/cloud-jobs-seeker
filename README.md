# cloud-jobs-seeker

> This is an entirely vibe coded version of a project I initially did not vibe code, but wrote hastily as a way to find an "alternance" contract. I thought it could benefit some of my classmates in their job searching and, well, ended up vibe coding a polished version quickly. Quite tragically, it is made of static HTML and Python glued together in ways no soul would have willingly written in anything but a vibe-coded hobby tinkering attempt. If you're a recruiter, you can safely ignore this project if you're trying to evaluate programming skills. That's just a tool I thought would be useful for my awesome classmates :)

**[English](#user-guide) · [Français](#guide-dutilisation) · [Technical reference](#technical-reference)**

Collects job offers on a schedule and saves them in your own database, so you can browse and filter
them in one place. Free to run.

*Récupère des offres d'emploi automatiquement et les enregistre dans votre propre base de données,
pour les consulter et les filtrer au même endroit. Gratuit.*

## User guide

No coding needed. You'll fill in a settings page in your browser.

### 1. Create two free accounts

- **[Supabase](https://supabase.com)** stores the jobs. Create a new project and **write down the
  database password** you choose. When it's ready, click **Connect**, find **Session pooler**, and
  copy the connection string (it starts with `postgresql://`).
- **[TheirStack](https://app.theirstack.com)** finds the jobs. Copy your API key from
  **Settings → API Key**. The free plan gives a limited number of credits each month, and each job
  found uses one.

### 2. Install

1. Install **Python 3.11 or newer** from [python.org](https://www.python.org/downloads/). On Windows,
   tick **“Add Python to PATH”** in the installer.
2. Get this project: on GitHub, click **Code → Download ZIP** and unzip it. (If you want it to run on
   a schedule later, use **Fork** instead to get your own copy, then download that.)
3. Open a terminal in the project folder. On Windows, right-click inside the folder → **Open in
   Terminal**. On a Mac, right-click the folder → **New Terminal at Folder**.
4. Paste these lines one at a time:

   ```sh
   python -m venv .venv
   .venv\Scripts\activate          # on Mac/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```

### 3. Open the app and set it up

```sh
python -m jobseeker ui
```

A page opens in your browser (if not, open the link shown in the terminal). It has three tabs:
**Offers**, **Dashboard** and **Settings**, and a **FR / EN** switch at the top right. Start with
**Settings** and go through it in order:

1. **Connections:** paste the Supabase connection string (replace `[YOUR-PASSWORD]` with your
   password) and your TheirStack key, then click **Save connections**, **Test database**, and
   **Create / update tables**.
2. **Budget:** how many jobs each run may fetch. The yellow box estimates your monthly credit use.
3. **Regions:** where to look. Pick countries, then optionally narrow down with the place search
   box (type “Île-de-France” or “Lyon” and pick it from the list), or exclude places.
4. **Searches:** which job titles to look for, and in which regions. Each search can also filter on
   words to exclude from the title, words the description must or must not mention, technologies,
   seniority, contract type, work mode and salary. Every filter except titles is optional; leave
   it empty to include everything. The yellow notes warn where a filter can hide jobs. For example,
   most posts don't list a salary, so a salary filter drops all of those.
5. **Save and try:** **Dry run** shows what would be searched, for free. **Count** tells you how
   many jobs a query matches in total (at most 1 credit). **Run now** really fetches jobs.

The connection details go in a `.env` file, which stays on your computer and is never uploaded.
Your searches go in `searches.toml`, which is part of the project. To stop the app, press
**Ctrl+C** in the terminal.

### 4. Follow your applications

- **Offers** lists every job found. Use the search box, or **Filters** to narrow down by any field
  (status, company, location, seniority, work mode, technologies, dates…). Click an offer to open
  the posting, mark it **Saved**, **Applied**, **Interview**, **Offer received**, **Rejected** or
  **Not interested**, set your application and interview dates, and keep notes. Offers found since
  your last visit are marked **New**.
- **Dashboard** shows your progress: offers found, applications, interviews and response rate, a
  pipeline from "found" to "offer received", weekly activity, the companies and technologies that
  come up most, upcoming interviews, and applications still waiting for an answer.

Your statuses and notes are stored in your own database, next to the offers.

### 5. Optional: run it automatically

This uses GitHub to run the search twice a week, even when your computer is off. You need your own
copy of the project on GitHub (a **Fork**).

1. In your copy on GitHub, go to **Settings → Secrets and variables → Actions → New repository
   secret**, and add two secrets: `DATABASE_URL` (the Supabase connection string, with your
   password) and `THEIRSTACK_API_KEYS` (your key).
2. Whenever you change your searches, put your `searches.toml` in your copy on GitHub: commit and
   push it, or on the GitHub website use **Add file → Upload files**. The scheduled runs use the
   version on GitHub.
3. Open the **Actions** tab, choose **Ingest jobs**, and click **Run workflow** to check that it works.

The days and times are in the [technical reference](#option-a-github-actions-simplest).

---

## Guide d'utilisation

Aucune ligne de code à écrire : tout se règle dans une page de votre navigateur.

### 1. Créer deux comptes gratuits

- **[Supabase](https://supabase.com)** stocke les offres. Créez un nouveau projet et **notez le mot
  de passe de la base** que vous choisissez. Une fois le projet prêt, cliquez sur **Connect**,
  repérez **Session pooler** et copiez la chaîne de connexion (elle commence par `postgresql://`).
- **[TheirStack](https://app.theirstack.com)** trouve les offres. Copiez votre clé API dans
  **Settings → API Key**. Le forfait gratuit donne un nombre limité de crédits par mois, et chaque
  offre trouvée en utilise un.

### 2. Installer

1. Installez **Python 3.11 ou plus récent** depuis [python.org](https://www.python.org/downloads/).
   Sous Windows, cochez **« Add Python to PATH »** dans l'installateur.
2. Récupérez le projet : sur GitHub, cliquez sur **Code → Download ZIP** puis décompressez-le. (Pour
   le faire tourner automatiquement plus tard, utilisez plutôt **Fork** pour avoir votre propre
   copie, puis téléchargez celle-ci.)
3. Ouvrez un terminal dans le dossier du projet. Sous Windows : clic droit dans le dossier →
   **Ouvrir dans le Terminal**. Sur Mac : clic droit sur le dossier → **Nouveau terminal au dossier**.
4. Collez ces lignes une par une :

   ```sh
   python -m venv .venv
   .venv\Scripts\activate          # sur Mac/Linux : source .venv/bin/activate
   pip install -r requirements.txt
   ```

### 3. Ouvrir l'application et la configurer

```sh
python -m jobseeker ui
```

Une page s'ouvre dans votre navigateur (sinon, ouvrez le lien affiché dans le terminal). Elle a trois
onglets : **Offres**, **Tableau de bord** et **Réglages**, et un bouton **FR / EN** en haut à droite.
Commencez par **Réglages** et suivez les étapes dans l'ordre :

1. **Connexions :** collez la chaîne de connexion Supabase (remplacez `[YOUR-PASSWORD]` par votre
   mot de passe) et votre clé TheirStack, puis cliquez sur **Enregistrer les connexions**,
   **Tester la base** et **Créer / mettre à jour les tables**.
2. **Budget :** le nombre d'offres que chaque exécution peut récupérer. L'encadré jaune estime vos
   crédits utilisés par mois.
3. **Régions :** où chercher. Choisissez des pays, puis restreignez si besoin avec le champ de
   recherche de lieux (tapez « Île-de-France » ou « Lyon » et choisissez dans la liste), ou excluez
   des lieux.
4. **Recherches :** les intitulés de poste à chercher, et dans quelles régions. Chaque recherche peut
   aussi filtrer sur des mots à exclure de l'intitulé, des mots que la description doit ou ne doit
   pas contenir, des technologies, le niveau, le type de contrat, le mode de travail et le salaire.
   Tous les filtres sont facultatifs sauf les intitulés : laissez vide pour tout inclure. Les
   encadrés jaunes signalent quand un filtre peut masquer des offres. Par exemple, la plupart des
   offres n'affichent pas de salaire, donc un filtre de salaire les écarte toutes.
5. **Enregistrer et tester :** la **Simulation** montre ce qui serait cherché, gratuitement.
   **Compter** indique combien d'offres correspondent à une requête au total (1 crédit maximum).
   **Lancer maintenant** récupère vraiment les offres.

Les connexions vont dans un fichier `.env`, qui reste sur votre ordinateur et n'est jamais envoyé.
Vos recherches vont dans `searches.toml`, qui fait partie du projet. Pour arrêter l'application,
appuyez sur **Ctrl+C** dans le terminal.

### 4. Suivre vos candidatures

- **Offres** liste toutes les offres trouvées. Utilisez le champ de recherche, ou **Filtres** pour
  affiner selon n'importe quel champ (statut, entreprise, lieu, niveau, mode de travail,
  technologies, dates…). Cliquez sur une offre pour ouvrir l'annonce, la marquer **Gardée**,
  **Postulé**, **Entretien**, **Proposition reçue**, **Refusée** ou **Pas intéressé·e**, renseigner
  vos dates de candidature et d'entretien, et prendre des notes. Les offres trouvées depuis votre
  dernière visite sont marquées **Nouvelle**.
- **Tableau de bord** montre où vous en êtes : offres trouvées, candidatures, entretiens et taux de
  réponse, le parcours de « trouvée » à « proposition reçue », l'activité par semaine, les
  entreprises et technologies qui reviennent le plus, les entretiens à venir et les candidatures
  toujours sans réponse.

Vos statuts et notes sont enregistrés dans votre propre base de données, à côté des offres.

### 5. Facultatif : lancement automatique

GitHub peut lancer la recherche deux fois par semaine, même ordinateur éteint. Il vous faut votre
propre copie du projet sur GitHub (un **Fork**).

1. Dans votre copie sur GitHub, allez dans **Settings → Secrets and variables → Actions → New
   repository secret** et ajoutez deux secrets : `DATABASE_URL` (la chaîne de connexion Supabase,
   avec votre mot de passe) et `THEIRSTACK_API_KEYS` (votre clé).
2. À chaque modification de vos recherches, mettez votre `searches.toml` dans votre copie sur
   GitHub : faites un commit et un push, ou sur le site de GitHub utilisez **Add file → Upload
   files**. Les lancements automatiques utilisent la version présente sur GitHub.
3. Ouvrez l'onglet **Actions**, choisissez **Ingest jobs** et cliquez sur **Run workflow** pour
   vérifier que tout fonctionne.

Les jours et heures se règlent dans la [référence technique](#option-a-github-actions-simplest)
(en anglais).

---

# Technical reference

## What you need

- Python 3.11+
- A free [Supabase](https://supabase.com) project (or any Postgres 13+)
- A [TheirStack](https://app.theirstack.com) API key. The free plan includes a limited number of
  credits per month, and each job returned costs one credit.

## Setup (about 5 minutes)

**1. Create the database.** In Supabase, create a new project and save the database password.
Then click **Connect**, find the **Session pooler** connection string, and copy it.

> Use the *pooler* string, not the *direct connection* one: the direct one only works over IPv6,
> which GitHub Actions and many home networks don't have.

**2. Configure.**

```sh
git clone https://github.com/<you>/cloud-jobs-seeker.git
cd cloud-jobs-seeker
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # Windows: copy .env.example .env
```

Edit `.env` and fill in `DATABASE_URL` (the string from step 1, with your password in place of
`[YOUR-PASSWORD]`) and `THEIRSTACK_API_KEYS`. Or run `python -m jobseeker ui`, which edits `.env` and
your searches for you from a local browser page (see the [user guide](#3-open-the-app-and-set-it-up)).

**3. Create the tables.**

```sh
python -m jobseeker setup
```

This checks your config, connects to the database and creates the `jobs` schema. It's safe to run
again at any time; it only applies what's missing.

**4. Edit your searches, then try them.**

```sh
python -m jobseeker run --dry-run   # shows the API queries; costs nothing
python -m jobseeker run             # fetches and stores jobs
```

## Configuring searches

Everything lives in `searches.toml`, which is committed: the version in this repo is the author's
own, so a fork starts from a working config and edits it. Scheduled runs use the version that's
pushed. The settings page edits the same file (it rewrites it without comments and keeps the
previous version as `searches.toml.bak`). `SEARCHES_FILE=path` points the app at another file.

The format:

```toml
[defaults]
run_budget = 40          # max jobs (= API credits) per run, split evenly across queries
max_age_days = 15        # only jobs posted in the last N days
per_page = 25            # API page size (25 is the free-plan cap)
exclude_seen_days = 30   # don't pay again for jobs stored in the last N days

[regions.berlin]
countries = ["DE"]
locations = [{ id = 2950159, name = "Berlin" }]   # optional; omit to search the whole country
max_age_days = 10                                  # optional override

[[search]]
name = "backend"                 # stored in the `search` column
titles = ["Backend Engineer", "Backend Developer"]
exclude_titles = ["Intern", "Working Student"]
regions = ["berlin"]
max_results = 10                 # optional: cap this search's share of run_budget
```

Each search runs once per region it lists.

### Regions

| Key | What it does |
|---|---|
| `countries` | 2-letter country codes to search in |
| `exclude_countries` | Countries to leave out |
| `locations` | Only jobs in these places: cities, regions, metro areas. Each is `{ id = …, name = "…" }`, where `name` is just a label for you. Get IDs from the settings page's place search, or from TheirStack's [locations catalog](https://theirstack.com/en/docs/api-reference/catalog/get_catalog_locations_v0). |
| `exclude_locations` | Places to leave out, same format |
| `max_age_days` | Overrides the default for this region |
| `cities` | **Legacy.** Plain city names, matched with a filter TheirStack has deprecated: a name also matches longer names that contain it, e.g. "Paris" matches "Cormeilles-en-Parisis". Ignored once `locations` is set. |

A region needs at least one country or location.

### Search filters

Every filter is optional except `titles`. Lists are OR: a job matches if any entry does.

| Key | Matches |
|---|---|
| `titles` | Title contains **all the words** of any entry, in any order. Not case-sensitive; accents count. |
| `exclude_titles` | Same matching, to exclude |
| `description_words` / `exclude_description_words` | Whole words or phrases in the description. Not case-sensitive, unless the entry is UPPERCASE. |
| `technologies` / `technologies_all` / `exclude_technologies` | Technology slugs TheirStack detected in the post (`python`, `apache-spark`…). Any of / all of / none of. |
| `seniority` | Any of `junior`, `mid_level`, `senior`, `staff`, `c_level` |
| `employment` | Any of `full_time`, `part_time`, `contract`, `temporary`, `internship` |
| `workplace` | Any of `on_site`, `hybrid`, `remote` |
| `min_salary_usd` / `max_salary_usd` | Yearly salary in USD |
| `title_patterns` / `title_patterns_all` / `exclude_title_patterns` | Regular expressions on the title (not case-sensitive): any / all / none |
| `description_patterns` / `description_patterns_all` / `exclude_description_patterns` | Regular expressions on the description: any / all / none. **Case-sensitive**; start with `(?i)` to ignore case. |
| `exclude_companies` | Exact company names, case-sensitive |

> **Filters that can hide jobs.** `seniority`, `employment` and the salary filters drop every job
> where TheirStack couldn't find that information, and most posts don't list a salary at all.
> Posts that don't mention a work mode count as `on_site`, so `workplace = ["remote"]` skips them.
> Leave these out unless you really want them.

**Budget:** credits used per month ≈ `run_budget` × runs per month. With the default schedule
(twice a week) and `run_budget = 40`, that's about 350 a month. Lower it if your plan has fewer
credits.

**Several API keys:** list them comma-separated in `THEIRSTACK_API_KEYS`. When one runs out of
credits (or is rejected), the run moves on to the next.

## Scheduling

### Option A: GitHub Actions (simplest)

[`.github/workflows/ingest.yml`](.github/workflows/ingest.yml) runs on Mondays and Thursdays at
06:00 UTC.

1. Push the repo to GitHub (a private repo is fine).
2. Go to **Settings → Secrets and variables → Actions** and add two repository secrets:
   `DATABASE_URL` and `THEIRSTACK_API_KEYS`. Runs use the `searches.toml` on the branch.
3. Under **Actions → Ingest jobs → Run workflow**, start a first run by hand to check it works.
   There's a *dry run* checkbox that costs no credits.

Each run applies any new migrations, then fetches jobs. Failed runs show up in the Actions tab, and
GitHub emails you about them. Edit the `cron:` line to change the schedule.

> GitHub disables scheduled workflows in a repo after 60 days with no commits. If that happens,
> re-enable it from the Actions tab.

### Option B: Prefect Cloud

Use this if you want a run history UI and automatic retries of failed runs. The free plan
includes a managed work pool, so there's no server to keep running.

```sh
pip install -r requirements-prefect.txt
prefect cloud login
prefect work-pool create jobseeker --type prefect:managed
python -m jobseeker setup
python -m jobseeker.prefect_flow deploy
```

`deploy` copies `DATABASE_URL` and `THEIRSTACK_API_KEYS` from your `.env` into Prefect Secret
blocks, and creates a deployment that runs on Mondays and Thursdays and pulls the code from your
git remote. Options: `--cron "0 6 * * *"`, `--branch main`, `--work-pool jobseeker`.

- **Private repo:** set `JOBSEEKER_GIT_TOKEN` in `.env` before deploying (on GitHub: a fine-grained
  token with read-only *Contents* access to this repo).
- **Changes to `searches.toml`** take effect on the next run once they're pushed; no redeploy needed.
- **Changing secrets:** edit `.env` and run `deploy` again.

Pick one option. Running both would fetch every search twice.

## The data

```sql
-- Newest jobs first
select job_title, company, locations, date_posted, url
from jobs.offers
order by date_posted desc nulls last
limit 50;

-- Most requested technologies per search
select search, tech, count(*)
from jobs.offers, unnest(technology_slugs) as tech
group by 1, 2
order by 3 desc;
```

| Column | |
|---|---|
| `offer_id` | `theirstack:<id>`, primary key |
| `search`, `region` | which `[[search]]` and region found it |
| `job_title`, `company`, `url`, `seniority` | as returned by TheirStack |
| `date_posted` | when the job was posted |
| `avg_salary_usd` | yearly, when TheirStack has it |
| `technology_slugs`, `locations` | text arrays |
| `first_seen_at`, `last_seen_at` | when this tool first and last stored it |
| `remote`, `hybrid`, `employment_statuses`, `salary_string`, `company_domain` | as returned by TheirStack |

Your tracking lives in two more tables, so new runs never overwrite it:
`jobs.applications` (one row per offer you've acted on: `status`, `notes`, `applied_at`,
`interview_at`) and `jobs.application_events` (every status change, with its time).

The tables live in a `jobs` schema, which Supabase doesn't expose through its public REST API, so
they're only reachable with the database password.

Schema changes go in `migrations/` as new numbered `.sql` files; `setup` applies the ones not yet
recorded in `jobs.schema_migrations`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Database connection failed` | Use the Session pooler string, check the password, and make sure the Supabase project isn't paused (free projects pause after a week without activity; restore it from the dashboard). |
| `All API key(s) were rejected` | The keys are invalid or out of credits. Check your TheirStack dashboard. |
| `Database is missing migrations` | Run `python -m jobseeker setup`. |
| A run returns 0 jobs | Run `--dry-run` and check the query. Very specific titles, few cities, or a small `max_age_days` can match nothing. **Count** in the settings page tells you how many jobs a query matches before filters you add. |
| Offers / Dashboard tab says the database needs updating | Settings → **Create / update tables**, or `python -m jobseeker setup`. |

Output never contains anything from `.env`: connection details and keys are replaced with `***` in
every message, log line and error, including CI logs. Run with `-v` to see a (redacted) traceback.

## Project layout

```
jobseeker/
  __main__.py      CLI: setup, run, ui
  config.py        reads .env and the searches file; redacts secrets from output
  ingest.py        turns searches into queries; fetches and stores
  theirstack.py    API client: retries, backoff, key rotation, catalogs
  db.py            connection, migrations, upserts
  tracker.py       offers list, application tracking, dashboard numbers
  prefect_flow.py  optional Prefect flow and deploy command
  ui/server.py     local web app (python -m jobseeker ui)
  ui/static/       its pages: offers, dashboard, settings
migrations/        SQL schema
searches.toml      what to search for (edit it in your fork)
```

## License

Do whatever you want with it, including commercially. No warranty, no liability, and you're
responsible for following the terms of the services you connect it to and data-protection law
such as the GDPR. See [LICENSE](LICENSE).
