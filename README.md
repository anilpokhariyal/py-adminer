# PyAdminer

PyAdminer is a **Flask** web UI for **MySQL** (similar in spirit to [Adminer](https://www.adminer.org/)): browse databases and tables, run SQL, edit rows, and export data. It is open source; contributions are welcome.

## Features

- Connect with server, user, password, and optional default database
- List databases (sizes, collations); create, rename, and drop databases
- Tables: structure (columns, indexes, foreign keys), alter, browse with filters/order/limit
- Row **edit** and **delete** using primary keys (including composite)
- **SQL command** panel; optional **natural-language to SQL** via the AI assistant (configured under **AI** in the sidebar)
- **Visualize** tab: column profiles, charts (categorical, time series, scatter), pivot aggregates
- **Impact** / **Quality** / **Diff** table insights (FKs, views/routines references, PK duplicates, FK orphans, table comparison)
- **Data** grid: optional heatmap for numeric columns, JSON and long-text expanders
- **Database diagram** (Mermaid ER) and **Advanced** panel (views, routines, triggers, events)
- Export table as **CSV** or **SQL** (`INSERT`s); export whole database as SQL (row cap)
- **Activity log** (JSON audit file, tail view and download)
- **CSRF** protection, optional **read-only** mode, optional **HTTP Basic Auth**, **rate limits**
- **`/health`** endpoint for load balancers and probes

## Requirements

- **Python** 3.9+
- **MySQL** or **MariaDB** reachable from the app host
- System packages to build **`mysqlclient`** (e.g. Debian/Ubuntu: `default-libmysqlclient-dev`, `pkg-config`)

Runtime Python deps are listed in `pyproject.toml` and mirrored in `requirements.txt` (used by Docker).

## Local setup (virtualenv)

```bash
git clone https://github.com/anilpokhariyal/py-adminer.git
cd py-adminer
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
export FLASK_APP=main.py
export SECRET_KEY="change-me-in-production"   # required for stable sessions in production
flask run
# or: python main.py
```

Defaults: bind `0.0.0.0:5000` (override with `FLASK_RUN_HOST` / `FLASK_RUN_PORT`).

## Docker (local stack with MySQL)

From the repo root:

```bash
make docker-local
# equivalent: docker compose -f docker/docker-compose.local.yml up --build -d
```

- **App:** http://127.0.0.1:8080  
- **MySQL:** host `127.0.0.1` port **3307** (mapped from container `3306`)  
- In the UI, for the bundled DB use **Server:** `mysql`, **User:** `root`, **Password:** `root`, **Database:** `demo` (optional)

The compose file bind-mounts the project and sets `FLASK_DEBUG=1` so most code changes reload without rebuilding. Re-run `make docker-local` after changing `requirements.txt` or `docker/Dockerfile`. Restart only the app: `make docker-local-restart`.

An older Laradock-oriented `docker/docker-compose.yml` may still exist for custom networks; the **local** file above is the supported quick start.

## Configuration (environment variables)

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask session signing; **set explicitly in production** |
| `FLASK_DEBUG` | `1` / `true` for debug (not for production) |
| `FLASK_RUN_HOST`, `FLASK_RUN_PORT` | Dev server bind (defaults `0.0.0.0`, `5000`) |
| `MYSQL_PORT` | Default MySQL port for connections (default `3306`) |
| `PYADMINER_DEFAULT_MYSQL_HOST` | Prefilled “Server” on the login form (e.g. `mysql` in Compose) |
| `PYADMINER_READ_ONLY` | `1` / `true`: block mutating routes and mutating SQL in the SQL panel |
| `PYADMINER_AUTH_USERNAME`, `PYADMINER_AUTH_PASSWORD` | Optional HTTP Basic Auth in front of the whole app |
| `PYADMINER_AUDIT_LOG_PATH` | Audit JSON log path; empty → Flask `instance/` folder |
| `PYADMINER_AUDIT_MAX_QUERY_CHARS` | Max SQL/query chars stored per audit line (default `16384`) |
| `PYADMINER_AI_DISABLE` | `1` / `true`: disable AI assistant regardless of UI settings |
| `PYADMINER_AI_SETTINGS_PATH` | Optional path for encrypted AI settings file (default: `instance/ai_settings.enc`) |
| `RATELIMIT_ENABLED`, `RATELIMIT_STORAGE_URI` | Flask-Limiter (default in-memory; use Redis URI in multi-worker setups) |
| `MYSQL_TEST_*` | `MYSQL_TEST_HOST`, `MYSQL_TEST_PORT`, `MYSQL_TEST_USER`, `MYSQL_TEST_PASSWORD`, `MYSQL_TEST_DATABASE` for optional integration tests |

AI provider keys and model settings are **not** environment variables: configure them in the app under **AI** (stored encrypted on disk, key derived from `SECRET_KEY`).

## Development

```bash
pip install -e ".[dev]"
ruff check pyadminer tests
pytest
```

Integration tests run only when `MYSQL_TEST_HOST` is set (see `tests/conftest.py`). CI runs ruff and pytest with a MySQL service when configured.

## Documentation

- [docs/PROJECT_IMPROVEMENT_PLAN.md](docs/PROJECT_IMPROVEMENT_PLAN.md) — security, engineering, and product notes
- [docs/ADMINER_GAP.md](docs/ADMINER_GAP.md) — comparison with Adminer/phpMyAdmin and possible next steps

## License

See [LICENSE](LICENSE) (MIT).
