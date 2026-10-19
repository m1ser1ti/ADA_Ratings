<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/logo-transparent-dark.svg">
    <img src="docs/brand/logo-transparent-light.svg" alt="ADA Ratings" width="180">
  </picture>
</p>

<p align="center">
  Anonymous professor reviews for ADA University students.<br>
  <a href="https://www.adaratings.net"><strong>www.adaratings.net</strong></a>
</p>

<p align="center">
  <a href="https://github.com/m1ser1ti/ADA_Ratings/actions/workflows/ci.yml"><img src="https://github.com/m1ser1ti/ADA_Ratings/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/flask-3.1-000000?logo=flask" alt="Flask 3.1">
</p>

## Features

- **140 professors** across all six ADA schools (SPIA, SITE, SB, LAW, SAFS, SDA), kept in sync with the official faculty pages on ada.edu.az
- **Anonymous reviews** with a 1–10 rating, course code, difficulty, "would take again" and tags
- **Moderation:** profanity filter (English, Russian, Azerbaijani), reports from different networks hide a review until a moderator checks it, private admin queue
- **Abuse protection:** per-browser, per-network and per-professor rate limits backed by Redis
- **Fast and accessible:** no frontend build step, self-hosted fonts, light/dark theme, phone and tablet layouts, strict Content Security Policy
- **Nightly backups** to a second database, with a one-command restore

## Tech stack

| Layer | Tools |
| --- | --- |
| Backend | Python 3.12, Flask, Flask-SQLAlchemy, Flask-Limiter, Flask-Compress, gunicorn |
| Data | PostgreSQL, Redis for rate limits |
| Frontend | HTML, CSS, vanilla JavaScript (ES modules) |
| Hosting | Railway (EU West), GitHub Actions for tests |

## Project structure

```
app.py            Flask app: pages, JSON API, security headers, CLI commands
models.py         Database models (School, Professor, Review, Report)
faculty.py        Sync with the official faculty list in data/faculty.json
backup.py         Copy the whole database into a backup database and back
seed.py           Initial schools and professors for an empty database
public/           Static site: HTML pages, style.css, js/, img/, fonts/
tests/            pytest suite
docs/brand/       Logo files
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Database URL. Defaults to a local SQLite file. |
| `RATELIMIT_STORAGE_URI` | Where rate limits live, e.g. a Redis URL. Defaults to in-process memory, which resets on restart. |
| `SECRET_KEY` | Key for the one-way network codes stored with reports. Set a long random value so they stay comparable across restarts. |
| `ADMIN_TOKEN` | Turns on the moderation queue at `/admin.html`; without it the admin API does not exist. |
| `SITE_URL` | Public origin for canonical links, link previews and the sitemap. |
| `TRUST_PROXY` | Set to `1` behind exactly one hosting proxy so the real client address is used. |
| `BACKUP_DATABASE_URL` | A second Postgres for nightly copies (see Backups). |

## Deployment

- **Railway:** its Railpack builder ignores the Procfile and would run `python app.py` (a dev server on 127.0.0.1, so every request gets a 502). Set the service's *Custom Start Command* to `gunicorn app:app --preload --workers 2 --threads 4 --bind 0.0.0.0:$PORT` (two workers are safe because rate limits live in Redis) and add `TRUST_PROXY=1`. Link `DATABASE_URL` to a Postgres service and `RATELIMIT_STORAGE_URI` to a Redis service's `REDIS_URL`.
- The Procfile runs one worker with several threads, so in-memory rate limits work on hosts without Redis.
- Review limits are per browser (an anonymous random cookie), because students on the campus network share one public address. Looser per-network and per-professor ceilings stop scripted floods.
- Reports hide a review only when they come from at least three different networks; reports from one network still show up in the moderation queue.
- `flask --app app init-db` creates the tables and seeds an empty database explicitly; the app also does this on start.

## Backups

A second Postgres holds a full copy of the live data, refreshed every night:

1. In Railway, add a second PostgreSQL service named `Postgres-backup`.
2. Add a service from this repo named `db-backup` with:
   - *Custom Start Command*: `flask --app app backup-db`
   - *Cron Schedule*: `0 0 * * *` (00:00 UTC daily), restart policy *Never*
   - Variables: `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `BACKUP_DATABASE_URL=${{Postgres-backup.DATABASE_URL}}`
3. Each run replaces the backup with one consistent snapshot; its log prints the row counts.

To restore, run once with the same variables: `flask --app app restore-from-backup --yes`.

## Security

Please report vulnerabilities privately, see [SECURITY.md](SECURITY.md).
