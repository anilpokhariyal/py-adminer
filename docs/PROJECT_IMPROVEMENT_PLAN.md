# PyAdminer — improvement plan (implemented)

This document summarizes the industry-oriented upgrades applied to the project. The codebase is a Flask web UI for MySQL (Adminer-style browsing, structure, data, SQL panel).

## Security baseline

- Removed unsafe `eval()` on collation input; collations are selected as `charset|collation` strings and validated.
- CSRF protection (Flask-WTF) on forms; AJAX delete sends `X-CSRFToken`.
- Dynamic SQL uses validated identifiers (`[a-zA-Z0-9_]{1,64}`) and parameterized clauses for search filters and row delete/update.
- `SECRET_KEY` and `DEBUG` come from environment (`SECRET_KEY`, `FLASK_DEBUG`).
- `CREATE TABLE` submissions are restricted to DDL that starts with `CREATE TABLE` and references the submitted table name.

## Engineering

- Application factory (`create_app`), package layout under `pyadminer/`, blueprint `main`.
- `pyproject.toml` with runtime and `[dev]` extras; `LICENSE` (MIT); `.gitignore` extended.
- Docker image installs MySQL client dev libraries for `mysqlclient`; `EXPOSE 5000` matches the app port.
- `/health` JSON endpoint for probes.

## Quality

- `pytest` for validators, `/health`, and optional MySQL integration (`MYSQL_TEST_*`).
- `ruff` in CI.
- GitHub Actions workflow: Ubuntu, MySQL 8 service, install `default-libmysqlclient-dev`, run ruff + pytest.

## Product

- Table structure view includes **indexes** (`information_schema.STATISTICS`) and **foreign keys** (`KEY_COLUMN_USAGE`).
- Row **edit/delete** use real **primary keys** (including composite); JSON payload / hidden `pk_json`.
- **Export** table as CSV or SQL (`/export/csv` and `/export/sql`).

## Hardening (optional via env)

- `PYADMINER_READ_ONLY=true` blocks mutating routes and mutating SQL in the SQL panel (prefix check).
- `PYADMINER_AUTH_USERNAME` / `PYADMINER_AUTH_PASSWORD` enable HTTP Basic Auth in front of the app.
- `RATELIMIT_ENABLED`, `RATELIMIT_STORAGE_URI` (Flask-Limiter); limits on destructive or heavy POST routes.
- `pyadminer.audit` logger records exports, DDL, SQL execution (truncated), drops, etc.

## Environment reference

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask session signing (required in production) |
| `FLASK_DEBUG` | `1` / `true` for debug |
| `FLASK_RUN_HOST`, `FLASK_RUN_PORT` | Dev server bind |
| `MYSQL_PORT` | Default MySQL port for sessions (default 3306) |
| `PYADMINER_READ_ONLY` | Read-only mode |
| `PYADMINER_AUTH_USERNAME` / `PYADMINER_AUTH_PASSWORD` | Optional Basic Auth |
| `RATELIMIT_ENABLED`, `RATELIMIT_STORAGE_URI` | Rate limiting |
| `MYSQL_TEST_*` | Integration tests in CI |
