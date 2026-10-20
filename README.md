<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/logo-transparent-dark.svg">
    <img src="docs/brand/logo-transparent-light.svg" alt="ProfScope" width="180">
  </picture>
</p>

<p align="center">
  Anonymous professor reviews written by students. An independent project, not affiliated with any university.<br>
  <a href="https://www.profscope.com"><strong>www.profscope.com</strong></a>
</p>

<p align="center">
  <a href="https://github.com/m1ser1ti/ADA_Ratings/actions/workflows/ci.yml"><img src="https://github.com/m1ser1ti/ADA_Ratings/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/flask-3.1-000000?logo=flask" alt="Flask 3.1">
</p>

## Features

- **140 professors** across all schools and programs (SPIA, SITE, SB, LAW, SAFS, SDA, SE, EAPP, Foundation), kept in sync with the public faculty pages of the university
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
faculty.py        Sync with the public faculty list in data/faculty.json
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
| `ADMIN_TOKEN` | Turns on the moderation queue at `/admin.html`; without it the admin API does not exist. Required for every admin action (restoring reviews, lifting bans). |
| `MODERATOR_TOKEN` | Token for the AI moderator on the Mac. It only grants access to the `/api/moderation/*` endpoints; it cannot perform admin actions. |
| `SITE_URL` | Public origin for canonical links, link previews and the sitemap. |
| `REDIRECT_HOSTS` | Old domains, comma separated (host names only). Requests on those hosts get a "we moved" notice and a link to the same page on `SITE_URL`. |
| `TRUST_PROXY` | Set to `1` behind exactly one hosting proxy so the real client address is used. |
| `BACKUP_DATABASE_URL` | A second Postgres for nightly copies (see Backups). |

## Deployment

- **Railway:** its Railpack builder ignores the Procfile and would run `python app.py` (a dev server on 127.0.0.1, so every request gets a 502). Set the service's *Custom Start Command* to `gunicorn app:app --preload --workers 2 --threads 4 --bind 0.0.0.0:$PORT` (two workers are safe because rate limits live in Redis) and add `TRUST_PROXY=1`. Link `DATABASE_URL` to a Postgres service and `RATELIMIT_STORAGE_URI` to a Redis service's `REDIS_URL`.
- The Procfile runs `gunicorn` with 2 workers and 4 threads (the same as the start command above) and sets `TRUST_PROXY=1`. Railway ignores the Procfile when a start command is set in the dashboard, so `TRUST_PROXY=1` must also be a service variable there. Use Redis for rate limits with more than one worker.
- Review limits are per browser (an anonymous random cookie), because students on the campus network share one public address. Looser per-network and per-professor ceilings stop scripted floods.
- Reports: three reports from different networks hide a review until it is checked again, and hidden reviews go back to the AI queue. Reports from one network only show up in the moderation queue. A faculty removal request hides the review at once until a moderator decides.
- Cookies: `profscope_client` (signed, HttpOnly, anonymous, for rate limits) and `profscope_rules` (remembers that the rules were accepted).
- The admin queue flags a possible rating burst (5 or more rating-only reviews of one professor from one network within 24 hours). Nothing is blocked; it is a hint for a human.
- `GET /healthz` returns `{"ok":true}`, or 503 when the database does not answer. Use `/healthz` as the Railway healthcheck path and for an uptime monitor.
- `flask --app app purge-personal-data` erases removal-request contact details and messages: the email is cleared when a request is resolved, the message 30 days after. The nightly backup job runs it too.
- `flask --app app init-db` creates the tables and seeds an empty database explicitly; the app also does this on start.

## Backups

A second Postgres holds a full copy of the live data, refreshed every night:

1. In Railway, add a second PostgreSQL service named `Postgres-backup`.
2. Add a service from this repo named `db-backup` with:
   - *Custom Start Command*: `flask --app app backup-db`
   - *Cron Schedule*: `0 0 * * *` (00:00 UTC daily), restart policy *Never*
   - Variables: `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `BACKUP_DATABASE_URL=${{Postgres-backup.DATABASE_URL}}`
3. Each run writes a dated snapshot (tables with a `_YYYYMMDD` suffix; a rerun on the same day replaces that day's copy), reading the source in one consistent transaction. The newest 7 complete snapshots are kept. The log prints the row counts.

The nightly run first runs `purge-personal-data`. Backups made before dated snapshots existed left unsuffixed tables in the backup database; remove those by hand once.

To restore, run once with the same variables: `flask --app app restore-from-backup --yes`. It uses the newest complete snapshot and first upgrades the target schema.

## Security

Please report vulnerabilities privately, see [SECURITY.md](SECURITY.md).

## AI moderation

Every published review with text is also checked by an AI model that runs **on a Mac, not in the cloud**: `moderator/ai_moderator.py` (Python standard library only) asks the site for reviews the AI has not checked yet (`GET /api/moderation/queue`), lets a local [Ollama](https://ollama.com) model (`qwen3:14b` by default) judge each one against the [review rules](public/rules.html), and sends back the verdict (`POST /api/moderation/reviews/<id>`). Review text goes only from the site to that Mac and its local model; it never reaches a third-party AI service.

- **ok:** the review stays. Harsh but honest criticism of the teaching is kept.
- **remove:** the review is hidden, not deleted, and a moderator can restore it from `/admin.html`.
- **remove + ban:** for severe cases only (threats, hate, sexual harassment, personal data, obscene insults), the author's browser is also blocked. Bans can be lifted from the admin page.

The server needs `MODERATOR_TOKEN` set; the Mac uses the same value. This token only works on the moderation endpoints; `ADMIN_TOKEN` is still required for admin actions.

```bash
ollama pull qwen3:14b                       # once; Ollama must be running
bash moderator/install-macos.sh             # LaunchAgent: starts at login, restarts, keeps the Mac awake
nano ~/.config/ada-ratings/moderator.env    # paste MODERATOR_TOKEN= (file is chmod 600)
bash moderator/uninstall-macos.sh           # stop and remove the agent (settings and logs are kept)
```

The env file also takes `SITE_URL`, `OLLAMA_URL`, `OLLAMA_MODEL` and `POLL_SECONDS` (the script defaults to 10 seconds; the generated env file sets 60). Changes are picked up without a restart. To try it by hand: `python3 moderator/ai_moderator.py --once --dry-run` classifies the queue and prints the verdicts without changing anything. `python3 moderator/ai_moderator.py --status` prints the time of the last successful poll, whether the queue answers now and how many reviews are waiting.

Logs: `~/Library/Logs/ada-ratings-moderator.log` (rotating); crashes land in `~/Library/Logs/ada-ratings-moderator.launchd.log`. After a connection problem the log says "Connection to ProfScope restored after N minutes". The time of the last successful poll is kept in `~/Library/Logs/ada-ratings-moderator.state.json`.

## Operations

These are set up outside the code, by the site owner:

- **Uptime monitor** pointed at `https://www.profscope.com/healthz`, with an alert to a phone or email.
- **Error tracking** for the production app (the app does not ship with one).
- **Off-provider backup copy:** the nightly backup lives in the same hosting account as the live data. Keep a periodic dump somewhere else, so losing the account does not lose both.
- **Moderator Mac:** check the log or run `--status` now and then; the AI moderator only works while that Mac is on and online.
